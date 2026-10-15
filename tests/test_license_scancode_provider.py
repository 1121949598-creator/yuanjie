import json

import pytest

from yuanjian_agent.config import LicenseProviderSettings
from yuanjian_agent.core.scanner import ScanStatus
from yuanjian_agent.license.adapters.base import InvalidProviderOutput
from yuanjian_agent.license.adapters.scancode import ScanCodeAdapter, ScanCodeResultParser
from license_provider_support import SCANCODE, FakeExecutableRunner, context_for, safe_payload


def test_scancode_real_fake_process_normalizes_and_cleans_workspace(tmp_path, monkeypatch):
    context = context_for(tmp_path)
    for key in ("PYTHONPATH", "PYTHONHOME", "AWS_SECRET_ACCESS_KEY", "HTTP_PROXY", "SCANCODE_OPTIONS"):
        monkeypatch.setenv(key, "SyntheticToken9")
    runner = FakeExecutableRunner()
    result = ScanCodeAdapter(runner).collect(context)
    assert result.status == "success" and result.version == "32.4.1"
    assert result.execution_mode == "local-cli"
    assert {p.name for p in result.packages} == {"foo", "synthetic-gpl", "synthetic-unknown"}
    assert {p.license_expression for p in result.licenses} >= {"MIT", "GPL-3.0-only", None}
    detected = next(f for f in result.licenses if f.provenance[0].source_kind == "detected_license")
    assert detected.package.name == "foo" and detected.confidence == 1.0
    assert detected.evidence.source_span.start_line == 2
    assert detected.evidence.source_span.end_line == 8
    assert detected.evidence.details["source_scope"] == "package"
    assert result.dependencies[0].manifest_path == "requirements.txt"
    assert result.dependencies[0].requirement == "==1.0"
    assert len(runner.requests) == 3
    assert runner.requests[0].arguments == ("--version",)
    assert runner.requests[1].arguments == ("--help",)
    assert runner.requests[2].arguments[-1] == str(context.project_root.resolve())
    assert runner.requests[2].timeout_seconds == 5
    assert not list((context.temp_dir / "providers").iterdir())
    assert not (tmp_path / "target-executed").exists()
    safe_payload(result)


@pytest.mark.parametrize("mode,status,reason", [
    ("partial", "partial", "incomplete_output"),
    ("partial-exit", "partial", "incomplete_output"),
    ("invalid-json", "failed", "invalid_output"),
    ("oversize", "failed", None),
    ("timeout", "failed", "timeout"),
    ("probe-timeout", "failed", "timeout"),
    ("nonzero", "failed", "execution_failed"),
    ("no-output", "failed", "invalid_output"),
    ("stderr-limit", "failed", "output_limit"),
    ("stdout-limit", "failed", "output_limit"),
    ("unsupported-version", "unavailable", "unsupported_version"),
    ("bad-help", "unavailable", "unsupported_version"),
    ("header-mismatch", "failed", "invalid_output"),
])
def test_scancode_cli_failures_are_fixed_and_cleanup(mode, status, reason, tmp_path, caplog, capsys):
    context = context_for(tmp_path, timeout_seconds=0.4 if mode == "timeout" else 5,
                          probe_timeout_seconds=0.4 if mode == "probe-timeout" else 5)
    result = ScanCodeAdapter(FakeExecutableRunner(mode)).collect(context)
    assert result.status == status
    assert result.reason_code == reason if reason else result.reason_code in {"invalid_output", "output_limit"}
    assert not list((context.temp_dir / "providers").iterdir())
    safe_payload(result)
    captured = capsys.readouterr()
    assert "SyntheticToken9" not in caplog.text + captured.out + captured.err


def test_not_installed_does_not_invoke_runner(tmp_path, monkeypatch):
    context = context_for(tmp_path, scancode_executable=None)
    monkeypatch.setattr("yuanjian_agent.license.adapters.scancode.shutil.which", lambda *a, **k: None)
    runner = FakeExecutableRunner()
    result = ScanCodeAdapter(runner).collect(context)
    assert result.status == "unavailable" and result.reason_code == "binary_not_found"
    assert not runner.requests


def test_exact_version_pin(tmp_path):
    result = ScanCodeAdapter(FakeExecutableRunner()).collect(context_for(tmp_path, scancode_version="32.4.0"))
    assert result.reason_code == "unsupported_version"


@pytest.mark.parametrize("field,value", [("headers", []), ("files", {}), ("packages", {}), ("dependencies", {}), ("files", None)])
def test_scancode_root_collections_are_validated(field, value):
    data = json.loads(SCANCODE.read_text())
    data[field] = value
    with pytest.raises(InvalidProviderOutput):
        ScanCodeResultParser().parse(data, LicenseProviderSettings())


@pytest.mark.parametrize("change", ["wrong-tool", "wrong-version", "deep", "long", "many-files", "many-packages", "many-deps", "many-detections", "nan"])
def test_scancode_json_limits(change):
    data = json.loads(SCANCODE.read_text())
    limits = LicenseProviderSettings()
    if change == "wrong-tool": data["headers"][0]["tool_name"] = "other"
    if change == "wrong-version": data["headers"][0]["tool_version"] = "31.0.0"
    if change == "deep":
        value = {}
        for _ in range(45): value = {"x": value}
        data["ignored"] = value
    if change == "long": data["ignored"] = "x" * 20_000
    if change == "many-files": limits.max_files = 1
    if change == "many-packages": limits.max_packages = 1
    if change == "many-deps": data["dependencies"] *= 3; limits.max_dependencies = 1
    if change == "many-detections": data["files"][0]["license_detections"][0]["matches"] *= 3; limits.max_detections = 1
    if change == "nan": data["ignored"] = float("nan")
    with pytest.raises(InvalidProviderOutput):
        ScanCodeResultParser().parse(data, limits)


def test_one_invalid_record_keeps_valid_records():
    data = json.loads(SCANCODE.read_text())
    data["files"].append({"path": "../../outside", "license_detections": []})
    result = ScanCodeResultParser().parse(data, LicenseProviderSettings())
    assert result.status == ScanStatus.PARTIAL and result.packages
    assert "outside" not in safe_payload(result)
