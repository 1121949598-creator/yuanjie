import ast
from contextlib import closing
import gc
import json
from pathlib import Path
import sqlite3
import subprocess

from fastapi.testclient import TestClient
import pytest

from yuanjian_agent.config import LicenseProviderSettings, Settings
from yuanjian_agent.core.registry import ScannerRegistry
from yuanjian_agent.core.scanner import ScanStatus
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.license.adapters.base import InvalidProviderOutput, read_json
from yuanjian_agent.license.adapters.ort import OrtResultProvider
from yuanjian_agent.license.adapters.scancode import ScanCodeAdapter, ScanCodeResultParser
from yuanjian_agent.license.models import LicensePolicyDecision
from yuanjian_agent.license.policy import UnavailableLicensePolicy
from yuanjian_agent.license.scanner import LicenseScanner
from yuanjian_agent.models import Severity
from yuanjian_agent.secret.scanner import SecretScanner as SecretPipeline
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app
from license_provider_support import RAW, SCANCODE, FakeExecutableRunner, context_for, safe_payload


class ExplicitTestPolicy:
    """Only tests the existing normalization/storage contract; no license risk rule."""
    def evaluate(self, evidence):
        return [LicensePolicyDecision("test.upstream-projection", Severity.INFO, 0.8,
                                      "Synthetic upstream observation", ["Fixture contract"], ["Review fixture"])]


def configured_engine(context, scancode):
    engine = ScanEngine(context.config)
    registry = ScannerRegistry()
    registry.register(SecretPipeline(engine.secret_scanner))
    registry.register(LicenseScanner(ExplicitTestPolicy(), providers=(scancode, OrtResultProvider())))
    registry.register(engine.agent_scanner)
    engine.registry = registry
    return engine


def test_upstream_evidence_through_existing_engine_store_api_and_restart(tmp_path, caplog, capsys):
    context = context_for(tmp_path)
    engine = configured_engine(context, ScanCodeAdapter(FakeExecutableRunner()))
    result = engine.scan(context.project_root)
    assert result.findings and result.metadata["scanners"]["license"]["status"] == "success"
    assert {f.rule_id for f in result.findings} == {"test.upstream-projection"}
    boundaries = [safe_payload(result), engine.store.result_path(result.id).read_text(encoding="utf-8")]
    with closing(sqlite3.connect(context.config.database_path)) as db:
        boundaries.append(db.execute("SELECT result_json FROM scans WHERE id = ?", (result.id,)).fetchone()[0])
        boundaries.append(json.dumps(db.execute("SELECT * FROM findings WHERE scan_id = ?", (result.id,)).fetchall()))
    with TestClient(create_app(context.config)) as client:
        before = client.get(f"/api/scans/{result.id}").json()
        boundaries.append(json.dumps(before))
    scan_id = result.id
    del result, engine
    gc.collect()
    new_settings = Settings(data_dir=context.config.data_dir)
    restored = ScanStore(new_settings).get(scan_id)
    boundaries.append(safe_payload(restored))
    with TestClient(create_app(new_settings)) as client:
        after = client.get(f"/api/scans/{scan_id}").json()
        assert after == before
        boundaries.append(client.get(f"/api/scans/{scan_id}/findings").text)
    captured = capsys.readouterr()
    boundaries += [caplog.text, captured.out, captured.err]
    assert not any(raw in "\n".join(boundaries) for raw in RAW)
    assert not (tmp_path / "target-executed").exists()


@pytest.mark.parametrize("broken", ["scancode-timeout", "ort-corrupt", "provider-exception"])
def test_provider_failure_does_not_stop_other_modules(broken, tmp_path):
    context = context_for(tmp_path, timeout_seconds=0.4 if broken == "scancode-timeout" else 5)
    if broken == "ort-corrupt": context.config.license_providers.ort_result_path.write_text("corrupt SyntheticToken9")
    adapter = ScanCodeAdapter(FakeExecutableRunner("timeout" if broken == "scancode-timeout" else "normal"))
    if broken == "provider-exception":
        class Broken:
            name = "scancode"
            def collect(self, context): raise RuntimeError("SyntheticToken9")
        adapter = Broken()
    result = configured_engine(context, adapter).scan(context.project_root)
    states = result.metadata["scanners"]
    assert states["secret"]["status"] == states["agent_security"]["status"] == "success"
    assert states["license"]["status"] == "partial"
    assert result.findings
    safe_payload(result)


def test_no_policy_means_no_risk_findings_and_facts_are_still_available(tmp_path):
    context = context_for(tmp_path)
    scanner = LicenseScanner(UnavailableLicensePolicy(), providers=(ScanCodeAdapter(FakeExecutableRunner()), OrtResultProvider()))
    upstream = scanner.collect(context)
    assert all(r.status == "success" for r in upstream)
    assert all(r.licenses for r in upstream)
    output = scanner.scan(context)
    assert output.status == "unavailable" and output.findings == []
    assert set(output.providers.values()) == {ScanStatus.SUCCESS}
    assert any("version=32.4.1" in warning and "mode=local-cli" in warning for warning in output.warnings)


@pytest.mark.parametrize("mode", ["normal", "timeout"])
def test_runner_uses_explicit_shell_false_cwd_env_and_no_target_config(mode, tmp_path, monkeypatch):
    context = context_for(tmp_path, timeout_seconds=0.4 if mode == "timeout" else 5)
    (context.project_root / ".scancode.yml").write_text("command: setup.py\n")
    seen = []
    original = subprocess.Popen
    def observing(*args, **kwargs):
        seen.append((args, kwargs))
        return original(*args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", observing)
    result = ScanCodeAdapter(FakeExecutableRunner(mode)).collect(context)
    assert result.status == ("success" if mode == "normal" else "failed")
    assert len(seen) >= 3
    for args, kwargs in seen:
        assert isinstance(args[0], list) and kwargs["shell"] is False
        assert kwargs["cwd"].parent == context.temp_dir / "providers"
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["env"]["HOME"] == str(kwargs["cwd"])
        assert "--config-file" not in args[0]
    assert not (tmp_path / "target-executed").exists()


@pytest.mark.parametrize("bad", ["target-binary", "batch", "workspace", "binary-link", "ort-link"])
def test_host_boundary_rejects_unsafe_paths_without_execution(bad, tmp_path, monkeypatch):
    context = context_for(tmp_path)
    runner = FakeExecutableRunner()
    if bad == "target-binary":
        executable = context.project_root / "scancode.exe"
        executable.write_text("not executable")
        context.config.license_providers.scancode_executable = executable
    if bad == "batch":
        executable = tmp_path / "scancode.bat"
        executable.write_text("echo unsafe")
        context.config.license_providers.scancode_executable = executable
    if bad == "workspace": context.temp_dir = context.project_root
    if bad == "binary-link": monkeypatch.setattr("yuanjian_agent.license.adapters.scancode.has_link", lambda p: True)
    if bad == "ort-link":
        monkeypatch.setattr("yuanjian_agent.license.adapters.ort.has_link", lambda p: True)
        result = OrtResultProvider().collect(context)
    else: result = ScanCodeAdapter(runner).collect(context)
    assert result.reason_code == "unsafe_mode_disabled" and not runner.requests


@pytest.mark.parametrize("value", ["../secret", "/tmp/secret", "C:/secret", "\\\\server\\share", "a/%2e%2e/b", "git+https://u:pass@host/x", "safe?token=x", "safe\nname"])
def test_upstream_paths_cannot_escape_or_reveal_credentials(value):
    data = json.loads(SCANCODE.read_text())
    data["files"][0]["path"] = value
    result = ScanCodeResultParser().parse(data, LicenseProviderSettings())
    assert result.status == "partial"
    assert not any(f.evidence.details["source_kind"] == "detected_license" for f in result.licenses)
    safe_payload(result)


def test_purl_qualifiers_and_dependency_urls_are_withheld():
    data = json.loads(SCANCODE.read_text())
    data["dependencies"][0]["purl"] += "?repository_url=https://synthetic_user:SyntheticToken9@example.com"
    data["dependencies"][0]["extracted_requirement"] = "git+https://synthetic_user:SyntheticToken9@example.com/repo"
    result = ScanCodeResultParser().parse(data, LicenseProviderSettings())
    assert result.dependencies[0].package.purl == "pkg:pypi/foo@1.0"
    assert result.dependencies[0].requirement == "[withheld]"
    safe_payload(result)


@pytest.mark.parametrize("payload", ['{"x":1,"x":2}', '{"x":NaN}', '[1]', '{"x":Infinity}'])
def test_untrusted_json_rejects_duplicate_keys_nonfinite_and_nonobject(payload, tmp_path):
    path = tmp_path / "result.json"
    path.write_text(payload)
    with pytest.raises(InvalidProviderOutput): read_json(path, LicenseProviderSettings())


def test_external_process_access_is_confined_to_audited_license_runner():
    root = Path(__file__).parents[1] / "src" / "yuanjian_agent"
    callers = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                pytest.fail("No aliases may bypass the external process boundary")
            if isinstance(node, ast.Call) and ast.unparse(node.func).startswith("subprocess."):
                assert path == root / "license" / "adapters" / "process.py"
                if ast.unparse(node.func) == "subprocess.Popen": callers.append(node)
    assert len(callers) == 2
    assert all(any(k.arg == "shell" and isinstance(k.value, ast.Constant) and k.value.value is False
                   for k in call.keywords) for call in callers)


@pytest.mark.parametrize("provider", ["scancode", "ort"])
def test_expanded_evidence_is_bounded_before_deduplication(provider, monkeypatch):
    from importlib import import_module
    from license_provider_support import ORT

    module = import_module(f"yuanjian_agent.license.adapters.{provider}_parser")
    original = module.license_fact
    calls = []

    def observing(*args, **kwargs):
        calls.append(None)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "license_fact", observing)
    if provider == "scancode":
        data = json.loads(SCANCODE.read_text())
        data["packages"] = data["packages"][:2]
        for package in data["packages"]:
            package["datafile_paths"] = [f"path-{i}.txt" for i in range(4)]
        data["files"], data["dependencies"] = [], []
        parser = module.ScanCodeResultParser()
    else:
        data = json.loads(ORT.read_text())
        data["analyzer"]["result"]["packages"][0]["declared_licenses"] = ["MIT"] * 4
        parser = module.OrtResultParser()
    with pytest.raises(InvalidProviderOutput):
        parser.parse(data, LicenseProviderSettings(max_detections=5))
    assert len(calls) == 6
