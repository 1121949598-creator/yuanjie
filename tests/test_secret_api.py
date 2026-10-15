"""HTTP contracts consume saved synthetic results; no query invokes a scanner."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from test_secret_query import finding, scan
from yuanjian_agent.config import Settings
from yuanjian_agent.core.scanner import ScanStatus
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.models import Evidence, FindingCategory, Severity, SourceSpan
from yuanjian_agent.secret.query import TYPE_BY_RULE
from yuanjian_agent.secrets import SecretScanner
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app


RAW = "sk-test-8KJd82kdlQ93kdl20f"
BASE = "/api/scans/scan-a/secrets"


@pytest.fixture
def api(tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    store = ScanStore(settings)
    rows = [
        finding("private", Severity.CRITICAL, "private_key", "key.pem", confidence=0.95),
        finding("aws", Severity.HIGH, "aws_access_key", ".env", confidence=0.9),
        finding("api-a", Severity.HIGH, "api_key", "config.py", 3),
        finding("api-b", Severity.HIGH, "api_key", "src/client.py", 7),
        finding("password", Severity.MEDIUM, "password", "settings.py", confidence=0.7),
        finding("jwt", Severity.MEDIUM, "jwt", "auth.py", confidence=0.65),
        finding("token", Severity.LOW, "token", "token.txt", confidence=0.4),
        finding("info", Severity.INFO, "future_type", "notes.txt", confidence=0.2),
        finding("not-secret", category=FindingCategory.LICENSE),
    ]
    for row in rows:
        row.rule_id = next((rule for rule, kind in TYPE_BY_RULE.items()
                            if kind == row.metadata["secret_type"]), "future.rule")
    rows[2].evidence.append(Evidence(SourceSpan("nested/secondary.conf", 12, 14, 2, 5), "****",
                                    {"masked_value": "****"}))
    saved = scan(findings=rows)
    store.save(saved)
    client = TestClient(create_app(settings))
    return client, store, saved


def test_secret_overview(api):
    response = api[0].get(BASE)
    assert response.status_code == 200
    result = response.json()
    assert result["scan_id"] == "scan-a" and result["module"] == "secret"
    assert result["status"] == "success" and result["scan_status"] == "completed"
    assert len(result["items"]) == 8
    assert result["items"][0]["finding_id"] == "private"
    assert set(result["items"][0]) == {
        "finding_id", "rule_id", "secret_type", "severity", "confidence", "message",
        "location", "masked_value", "occurrence_count",
    }


def test_secret_overview_empty(api):
    api[1].save(scan("empty"))
    result = api[0].get("/api/scans/empty/secrets").json()
    assert result["items"] == [] and result["by_type"] == {}
    assert result["summary"] == dict(total=0, critical=0, high=0, medium=0, low=0, info=0)
    assert result["pagination"]["total"] == 0


def test_secret_overview_summary(api):
    result = api[0].get(BASE).json()
    assert result["summary"] == dict(total=8, critical=1, high=3, medium=2, low=1, info=1)


def test_secret_overview_group_by_type(api):
    result = api[0].get(BASE).json()
    assert result["by_type"] == {
        "private_key": 1, "aws_access_key": 1, "api_key": 2, "password": 1,
        "jwt": 1, "token": 1, "future_type": 1,
    }


def test_secret_overview_pagination(api):
    result = api[0].get(BASE, params={"page": 2, "page_size": 3}).json()
    assert result["pagination"] == {"page": 2, "page_size": 3, "total": 8}
    assert [item["finding_id"] for item in result["items"]] == ["api-b", "password", "jwt"]
    assert api[0].get(BASE, params={"page": 99}).json()["items"] == []


def test_secret_overview_filter_severity(api):
    result = api[0].get(BASE, params={"severity": "high"}).json()
    assert result["pagination"]["total"] == 3
    assert all(item["severity"] == "high" for item in result["items"])
    assert result["summary"]["total"] == 8


def test_secret_overview_filter_secret_type(api):
    result = api[0].get(BASE, params={"secret_type": "api_key"}).json()
    assert result["pagination"]["total"] == 2
    assert all(item["secret_type"] == "api_key" for item in result["items"])


def test_secret_overview_filter_file_path(api):
    result = api[0].get(BASE, params={"file_path": "SECONDARY"}).json()
    assert [item["finding_id"] for item in result["items"]] == ["api-a"]


def test_secret_overview_combined_filters(api):
    result = api[0].get(BASE, params={
        "severity": "high", "secret_type": "api_key", "file_path": "src", "min_confidence": 0.8,
    }).json()
    assert [item["finding_id"] for item in result["items"]] == ["api-b"]
    assert api[0].get(BASE, params={"min_confidence": 0.99}).json()["items"] == []
    assert api[0].get(BASE, params={"rule_id": "secret.jwt"}).json()["items"][0]["finding_id"] == "jwt"


def test_secret_overview_stable_sort(api):
    expected = ["private", "aws", "api-a", "api-b", "password", "jwt", "token", "info"]
    first = api[0].get(BASE).json()
    second = api[0].get(BASE).json()
    assert [item["finding_id"] for item in first["items"]] == expected
    assert first == second


def test_secret_detail(api):
    response = api[0].get(BASE + "/api-a")
    assert response.status_code == 200
    detail = response.json()
    assert detail["finding_id"] == "api-a" and detail["scan_id"] == "scan-a"
    assert detail["secret_type"] == "api_key"
    assert detail["occurrence_count"] == 2
    assert len(detail["evidence"]) == 2


@pytest.mark.parametrize("identifier", ["missing", "not-secret"])
def test_secret_detail_not_found(api, identifier):
    response = api[0].get(BASE + "/" + identifier)
    assert response.status_code == 404
    assert response.json() == {"detail": "Secret finding not found in this scan"}


def test_secret_detail_does_not_belong_to_scan(api):
    api[1].save(scan("scan-b", [finding("only-b")]))
    assert api[0].get(BASE + "/only-b").status_code == 404
    assert api[0].get("/api/scans/scan-b/secrets/only-b").status_code == 200


def test_secret_detail_same_id_in_distinct_scans(api):
    api[1].save(scan("scan-b", [finding("api-a", path="b.py")]))
    assert api[0].get(BASE + "/api-a").json()["location"]["file_path"] == "config.py"
    assert api[0].get("/api/scans/scan-b/secrets/api-a").json()["location"]["file_path"] == "b.py"


def test_secret_detail_location(api):
    detail = api[0].get(BASE + "/api-a").json()
    assert detail["location"] == {
        "file_path": "config.py", "line": 3, "end_line": 3, "column_start": 10, "column_end": 30,
    }
    assert detail["evidence"][1]["location"]["end_line"] == 14


def test_secret_detail_remediation(api):
    detail = api[0].get(BASE + "/api-a").json()
    assert detail["remediation"]["title"] == "Rotate the exposed API key"
    assert len(detail["remediation"]["steps"]) == 3


def test_secret_detail_unknown_type_has_fallback(api):
    result = api[0].get(BASE + "/info").json()
    assert result["secret_type"] == "future_type"
    assert result["remediation"]["title"] == "Review and replace the exposed credential"


@pytest.mark.parametrize("suffix", ["", "/finding"])
def test_secret_overview_scan_not_found(api, suffix):
    response = api[0].get("/api/scans/missing/secrets" + suffix)
    assert response.status_code == 404 and response.json() == {"detail": "Scan not found"}


def test_secret_overview_partial_module(api):
    saved = api[2]
    saved.status = "partial"
    saved.metadata["scanners"]["secret"]["status"] = "partial"
    saved.warnings = [RAW]
    api[1].save(saved)
    response = api[0].get(BASE)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "partial" and result["summary"]["total"] == 8
    assert result["diagnostics"] and RAW not in response.text


@pytest.mark.parametrize("status", ["disabled", "unavailable", "failed"])
def test_secret_overview_disabled_module(api, status):
    api[1].save(scan("state", module_status=status))
    result = api[0].get("/api/scans/state/secrets").json()
    assert result["status"] == status and result["items"] == []
    assert result["diagnostics"]


@pytest.mark.parametrize("status", list(ScanStatus))
def test_secret_detail_module_status_does_not_drop_available_result(api, status):
    api[1].save(scan("state", [finding("saved")], module_status=status))
    response = api[0].get("/api/scans/state/secrets/saved")
    assert response.status_code == 200 and response.json()["status"] == status


@pytest.mark.parametrize("state", ["pending", "running", "queued"])
@pytest.mark.parametrize("suffix", ["", "/saved"])
def test_secret_api_unfinished_scan_returns_conflict(api, state, suffix):
    api[1].save(scan("unfinished", [finding("saved")], status=state))
    response = api[0].get("/api/scans/unfinished/secrets" + suffix)
    assert response.status_code == 409 and response.json() == {"detail": "Scan results are not final"}


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page_size": 101}, {"page_size": 0}, {"severity": RAW},
    {"page": RAW}, {"min_confidence": RAW}, {"min_confidence": "nan"},
    {"min_confidence": 1.1}, {"file_path": ""}, {"secret_type": " "},
    {"sort": "severity; DROP TABLE findings;"}, {"unrecognized": RAW},
])
def test_secret_api_invalid_parameters_are_safe(api, params, caplog):
    response = api[0].get(BASE, params=params)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid Secret query parameters"}
    assert RAW not in response.text + caplog.text


def test_secret_api_rejects_repeated_query_parameters(api):
    response = api[0].get(BASE, params=[("page", "1"), ("page", RAW)])
    assert response.status_code == 422 and RAW not in response.text


def test_secret_query_input_is_not_sql(api):
    response = api[0].get(BASE, params={"file_path": "' OR 1=1 --"})
    assert response.status_code == 200 and response.json()["pagination"]["total"] == 0
    assert api[0].get(BASE).json()["summary"]["total"] == 8


@pytest.mark.parametrize("suffix", ["", "/api-a"])
def test_secret_api_persistence_errors_are_safe(api, monkeypatch, suffix, caplog, capsys):
    def fail(*args):
        raise sqlite3.OperationalError(RAW)
    monkeypatch.setattr(ScanStore, "get", fail)
    response = api[0].get(BASE + suffix)
    assert response.status_code == 500
    assert response.json() == {"detail": "Secret results could not be loaded"}
    assert RAW not in response.text + caplog.text + capsys.readouterr().out


def test_secret_api_response_validation_error_is_safe(api, caplog):
    saved = api[2]
    saved.findings[0].confidence = 2
    saved.findings[0].title = RAW
    api[1].save(saved)
    response = api[0].get(BASE)
    assert response.status_code == 500 and RAW not in response.text + caplog.text


def test_secret_api_does_not_project_internal_fields_or_legacy_source_line(api):
    saved = api[2]
    target = saved.findings[2]
    target.metadata["raw_value"] = RAW
    target.metadata["source_text"] = RAW
    target.evidence[0].details["matched_value"] = RAW
    target.evidence[0].masked_excerpt = f'API_KEY="sk-****abcd"; other="{RAW}"'
    saved.warnings = [RAW]
    api[1].save(saved)
    detail = api[0].get(BASE + "/api-a")
    overview = api[0].get(BASE)
    assert detail.status_code == overview.status_code == 200
    assert RAW not in detail.text + overview.text
    assert detail.json()["evidence"][0]["masked_excerpt"] == "****"
    assert not any(key in detail.json() for key in ("metadata", "signature", "fingerprint", "rationale"))


@pytest.fixture
def scanned_api(tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    project = tmp_path / "source"
    project.mkdir()
    (project / "config.py").write_text(f'API_KEY="{RAW}"', encoding="utf-8")
    result = ScanEngine(settings).scan(project)  # Arrange once; all following requests are reads.
    client = TestClient(create_app(settings))
    return client, settings, result


def test_secret_overview_does_not_expose_raw_secret(scanned_api):
    client, _, saved = scanned_api
    response = client.get(f"/api/scans/{saved.id}/secrets")
    assert response.status_code == 200 and RAW not in response.text


def test_secret_detail_does_not_expose_raw_secret(scanned_api):
    client, _, saved = scanned_api
    response = client.get(f"/api/scans/{saved.id}/secrets/{saved.findings[0].id}")
    assert response.status_code == 200 and RAW not in response.text


def test_secret_api_json_does_not_expose_raw_secret(scanned_api, caplog, capsys):
    client, settings, saved = scanned_api
    store = ScanStore(settings)
    restored = store.get(saved.id)
    responses = [client.get(f"/api/scans/{saved.id}/secrets"),
                 client.get(f"/api/scans/{saved.id}/secrets/{restored.findings[0].id}")]
    assert all(RAW not in response.text + json.dumps(response.json()) for response in responses)
    assert RAW not in json.dumps(asdict(restored)) + caplog.text + capsys.readouterr().out


def test_secret_queries_never_rescan_or_read_source(scanned_api, monkeypatch):
    client, _, saved = scanned_api
    def forbidden(*args, **kwargs):
        pytest.fail("Query attempted to scan or open source files")
    for method in ("scan", "scan_file", "matches", "redactor_for", "redact_text"):
        monkeypatch.setattr(SecretScanner, method, forbidden)
    monkeypatch.setattr(ScanEngine, "scan", forbidden)
    for method in ("open", "read_text", "read_bytes", "rglob"):
        monkeypatch.setattr(Path, method, forbidden)
    assert client.get(f"/api/scans/{saved.id}/secrets").status_code == 200
    assert client.get(f"/api/scans/{saved.id}/secrets/{saved.findings[0].id}").status_code == 200


def test_secret_api_openapi_contract(api):
    response = api[0].get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    for path in ("/api/scans/{scan_id}/secrets", "/api/scans/{scan_id}/secrets/{finding_id}"):
        operation = spec["paths"][path]["get"]
        assert set(operation["responses"]) >= {"200", "404", "409", "422", "500"}
        assert "$ref" in operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert operation["description"]
    parameters = {p["name"]: p for p in spec["paths"]["/api/scans/{scan_id}/secrets"]["get"]["parameters"]}
    assert parameters["page_size"]["schema"]["maximum"] == 100
    assert RAW not in response.text
    fields = spec["components"]["schemas"]["SecretDetailResponse"]["properties"]
    assert not {"raw_value", "secret_value", "matched_value", "source_text", "metadata"} & fields.keys()

