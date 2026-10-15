import io
import math
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from yuanjian_agent.component_security import (
    ComponentSecurityPipeline,
    EvidenceConstrainedScorer,
)
from yuanjian_agent.config import Settings
from yuanjian_agent.files import iter_text_files
from yuanjian_agent.models import ScanLimits
from yuanjian_agent.web import create_app


FIXTURES = Path(__file__).parent / "fixtures" / "component_security_v1"


class Encoder:
    def __init__(self, cosine: float):
        self.cosine = cosine

    def encode(self, texts):
        return [[1.0, 0.0]] + [
            [self.cosine, math.sqrt(1 - self.cosine**2)] for _ in texts[1:]
        ]


def _files(name: str):
    files, _warnings = iter_text_files(FIXTURES / name, ScanLimits())
    return files


def _archive(name: str) -> bytes:
    content = io.BytesIO()
    root = FIXTURES / name
    with zipfile.ZipFile(content, "w") as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(root).as_posix())
    return content.getvalue()


def test_b_to_c_pipeline_creates_findings_only_for_inconsistent_relations():
    pipeline = ComponentSecurityPipeline(
        scorer=EvidenceConstrainedScorer(encoder=Encoder(0.1))
    )
    module, findings, warnings = pipeline.run(
        scan_id="integration-agent",
        scene="release_precheck",
        files=_files("fixture_b_faq"),
    )

    assert module["status"] == "success"
    assert module["summary"]["inconsistent"] == 2
    assert not warnings
    assert len(findings) == 2
    assert {finding.rule_id for finding in findings} == {
        "component.intent_capability_mismatch"
    }
    assert all(finding.evidence for finding in findings)


def test_fallback_is_visible_and_component_api_survives_restart(tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    client = TestClient(create_app(settings))
    created = client.post(
        "/api/scans",
        files={"file": ("faq-agent.zip", _archive("fixture_b_faq"), "application/zip")},
        data={"scene": "release_precheck"},
    )
    assert created.status_code == 201
    scan_id = created.json()["scan_id"]

    response = client.get(f"/api/scans/{scan_id}/component-security")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scene"] == "release_precheck"
    assert payload["status"] == "partial"
    assert payload["summary"]["components"] == 1
    assert all(
        not assessment["model"]["used"]
        for component in payload["components"]
        for assessment in component["result"]["assessments"]
    )

    reloaded = TestClient(create_app(settings))
    assert reloaded.get(f"/api/scans/{scan_id}/component-security").json() == payload


def test_invalid_scene_is_rejected_before_scan(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path / "state")))
    response = client.post(
        "/api/scans",
        files={"file": ("skill.zip", _archive("fixture_a_markdown"), "application/zip")},
        data={"scene": "unknown"},
    )
    assert response.status_code == 422
