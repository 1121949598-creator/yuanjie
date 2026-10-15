"""Profile behavior tests. Test encoders are not real-model evidence."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
import pytest

from yuanjian_agent.component_security import EvidenceConstrainedScorer
from yuanjian_agent.config import Settings, ScannerSettings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.models import FindingCategory
from yuanjian_agent.scan_profiles import resolve_profile
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app

ROOT = Path(__file__).parents[1]
AGENT = ROOT / "examples/01_langchain_research"
TOOL_FIXTURE = ROOT / "tests/fixtures/component_security_v1/fixture_b_faq"


class OrthogonalEncoder:
    def encode(self, texts):
        return [[1., 0.]] + [[0., 1.] for _ in texts[1:]]


def archive(root):
    data = BytesIO()
    with ZipFile(data, "w") as target:
        for source in sorted(root.rglob("*")):
            if source.is_file() and "__pycache__" not in source.parts:
                target.write(source, source.relative_to(root))
    return data.getvalue()


def forbidden(*args, **kwargs):
    pytest.fail("Unrequested scanner was invoked")


def test_project_skips_agent_and_semantic_scanners_but_detects_structure(tmp_path, monkeypatch):
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"))
    monkeypatch.setattr(engine.agent_scanner, "scan", forbidden)
    monkeypatch.setattr(engine.component_security, "run", forbidden)
    result = engine.scan(AGENT, profile="project")
    assert result.agents == result.tools == result.bindings == []
    assert result.summary.agent_security == 0
    assert result.metadata["scan_profile"]["agent_review_recommended"] is True
    assert result.metadata["scan_profile"]["requested_modules"] == ["secret", "license"]
    assert result.metadata["scan_profile"]["executed_modules"] == ["secret", "license"]
    assert result.metadata["scanners"]["agent_security"]["status"] == "disabled"
    assert result.metadata["module_data"]["component_security"]["status"] == "disabled"
    assert engine.settings.scanners.enable_agent is True


def test_download_has_capabilities_without_agent_scanner_or_agent_findings(tmp_path, monkeypatch):
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"),
                        component_scorer=EvidenceConstrainedScorer(encoder=OrthogonalEncoder()))
    monkeypatch.setattr(engine.agent_scanner, "scan", forbidden)
    monkeypatch.setattr(engine.component_security.adapter, "build_agents", forbidden)
    result = engine.scan(TOOL_FIXTURE, profile="download")
    module = result.metadata["module_data"]["component_security"]
    assert module["components"][0]["capabilities"]
    assert result.agents == result.tools == result.bindings == []
    assert result.metadata["scan_profile"]["scene"] == "install_precheck"
    assert result.metadata["scanners"]["agent_security"]["status"] == "disabled"
    assert not any(f.category == FindingCategory.AGENT_SECURITY for f in result.findings)
    assert any(f.category == FindingCategory.TOOL_CAPABILITY for f in result.findings)
    assert ScanStore(engine.settings).get(result.id).summary.tool_capabilities > 0


def test_agent_runs_specialized_checks_and_plans_do_not_leak(tmp_path):
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"))
    before = engine.scan(AGENT, profile="project")
    agent = engine.scan(AGENT, profile="agent")
    after = engine.scan(AGENT, profile="project")
    assert agent.agents and agent.tools and agent.bindings
    assert agent.summary.agent_security > 0
    assert "agent_security" in agent.metadata["scan_profile"]["executed_modules"]
    assert "component_security" in agent.metadata["scan_profile"]["executed_modules"]
    assert before.metadata["scan_profile"] == after.metadata["scan_profile"]
    assert before.agents == after.agents == []


def test_plain_main_and_readme_are_not_agents_and_source_is_not_executed(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    marker = tmp_path / "MUST_NOT_EXIST"
    (root / "README.md").write_text("# Plain formatter\nFormat text files only.\n")
    (root / "main.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"))
    project = engine.scan(root, profile="project")
    assert project.metadata["scan_profile"]["agent_review_recommended"] is False
    agent = engine.scan(root, profile="agent")
    assert agent.metadata["scanners"]["agent_security"]["status"] == "not_applicable"
    assert "agent_security" not in agent.metadata["scan_profile"]["executed_modules"]
    assert agent.metadata["module_data"]["component_security"]["status"] == "not_applicable"
    download = engine.scan(root, profile="download")
    assert download.metadata["module_data"]["component_security"]["components"][0]["component"]["component_type"] == "project"
    assert not marker.exists()


@pytest.mark.parametrize("name,text", [("main.py", "def invalid("), ("main.js", "runUntrustedCode();")])
def test_unparsed_code_is_not_a_successful_agent_assessment(tmp_path, name, text):
    root = tmp_path / "source"
    root.mkdir()
    (root / name).write_text(text)
    result = ScanEngine(Settings(data_dir=tmp_path / "state")).scan(root, profile="agent")
    assert result.metadata["scanners"]["agent_security"]["status"] == "partial"
    assert result.metadata["module_data"]["component_security"]["status"] == "partial"
    assert result.metadata["scan_profile"]["executed_modules"] == ["secret", "license"]
    assert result.status == "partial"


def test_profile_cannot_enable_host_disabled_checks(tmp_path):
    settings = Settings(data_dir=tmp_path / "state", scanners=ScannerSettings(enable_agent=False))
    result = ScanEngine(settings).scan(AGENT, profile="agent")
    assert result.metadata["scanners"]["agent_security"]["status"] == "disabled"
    assert result.metadata["module_data"]["component_security"]["status"] == "disabled"
    assert "component_security" not in result.metadata["scan_profile"]["executed_modules"]


@pytest.mark.parametrize("profile,scene", [("unknown", None), ("download", "release_precheck"), (None, "invalid")])
def test_invalid_plan_rejected_before_scanning(profile, scene):
    with pytest.raises(ValueError):
        resolve_profile(profile, scene)


def test_profile_persists_in_report_history_reopen_and_rescan(tmp_path):
    settings = Settings(data_dir=tmp_path / "state", demo_mode=False)
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/scans", files={"file": ("example.zip", archive(AGENT))}, data={"profile": "project"})
        assert created.status_code == 201
        scan_id = created.json()["scan_id"]
        report = client.get(f"/api/scans/{scan_id}/report").json()
        expected = report["metadata"]["scan_profile"]
        assert expected["id"] == "project"
        assert not report["agents"]
        agent_module = client.get(f"/api/scans/{scan_id}/agent-security").json()["module_data"]
        assert all(agent_module["features"][key] == "disabled" for key in (
            "agent_discovery", "tool_discovery", "binding_analysis", "risk_analysis"))
        assert client.get("/api/scans").json()["items"][0]["scan_profile"] == expected
        rescanned = client.post(f"/api/scans/{scan_id}/rescan")
        assert rescanned.status_code == 200
        assert rescanned.json()["metadata"]["scan_profile"]["id"] == "project"
    with TestClient(create_app(settings)) as reopened:
        assert reopened.get(f"/api/scans/{scan_id}/report").json() == report


def test_web_rejects_untrusted_plan_and_scene_conflict_before_creating_records(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path / "state"))) as client:
        for data in ({"profile": "arbitrary"}, {"profile": "download", "scene": "release_precheck"}):
            response = client.post("/api/scans", files={"file": ("sample.zip", archive(AGENT))}, data=data)
            assert response.status_code == 422
        assert client.get("/api/scans").json()["items"] == []


def test_old_callers_keep_comprehensive_behavior_without_fake_new_profile(tmp_path):
    result = ScanEngine(Settings(data_dir=tmp_path / "state")).scan(AGENT)
    assert result.agents
    assert "scan_profile" not in result.metadata
