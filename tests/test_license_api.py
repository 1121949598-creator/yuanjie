"""License HTTP contracts consume only a persisted schema-v1 inventory."""
import gc
from pathlib import Path
import sqlite3
import weakref

from fastapi.testclient import TestClient
import pytest

from test_license_query import inventory, license_finding, license_scan
from yuanjian_agent.config import Settings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.license.adapters.ort import OrtAdapter
from yuanjian_agent.license.adapters.scancode import ScanCodeAdapter
from yuanjian_agent.license.policy import DefaultLicensePolicy
from yuanjian_agent.license.scanner import LicenseScanner
from yuanjian_agent.models import Severity
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app


BASE = "/api/scans/scan-a/licenses"
MARKER = "sensitive-query-input-must-not-return"


@pytest.fixture
def api(tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    store = ScanStore(settings)
    saved = license_scan()
    store.save(saved)
    client = TestClient(create_app(settings))
    return client, store, saved, settings


def test_license_overview_200(api):
    response = api[0].get(BASE)
    assert response.status_code == 200
    result = response.json()
    assert result["scan_id"] == "scan-a" and result["module"] == "license"
    assert result["inventory_available"] and result["inventory"]["schema_version"] == 1
    assert result["pagination"] == {"page": 1, "page_size": 20, "total": 4}
    assert set(result["items"][0]) == {
        "assessment_id", "license_id", "package_id", "classification", "severity",
        "manual_review_required", "reason", "component_categories", "alternative_terms",
        "exception_review", "policy_status", "finding_ids", "package_name", "package_version",
        "package_purl", "original_expression", "canonical_expression", "normalization_status",
        "location", "source", "source_kind", "source_scope", "finding_count",
    }
    assert "source_path" not in response.text


def test_license_detail_uses_assessment_id(api):
    response = api[0].get(BASE + "/assess-strong")
    assert response.status_code == 200
    result = response.json()
    assert result["assessment"]["assessment_id"] == "assess-strong"
    assert result["assessment"]["license_id"] == "lic-strong"
    assert result["finding_refs"][0]["finding_id"] == "finding-strong"
    assert result["location"]["file_path"] == "src/license.py"


@pytest.mark.parametrize("suffix", ["", "/anything"])
def test_scan_not_found_has_fixed_body(api, suffix):
    response = api[0].get("/api/scans/missing/licenses" + suffix)
    assert response.status_code == 404 and response.json() == {"detail": "Scan not found"}


def test_assessment_not_found_has_fixed_body(api):
    response = api[0].get(BASE + "/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "License assessment not found in this scan"}


def test_assessment_scope_and_same_id_across_scans(api):
    second = inventory()
    second["assessments"][0]["id"] = "only-b"
    second["assessments"][1]["id"] = "assess-strong"
    api[1].save(license_scan("scan-b", inventory_data=second))
    assert api[0].get(BASE + "/only-b").status_code == 404
    assert api[0].get("/api/scans/scan-b/licenses/only-b").status_code == 200
    assert api[0].get(BASE + "/assess-strong").json()["assessment"]["license_id"] == "lic-strong"
    assert api[0].get("/api/scans/scan-b/licenses/assess-strong").json()["assessment"]["license_id"] == "lic-network"


@pytest.mark.parametrize("state", ["pending", "queued", "running"])
@pytest.mark.parametrize("suffix", ["", "/assess-strong"])
def test_unfinished_scan_returns_conflict(api, state, suffix):
    api[1].save(license_scan("unfinished", status=state))
    response = api[0].get("/api/scans/unfinished/licenses" + suffix)
    assert response.status_code == 409
    assert response.json() == {"detail": "Scan results are not final"}


@pytest.mark.parametrize("suffix", ["", "/assess-strong"])
def test_unsupported_schema_returns_conflict(api, suffix):
    data = inventory()
    data["schema_version"] = 2
    api[1].save(license_scan("future", inventory_data=data))
    response = api[0].get("/api/scans/future/licenses" + suffix)
    assert response.status_code == 409
    assert response.json() == {"detail": "License inventory schema is not supported"}


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": MARKER}, {"page_size": 0}, {"page_size": 101},
    {"severity": MARKER}, {"classification": ""}, {"package_name": " "},
    {"license_expression": "x" * 257}, {"file_path": ""},
    {"manual_review_required": "1"}, {"manual_review_required": "yes"},
    {"sort": "severity; DROP TABLE scans;"}, {"unknown": MARKER},
])
def test_invalid_parameters_are_fixed_and_safe(api, params, caplog):
    response = api[0].get(BASE, params=params)
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid License query parameters"}
    assert MARKER not in response.text + caplog.text


def test_repeated_parameter_is_rejected(api):
    response = api[0].get(BASE, params=[("page", "1"), ("page", MARKER)])
    assert response.status_code == 422 and response.json() == {"detail": "Invalid License query parameters"}


def test_sql_like_filter_is_only_a_string(api):
    response = api[0].get(BASE, params={"package_name": "' OR 1=1 --"})
    assert response.status_code == 200 and response.json()["pagination"]["total"] == 0
    assert api[0].get(BASE).json()["summary"]["assessments"] == 4


def test_all_http_filters_and_strict_boolean(api):
    params = {"classification": "network_copyleft", "severity": "high",
              "manual_review_required": "true", "package_name": "BETA",
              "license_expression": "agpl", "file_path": "REQUIREMENTS"}
    result = api[0].get(BASE, params=params).json()
    assert [item["assessment_id"] for item in result["items"]] == ["assess-network"]
    assert api[0].get(BASE, params={"manual_review_required": "false"}).json()["pagination"]["total"] == 1


def test_stable_pagination_and_item_kinds(api):
    first = api[0].get(BASE, params={"page": 1, "page_size": 2}).json()
    second = api[0].get(BASE, params={"page": 2, "page_size": 2}).json()
    repeat = api[0].get(BASE, params={"page": 1, "page_size": 2}).json()
    assert first == repeat
    assert [item["assessment_id"] for item in first["items"] + second["items"]] == [
        "assess-strong", "assess-network", "assess-unlocated", "assess-permissive"
    ]
    permissive = api[0].get(BASE + "/assess-permissive").json()
    unlocated = api[0].get(BASE + "/assess-unlocated").json()
    assert permissive["assessment"]["severity"] is None and permissive["finding_refs"] == []
    assert unlocated["license"] is None and unlocated["location"] is None


def test_historical_scan_returns_unavailable_overview(api):
    api[1].save(license_scan("history", include_inventory=False, findings=[]))
    response = api[0].get("/api/scans/history/licenses")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "unavailable" and result["inventory_available"] is False
    assert result["items"] == []
    assert result["diagnostics"][0] == "License inventory was not recorded for this scan."


@pytest.mark.parametrize("suffix", ["", "/assess-strong"])
def test_store_errors_are_safe(api, monkeypatch, suffix, caplog, capsys):
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError(MARKER)
    monkeypatch.setattr(ScanStore, "get", fail)
    response = api[0].get(BASE + suffix)
    assert response.status_code == 500
    assert response.json() == {"detail": "License results could not be loaded"}
    assert MARKER not in response.text + caplog.text + capsys.readouterr().out


def test_conversion_errors_are_safe(api, caplog):
    data = inventory()
    data["summary"]["packages"] = MARKER
    api[1].save(license_scan(inventory_data=data))
    response = api[0].get(BASE)
    assert response.status_code == 500
    assert response.json() == {"detail": "License results could not be loaded"}
    assert MARKER not in response.text + caplog.text


def test_absolute_saved_location_fails_closed_without_path_disclosure(api):
    data = inventory()
    absolute = "C:/private/target/LICENSE"
    data["licenses"][0]["location"]["path"] = absolute
    api[1].save(license_scan(inventory_data=data))
    response = api[0].get(BASE)
    assert response.status_code == 500
    assert response.json() == {"detail": "License results could not be loaded"}
    assert absolute not in response.text


def test_one_store_get_per_request(api, monkeypatch):
    original = ScanStore.get
    reads = []
    def counted(self, scan_id):
        reads.append(scan_id)
        return original(self, scan_id)
    monkeypatch.setattr(ScanStore, "get", counted)
    assert api[0].get(BASE).status_code == 200 and reads == ["scan-a"]
    reads.clear()
    assert api[0].get(BASE + "/assess-strong").status_code == 200 and reads == ["scan-a"]


def test_queries_do_not_rescan_run_policy_collect_providers_or_read_source(api, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("License query crossed the persisted-results boundary")
    monkeypatch.setattr(ScanEngine, "scan", forbidden)
    monkeypatch.setattr(LicenseScanner, "scan", forbidden)
    monkeypatch.setattr(ScanCodeAdapter, "collect", forbidden)
    monkeypatch.setattr(OrtAdapter, "collect", forbidden)
    monkeypatch.setattr(DefaultLicensePolicy, "evaluate", forbidden)
    monkeypatch.setattr(DefaultLicensePolicy, "assess", forbidden)
    monkeypatch.setattr("yuanjian_agent.license.spdx.normalize_spdx", forbidden)
    for method in ("open", "read_text", "read_bytes", "rglob"):
        monkeypatch.setattr(Path, method, forbidden)
    assert api[0].get(BASE).status_code == 200
    assert api[0].get(BASE + "/assess-strong").status_code == 200


def test_persisted_inventory_survives_store_and_app_recreation(tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "state")
    store = ScanStore(settings)
    store.save(license_scan())
    app = create_app(settings)
    with TestClient(app) as client:
        before_overview = client.get(BASE).json()
        before_detail = client.get(BASE + "/assess-strong").json()
    references = [weakref.ref(store), weakref.ref(app)]
    del client, app, store
    gc.collect()
    assert all(reference() is None for reference in references)
    recreated_settings = Settings(data_dir=settings.data_dir)
    recreated_store = ScanStore(recreated_settings)
    assert recreated_store.get("scan-a").metadata["module_data"]["license"]["schema_version"] == 1
    recreated_app = create_app(recreated_settings)
    def forbidden(*args, **kwargs):
        pytest.fail("Recreated query attempted a write or scan")
    monkeypatch.setattr(ScanStore, "save", forbidden)
    monkeypatch.setattr(ScanEngine, "scan", forbidden)
    monkeypatch.setattr(LicenseScanner, "scan", forbidden)
    with TestClient(recreated_app) as client:
        assert client.get(BASE).json() == before_overview
        assert client.get(BASE + "/assess-strong").json() == before_detail


def test_license_openapi_contract(api):
    response = api[0].get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = (
        "/api/scans/{scan_id}/licenses",
        "/api/scans/{scan_id}/licenses/{assessment_id}",
    )
    for path in paths:
        operation = spec["paths"][path]["get"]
        assert set(operation["responses"]) >= {"200", "404", "409", "422", "500"}
        assert "$ref" in operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert operation["summary"] and operation["description"]
        assert "License results" in operation["tags"]
    parameters = {item["name"]: item for item in spec["paths"][paths[0]]["get"]["parameters"]}
    assert parameters["page_size"]["schema"]["maximum"] == 100
    assert "assessment_id" in {item["name"] for item in spec["paths"][paths[1]]["get"]["parameters"]}
    assert MARKER not in response.text
    fields = spec["components"]["schemas"]["LicenseDetailResponse"]["properties"]
    assert not {"metadata", "source_path", "raw_json", "stdout", "stderr", "command"} & fields.keys()


def test_license_query_modules_do_not_import_secret_business_components():
    root = Path(__file__).parents[1] / "src" / "yuanjian_agent" / "license"
    for name in ("query.py", "schemas.py", "service.py", "router.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert "secret.query" not in source and "secret.router" not in source and "secret.service" not in source
