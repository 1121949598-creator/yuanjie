from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys

from yuanjian_agent.config import LicenseProviderSettings, ScannerSettings, Settings
from yuanjian_agent.core.context import ScanContext
from yuanjian_agent.files import iter_text_files
from yuanjian_agent.license.adapters.process import ScanCodeProcessRunner


FIXTURES = Path(__file__).parent / "fixtures"
SCANCODE = FIXTURES / "scancode" / "minimal.json"
ORT = FIXTURES / "ort" / "minimal.json"
RAW = ("RAW-UPSTREAM-TEXT-DO-NOT-PERSIST", "SyntheticToken9", "synthetic_user", "git+https://")


class FakeExecutableRunner(ScanCodeProcessRunner):
    """Exercise the real bounded runner with a portable synthetic executable.

    Only the trusted launcher changes: Python -I -S fake_cli.py on Windows/Unix.
    No production configuration accepts arbitrary prefix arguments.
    """

    def __init__(self, mode="normal"):
        self.mode = mode
        self.requests = []

    def command(self, request):
        self.requests.append(request)
        return [sys.executable, "-I", "-S", str(FIXTURES / "scancode" / "fake_scancode.py"),
                str(SCANCODE), self.mode, *request.arguments]


def context_for(tmp_path, **overrides):
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    for name in ("requirements.txt", "pyproject.toml", "LICENSE"):
        (project / name).write_text("# synthetic text only\n", encoding="utf-8")
    marker = tmp_path / "target-executed"
    (project / "setup.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
    (project / "script.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
    (project / "Makefile").write_text(f'all:\n\t"{sys.executable}" "{project / "script.py"}"\n', encoding="utf-8")
    trusted = tmp_path / "trusted-ort.json"
    shutil.copyfile(ORT, trusted)
    config = LicenseProviderSettings(scancode_executable=Path(sys.executable), ort_result_path=trusted,
                                     timeout_seconds=5, probe_timeout_seconds=5,
                                     max_json_bytes=100_000, max_stream_bytes=100_000)
    for name, value in overrides.items():
        setattr(config, name, value)
    settings = Settings(data_dir=tmp_path / "state", scanners=ScannerSettings(enable_scancode=True, enable_ort=True),
                        license_providers=config)
    settings.ensure_directories()
    workspace = settings.scans_dir / "fixture-scan"
    workspace.mkdir(exist_ok=True)
    files, _ = iter_text_files(project, settings.limits)
    return ScanContext("fixture-scan", project, "directory", settings, workspace, files=files)


def safe_payload(value):
    text = json.dumps(asdict(value), ensure_ascii=False)
    assert not any(raw in text for raw in RAW)
    return text
