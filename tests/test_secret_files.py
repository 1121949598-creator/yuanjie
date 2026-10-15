"""File-policy tests exercise the shared reader used by ScanEngine."""
import io
import json
from pathlib import Path

import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.files import IGNORED_DIRS, iter_text_files
from yuanjian_agent.models import ScanLimits


RAW = "sk-test-8KJd82kdlQ93kdl20f"


@pytest.mark.parametrize("name", ["code.py", "code.js", "code.jsx", "code.ts", "code.tsx",
    "code.java", "code.go", "code.rs", ".env", ".env.production", "config.yaml",
    "settings.yml", "config.json", "secrets.toml", "config.ini", "config.conf",
    "application.properties", "code.sh", "script.bash", "bash", "docker-compose.yml",
    "docker-compose.yaml", "key.pem", "id_ed25519"])
def test_required_source_and_configuration_files(tmp_path, name):
    (tmp_path / name).write_text(f'API_KEY="{RAW}"', encoding="utf-8")
    files, warnings = iter_text_files(tmp_path, ScanLimits())
    assert [f.relative_path for f in files] == [name]
    assert not warnings


def test_skip_binary_file(tmp_path):
    (tmp_path / "binary.py").write_bytes(b"\x00API_KEY=synthetic")
    files, warnings = iter_text_files(tmp_path, ScanLimits())
    assert not files and any("binary" in warning for warning in warnings)


@pytest.mark.parametrize("suffix", [".png", ".mp4", ".pt", ".zip", ".sqlite", ".unknown"])
def test_skip_unsupported_file(tmp_path, suffix):
    (tmp_path / ("file" + suffix)).write_text(f'API_KEY="{RAW}"', encoding="utf-8")
    files, warnings = iter_text_files(tmp_path, ScanLimits())
    assert not files and not warnings


def test_skip_large_file(tmp_path):
    (tmp_path / "huge.py").write_text("x" * 65, encoding="utf-8")
    files, warnings = iter_text_files(tmp_path, ScanLimits(max_file_bytes=64))
    assert not files and any("oversized" in warning for warning in warnings)


def test_skip_ignored_directories(tmp_path):
    for directory in IGNORED_DIRS:
        target = tmp_path / directory
        target.mkdir()
        (target / "config.py").write_text(f'API_KEY="{RAW}"', encoding="utf-8")
    files, _ = iter_text_files(tmp_path, ScanLimits())
    assert not files


def test_actual_read_is_bounded_if_file_grows(tmp_path, monkeypatch):
    target = tmp_path / "config.py"
    target.write_text("small", encoding="utf-8")
    original = Path.open
    read_sizes = []

    class GrowingStream(io.BytesIO):
        def read(self, size=-1):
            read_sizes.append(size)
            return super().read(size)

    def opened(path, mode="r", *args, **kwargs):
        if path == target and mode == "rb":
            return GrowingStream(b"x" * 1000)
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    files, warnings = iter_text_files(tmp_path, ScanLimits(max_file_bytes=64))
    assert read_sizes == [65]
    assert not files and warnings


@pytest.mark.parametrize("error_type", [PermissionError, FileNotFoundError, UnicodeDecodeError])
def test_unreadable_file_does_not_break_engine_or_leak_diagnostic(tmp_path, monkeypatch, caplog, error_type):
    project = tmp_path / "input"
    project.mkdir()
    bad = project / "bad.py"
    bad.write_text("bad", encoding="utf-8")
    (project / "good.py").write_text(f'API_KEY="{RAW}"', encoding="utf-8")
    original = Path.open

    def opened(path, mode="r", *args, **kwargs):
        if path == bad and mode == "rb":
            if error_type is UnicodeDecodeError:
                raise UnicodeDecodeError("utf8", RAW.encode(), 0, 1, RAW)
            raise error_type(RAW)
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"))
    result = engine.scan(project)
    assert result.summary.secrets == 1
    assert result.metadata["scanners"]["agent_security"]["status"] == "success"
    assert any("Could not read" in warning for warning in result.warnings)
    assert RAW not in json.dumps(result.to_dict()) + caplog.text
