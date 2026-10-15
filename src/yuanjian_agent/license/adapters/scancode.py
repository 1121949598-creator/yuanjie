from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import tempfile

from ...core.context import ScanContext
from ...core.exceptions import ExternalToolUnavailable
from ...core.scanner import ScanStatus
from ...external.process import ProcessRequest
from ..models import LicenseProviderResult
from .base import InvalidProviderOutput, has_link, note_partial, read_json, sanitize_result, version, within
from .process import ScanCodeProcessRunner, controlled_environment
from .scancode_parser import ScanCodeResultParser


REQUIRED_FLAGS = ("--license", "--package", "--json", "--strip-root", "--processes", "--timeout", "--quiet")


class ScanCodeAdapter:
    name = "scancode"

    def __init__(self, runner=None) -> None:
        self.runner = runner or ScanCodeProcessRunner()

    def scan(self, context: ScanContext):
        result = self.collect(context)
        if result.status not in {ScanStatus.SUCCESS, ScanStatus.PARTIAL}:
            raise ExternalToolUnavailable()
        return result.licenses

    def collect(self, context: ScanContext) -> LicenseProviderResult:
        result = LicenseProviderResult(self.name, execution_mode="local-cli")
        if not context.config.scanners.enable_scancode:
            result.status, result.reason_code = ScanStatus.DISABLED, "disabled"
            return result
        config = context.config.license_providers
        workspace = None
        try:
            search = os.pathsep.join(entry for entry in os.environ.get("PATH", "").split(os.pathsep)
                                     if entry and Path(entry).is_absolute()
                                     and not within(Path(entry).resolve(), context.project_root.resolve()))
            located = config.scancode_executable or shutil.which("scancode", path=search)
            if not located:
                result.reason_code = "binary_not_found"
                return result
            executable = Path(located)
            if (not executable.is_absolute() or has_link(executable) or not executable.is_file()
                    or within(executable.resolve(), context.project_root.resolve())
                    or executable.suffix.lower() in {".bat", ".cmd", ".ps1"}):
                result.reason_code = "unsafe_mode_disabled"
                return result
            executable = executable.resolve()
            root = context.project_root.resolve()
            scan_workspace = context.temp_dir.resolve()
            if (has_link(context.project_root) or has_link(context.temp_dir) or not root.is_dir()
                    or scan_workspace != (context.config.scans_dir / context.scan_id).resolve()
                    or within(scan_workspace, root) or not scan_workspace.is_dir()):
                result.reason_code = "unsafe_mode_disabled"
                return result
            provider_root = scan_workspace / "providers"
            if has_link(provider_root):
                result.reason_code = "unsafe_mode_disabled"
                return result
            provider_root.mkdir(exist_ok=True)
            workspace = Path(tempfile.mkdtemp(prefix="scancode-", dir=provider_root))
            output = workspace / "result.json"
            env = controlled_environment(workspace, executable)

            def run(arguments, timeout, output_path=None):
                return self.runner.run(ProcessRequest(str(executable), tuple(arguments), timeout, workspace),
                                       env=env, max_stream_bytes=config.max_stream_bytes,
                                       output_path=output_path, max_output_bytes=config.max_json_bytes)

            probe = run(["--version"], config.probe_timeout_seconds)
            if probe.reason_code != "ok" or probe.exit_code != 0:
                result.status = ScanStatus.FAILED
                result.reason_code = probe.reason_code if probe.reason_code != "ok" else "execution_failed"
                return result
            found = re.search(rb"ScanCode version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.]+)?)\b", probe.stdout)
            release = version(found[1].decode("ascii")) if found else None
            result.version = release
            if not release or release.split(".")[0] != "32" or (config.scancode_version and release != config.scancode_version):
                result.reason_code = "unsupported_version"
                return result
            help_result = run(["--help"], config.probe_timeout_seconds)
            if help_result.reason_code != "ok" or help_result.exit_code != 0:
                result.status = ScanStatus.FAILED
                result.reason_code = help_result.reason_code if help_result.reason_code != "ok" else "execution_failed"
                return result
            if not all(flag.encode() in help_result.stdout for flag in REQUIRED_FLAGS):
                result.reason_code = "unsupported_version"
                return result
            completed = run(["--license", "--package", "--json", str(output), "--strip-root",
                             "--processes", "-1", "--timeout", "30", "--quiet", str(root)],
                            config.timeout_seconds, output)
            if completed.reason_code != "ok":
                result.status, result.reason_code = ScanStatus.FAILED, completed.reason_code
                return result
            if completed.exit_code not in (0, 1):
                result.status, result.reason_code = ScanStatus.FAILED, "execution_failed"
                return result
            result = ScanCodeResultParser().parse(read_json(output, config), config, release)
            if completed.exit_code == 1:
                note_partial(result, "execution_failed")
            return sanitize_result(result, context)
        except (InvalidProviderOutput, ValueError, TypeError, RecursionError):
            result.status, result.reason_code = ScanStatus.FAILED, "invalid_output"
            return result
        except Exception:
            result.status, result.reason_code = ScanStatus.FAILED, "execution_failed"
            return result
        finally:
            if workspace is not None:
                try:
                    if workspace.parent == context.temp_dir.resolve() / "providers" and not has_link(workspace):
                        shutil.rmtree(workspace)
                except OSError:
                    result.status, result.reason_code = ScanStatus.FAILED, "cleanup_failed"
