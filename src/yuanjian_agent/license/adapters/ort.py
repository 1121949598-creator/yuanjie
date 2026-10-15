from pathlib import Path

from ...core.exceptions import ExternalToolUnavailable
from ...core.scanner import ScanStatus
from ..models import LicenseProviderResult
from .base import InvalidProviderOutput, has_link, read_json, sanitize_result, within
from .ort_parser import OrtResultParser


class OrtResultProvider:
    name = "ort"

    def __init__(self, runner=None) -> None:
        # Compatibility with the old adapter constructor; never invoke a runner.
        pass

    def collect(self, context):
        result = LicenseProviderResult(self.name)
        if not context.config.scanners.enable_ort:
            result.status, result.reason_code = ScanStatus.DISABLED, "disabled"
            return result
        configured = context.config.license_providers.ort_result_path
        if configured is None:
            return result
        try:
            path = Path(configured)
            if (not path.is_absolute() or has_link(path) or within(path.resolve(), context.project_root.resolve())):
                result.reason_code = "unsafe_mode_disabled"
                return result
            if not path.is_file():
                result.reason_code = "result_not_configured"
                return result
            data = read_json(path, context.config.license_providers)
            return sanitize_result(OrtResultParser().parse(data, context.config.license_providers), context)
        except (InvalidProviderOutput, ValueError, TypeError, RecursionError):
            result.status, result.reason_code = ScanStatus.FAILED, "invalid_output"
            return result
        except Exception:
            result.status, result.reason_code = ScanStatus.FAILED, "execution_failed"
            return result

    def scan(self, context):
        result = self.collect(context)
        if result.status not in {ScanStatus.SUCCESS, ScanStatus.PARTIAL}:
            raise ExternalToolUnavailable()
        return result.licenses


# Keep the installed import path and class role; no parallel ORT Analyzer runner.
OrtAdapter = OrtResultProvider
