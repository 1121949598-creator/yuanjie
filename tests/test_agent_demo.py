import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from yuanjian_agent.agent_security.demo import DemoFeatureUnavailable
from yuanjian_agent.cli import main
from yuanjian_agent.config import ScannerSettings, Settings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.repair import RepairService
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app


EXAMPLES = Path(__file__).parents[1] / "examples"


def archive_sample(name):
    data = BytesIO()
    root = EXAMPLES / name
    with ZipFile(data, "w") as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    return data.getvalue()


@pytest.mark.parametrize(
    "sample,counts",
    [
        ("03_crewai_mail", (1, 1, 1, 0, 0)),
        ("01_langchain_research", (1, 2, 2, 1, 0)),
        ("05_mcp_static", (2, 2, 2, 1, 1)),
        ("06_dynamic_unresolved", (1, 0, 1, 1, 1)),
    ],
)
def test_demo_zip_store_overview_and_reload(tmp_path, sample, counts):
    settings = Settings(data_dir=tmp_path / "state", demo_mode=True)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/scans", files={"file": ("sample.zip", archive_sample(sample), "application/zip")})
        assert response.status_code == 201
        assert response.json()["status"] == "completed"
        scan_id = response.json()["scan_id"]
        complete = client.get(f"/api/scans/{scan_id}").json()
        response = client.get(f"/api/scans/{scan_id}/agent-security")
        assert response.status_code == 200
        payload = response.json()
        assert set(payload) == {
            "scan_id", "status", "module_data", "rules_version", "scoring_model",
            "execution_policy", "agents", "tools", "bindings", "findings", "warnings",
        }
        observed = tuple(len(payload[key]) for key in ("agents", "tools", "bindings", "findings"))
        assert observed + (payload["module_data"]["unresolved_bindings"],) == counts
        assert payload["status"]["status"] == "success"
        assert complete["metadata"]["scanners"]["secret"]["status"] == "success"
        assert complete["metadata"]["scanners"]["license"]["status"] == "unavailable"
        assert payload["module_data"]["mode"] == "demo"
        assert payload["execution_policy"] == "static-only-never-execute-target"
        assert payload["rules_version"] == "2026.09.13"
        assert payload["module_data"]["features"]["repair"] == "disabled"
        assert payload["module_data"]["features"]["repair_preview"] == "disabled"
        assert payload["module_data"]["features"]["rescan"] == "disabled"
        assert payload["module_data"]["features"]["risk_analysis"] == "enabled"
        if sample == "01_langchain_research":
            finding = payload["findings"][0]
            assert finding["severity"] in {"high", "critical"}
            assert finding["rule_id"] == "agent.task-tool-overexposure"
            assert finding["rationale"]
            assert {e["details"]["evidence_kind"] for e in finding["evidence"]} == {"implementation", "registration"}
            assert all(e["source_span"]["start_line"] >= 1 for e in finding["evidence"])
        for binding in payload["bindings"]:
            assert any(a["id"] == binding["agent_id"] for a in payload["agents"])
            assert binding["tool_id"] is None or any(t["id"] == binding["tool_id"] for t in payload["tools"])
        assert client.get(f"/api/scans/{scan_id}/secrets").status_code == 200
        assert client.get(f"/api/scans/{scan_id}/licenses").status_code == 200
        assert client.get(f"/scans/{scan_id}/licenses").status_code == 200
        page = client.get(f"/scans/{scan_id}").text
        assert f'href="/scans/{scan_id}/licenses"' in page
        assert f'/scans/{scan_id}/repair' not in page
        assert f'/scans/{scan_id}/rescan' not in page
        assert "Demo 模式" in page
    saved = ScanStore(settings).get(scan_id)
    assert saved.to_dict() == complete
    with TestClient(create_app(settings)) as reloaded:
        assert reloaded.get(f"/api/scans/{scan_id}/agent-security").json() == payload


@pytest.mark.parametrize(
    "method,path,feature",
    [
        ("POST", "/scans/missing/repair", "repair"),
        ("GET", "/scans/missing/repair", "repair_preview"),
        ("POST", "/scans/missing/rescan", "rescan"),
        ("GET", "/scans/missing/comparison", "rescan"),
        ("POST", "/api/scans/missing/rescan", "rescan"),
        ("POST", "/api/findings/missing/repair-preview?scan_id=missing", "repair_preview"),
    ],
)
def test_demo_blocks_direct_routes_before_reading_or_editing(tmp_path, monkeypatch, method, path, feature):
    def forbidden(*args, **kwargs):
        pytest.fail("Disabled route reached persistence or repair implementation")
    client = TestClient(create_app(Settings(data_dir=tmp_path / "state", demo_mode=True)))
    monkeypatch.setattr(ScanStore, "get", forbidden)
    monkeypatch.setattr(RepairService, "preview", forbidden)
    monkeypatch.setattr(RepairService, "create_safe_copy", forbidden)
    response = client.request(method, path)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "demo_feature_disabled"
    assert response.json()["detail"]["feature"] == feature


@pytest.mark.parametrize("method,feature", [("preview", "repair_preview"), ("create_safe_copy", "repair")])
def test_demo_service_cannot_bypass_boundary(tmp_path, method, feature):
    engine = ScanEngine(Settings(data_dir=tmp_path / "state", demo_mode=True))
    # A null result proves the guard precedes result access and source reads.
    with pytest.raises(DemoFeatureUnavailable) as raised:
        getattr(RepairService(engine.settings, engine.secret_scanner), method)(None)
    assert raised.value.feature == feature
    assert not list(engine.settings.scans_dir.iterdir())


@pytest.mark.parametrize("command", ["repair", "rescan"])
def test_demo_cli_rejects_unsafe_commands_without_state_changes(tmp_path, capsys, command):
    state = tmp_path / "state"
    assert main(["--demo", "--data-dir", str(state), command, "missing"]) == 2
    assert "disabled in Demo mode" in capsys.readouterr().err
    assert not state.exists()


def test_demo_cli_scan_persists_policy(tmp_path, capsys):
    state = tmp_path / "state"
    assert main(["--demo", "--data-dir", str(state), "scan", str(EXAMPLES / "01_langchain_research")]) == 0
    result = json.loads(capsys.readouterr().out)
    saved = ScanStore(Settings(data_dir=state)).get(result["scan_id"])
    assert saved.metadata["module_data"]["agent_security"]["features"]["repair"] == "disabled"


def test_demo_preview_blocks_synthetic_secret_in_diff_context(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    raw = "sk-proj-" + "OnlySyntheticDemoFreeze9274AbCdEfGhIjKlMnOpQrSt" * 2
    source = (
        '@tool\ndef shell_exec(command):\n    """Execute arbitrary shell commands."""\n'
        '    return subprocess.run(command, shell=True)\n'
        f'api_key = "{raw}"\n'
        'agent = create_agent("m", tools=[shell_exec], system_prompt="Summarize papers")\n'
    )
    (project / "agent.py").write_text(source, encoding="utf-8")
    settings = Settings(data_dir=tmp_path / "state", demo_mode=True)
    result = ScanEngine(settings).scan(project)
    assert result.summary.secrets == 1
    finding = next(f for f in result.findings if f.category.value == "tool_exposure")
    client = TestClient(create_app(settings))
    response = client.post(f"/api/findings/{finding.id}/repair-preview", params={"scan_id": result.id})
    assert response.status_code == 409
    assert raw not in response.text
    assert raw not in client.get(f"/api/scans/{result.id}/agent-security").text
    assert raw not in client.get(f"/api/scans/{result.id}").text
    assert not (settings.scans_dir / result.id / "safe_copy").exists()
    assert (project / "agent.py").read_text(encoding="utf-8") == source


def test_demo_serving_policy_overrides_old_scan_without_mutating_store(tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    result = ScanEngine(settings).scan(EXAMPLES / "01_langchain_research")
    before = ScanStore(settings).get(result.id).to_dict()
    settings.demo_mode = True
    client = TestClient(create_app(settings))
    overview = client.get(f"/api/scans/{result.id}/agent-security").json()
    assert overview["module_data"]["mode"] == "demo"
    assert overview["module_data"]["features"]["rescan"] == "disabled"
    generic = client.get(f"/api/scans/{result.id}").json()
    assert generic["metadata"]["module_data"]["agent_security"]["features"] == overview["module_data"]["features"]
    assert ScanStore(settings).get(result.id).to_dict() == before


def test_demo_surfaces_parse_warning_without_claiming_full_coverage(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "agent.py").write_text("agent = create_agent(\n", encoding="utf-8")
    settings = Settings(data_dir=tmp_path / "state", demo_mode=True)
    result = ScanEngine(settings).scan(project)
    payload = TestClient(create_app(settings)).get(f"/api/scans/{result.id}/agent-security").json()
    assert any("Python syntax error" in warning for warning in payload["warnings"])
    assert payload["module_data"]["features"]["rescan"] == "disabled"


def test_demo_secret_fixture_remains_masked_and_queryable(tmp_path):
    settings = Settings(data_dir=tmp_path / "state", demo_mode=True)
    result = ScanEngine(settings).scan(EXAMPLES / "02_secret_project")
    assert result.summary.secrets == 2
    client = TestClient(create_app(settings))
    response = client.get(f"/api/scans/{result.id}/secrets")
    assert response.status_code == 200
    assert "sk-liveDemoOnly_1234567890abcdef" not in response.text


def test_demo_disabled_agent_status_and_missing_scan(tmp_path):
    settings = Settings(data_dir=tmp_path / "state", demo_mode=True, scanners=ScannerSettings(enable_agent=False))
    result = ScanEngine(settings).scan(EXAMPLES / "01_langchain_research")
    client = TestClient(create_app(settings))
    payload = client.get(f"/api/scans/{result.id}/agent-security").json()
    assert payload["status"]["status"] == "disabled"
    assert payload["agents"] == payload["tools"] == payload["bindings"] == payload["findings"] == []
    assert payload["module_data"]["features"]["agent_discovery"] == "disabled"
    assert client.get("/api/scans/missing/agent-security").status_code == 404
