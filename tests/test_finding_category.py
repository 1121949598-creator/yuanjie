from dataclasses import asdict
import json

import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.engine import _summary
from yuanjian_agent.license.models import LicenseEvidence, LicensePolicyDecision, PackageEvidence, DependencyEvidence
from yuanjian_agent.license.normalizer import normalize_license
from yuanjian_agent.models import Evidence, Finding, FindingCategory, ScanResult, Severity, SourceSpan
from yuanjian_agent.reporting import render_html_report
from yuanjian_agent.serialization import scan_result_from_dict
from yuanjian_agent.storage import ScanStore


@pytest.mark.parametrize("category", list(FindingCategory))
def test_every_category_roundtrips_sqlite_json_and_report(category, tmp_path):
    finding = Finding(
        "f", "sig", category, "test.contract", Severity.LOW, 0.5,
        "Contract fixture", [Evidence(SourceSpan("manifest.txt", 1, 1), "safe")], [], [],
        source="test-provider",
    )
    result = ScanResult("scan", "project", str(tmp_path), "2026-09-09", "completed", "1", findings=[finding])
    result.summary = _summary(result.findings)
    store = ScanStore(Settings(data_dir=tmp_path / "state"))
    store.save(result)
    restored = store.get(result.id)
    assert asdict(restored) == asdict(result)
    assert restored.findings[0].location.path == "manifest.txt"
    assert category.value in render_html_report(restored)
    with store._connect() as connection:
        assert connection.execute("SELECT category FROM findings").fetchone()[0] == category.value


def test_old_payload_and_summary_need_no_migration(tmp_path):
    finding = Finding("f", "sig", FindingCategory.TOOL_EXPOSURE, "agent.rule", Severity.LOW, 0.5, "Old", [], [], [])
    payload = ScanResult("old", "project", "source", "date", "completed", "1", findings=[finding]).to_dict()
    del payload["findings"][0]["source"]
    del payload["findings"][0]["fingerprint"]
    del payload["summary"]["licenses"]
    del payload["summary"]["agent_security"]
    store = ScanStore(Settings(data_dir=tmp_path))
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO scans VALUES (?, ?, ?, ?, ?, ?)",
            ("old", "project", "date", "completed", None, json.dumps(payload)),
        )
    restored = store.get("old")
    assert restored.findings[0].category == FindingCategory.TOOL_EXPOSURE
    assert restored.findings[0].fingerprint == "sig"
    assert restored.findings[0].source == "builtin"
    assert restored.summary.licenses == 0
    assert scan_result_from_dict(payload).findings == restored.findings


def test_license_normalizer_maps_explicit_decision_without_legal_rules():
    package = PackageEvidence("synthetic-package", "1.0")
    evidence = LicenseEvidence(
        Evidence(SourceSpan("LICENSE", 1, 2), "fixture only"), "test-provider",
        package=package, dependencies=[DependencyEvidence("pyproject.toml", package)],
    )
    decision = LicensePolicyDecision("test.manual-review", Severity.INFO, 1.0, "Fixture review", ["Fixture"], [])
    finding = normalize_license(evidence, decision)
    assert finding.category == FindingCategory.LICENSE
    assert finding.source == "test-provider"
    assert finding.metadata["dependencies"][0]["manifest_path"] == "pyproject.toml"
    assert finding.metadata["package"]["name"] == package.name
