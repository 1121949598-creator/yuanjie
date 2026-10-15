"""Host-managed discovery is independent of the uploaded target and drive letter."""
import importlib.util
import os
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'run_web.py'
spec = importlib.util.spec_from_file_location('web_launcher_license', SCRIPT)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_missing_tool_keeps_license_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, '__file__', str(tmp_path / 'scripts' / 'run_web.py'))
    assert launcher.resolve_scancode_executable(None) is None


def test_local_tool_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, '__file__', str(tmp_path / 'scripts' / 'run_web.py'))
    relative = 'Scripts/scancode.exe' if os.name == 'nt' else 'bin/scancode'
    local = tmp_path / '.tools' / 'scancode-venv' / relative
    local.parent.mkdir(parents=True)
    local.touch()
    assert launcher.resolve_scancode_executable(None) == local


def test_explicit_tool_takes_precedence_even_if_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, '__file__', str(tmp_path / 'scripts' / 'run_web.py'))
    explicit = tmp_path / 'trusted-tool' / 'scancode.exe'
    assert launcher.resolve_scancode_executable(str(explicit)) == explicit.resolve()


def test_never_discover_uploaded_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, '__file__', str(tmp_path / 'scripts' / 'run_web.py'))
    uploaded = tmp_path / '.local-data' / 'scans' / 'example' / 'project' / 'scancode.exe'
    uploaded.parent.mkdir(parents=True)
    uploaded.touch()
    assert launcher.resolve_scancode_executable(None) is None
