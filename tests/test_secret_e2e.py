"""Final offline acceptance: disk project -> scan -> save -> fresh app -> HTTP."""
import base64
from contextlib import closing
import gc
import json
import logging
from pathlib import Path
import shutil
import sqlite3
import weakref

from fastapi.testclient import TestClient
import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.models import FindingCategory
from yuanjian_agent.secrets import SecretScanner
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app


FIXTURE = Path(__file__).parent / "fixtures" / "secret_e2e_project"
RAW_API_KEY = "sk-test-8KJd82kdlQ93kdl20f"
RAW_PASSWORD = "A8fK29dLm7Qx"
RAW_DB_PASSWORD = "DbPass927x"
RAW_DATABASE_URL = "mysql://admin:DbPass927x@localhost/demo"
RAW_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJzeW50aGV0aWMtdXNlciJ9."
    "U3ludGhldGljU2lnbmF0dXJlT25seQ"
)
RAW_PEM_BODY = "U3ludGhldGljUHJpdmF0ZUtleU1hdGVyaWFs"
RAW_PEM = f"-----BEGIN PRIVATE KEY-----\n{RAW_PEM_BODY}\n-----END PRIVATE KEY-----"
RAW_VALUES = (RAW_API_KEY, RAW_PASSWORD, RAW_DB_PASSWORD, RAW_DATABASE_URL, RAW_JWT, RAW_PEM_BODY, RAW_PEM)
EXPECTED_SUMMARY = {"total": 5, "critical": 1, "high": 2, "medium": 2, "low": 0, "info": 0}
EXPECTED_TYPES = {"api_key": 1, "password": 1, "database_credential": 1, "jwt": 1, "private_key": 1}
EXPECTED_ITEMS = {
    "api_key": ("config.py", 2, 11, "secret.openai-key", "high", 0.99, "sk-t****l20f"),
    "password": (".env", 2, 13, "secret.generic-assignment", "medium", 0.73, "A8f****7Qx"),
    "database_credential": ("docker-compose.yml", 6, 21, "secret.database-url", "high", 0.85, "mysq****demo"),
    "jwt": ("app.py", 2, 15, "secret.jwt", "medium", 0.65, "eyJh****5seQ"),
    "private_key": ("app.py", 3, 17, "secret.private-key", "critical", 0.95, "****"),
}


@pytest.fixture
def project(tmp_path):
    target = tmp_path / "project"
    shutil.copytree(FIXTURE, target)
    assert {file.name for file in target.iterdir()} == {
        "app.py", "config.py", ".env", "docker-compose.yml", "normal.py",
    }
    return target


def assert_no_raw_values(boundaries):
    """Report the failing boundary, never print the credential or unsafe payload."""
    forbidden = (*RAW_VALUES, *(json.dumps(value)[1:-1] for value in RAW_VALUES))
    for name, output in boundaries.items():
        if any(value in output for value in forbidden):
            pytest.fail(f"Raw synthetic credential escaped at boundary: {name}", pytrace=False)


def snapshot(client, scan_id):
    response = client.get(f"/api/scans/{scan_id}/secrets")
    assert_no_raw_values({"Overview HTTP": response.text})
    assert response.status_code == 200
    overview = response.json()
    details = {}
    for item in overview["items"]:
        response = client.get(f"/api/scans/{scan_id}/secrets/{item['finding_id']}")
        assert_no_raw_values({"Detail HTTP": response.text})
        assert response.status_code == 200
        details[item["finding_id"]] = response.json()
    return {"overview": overview, "details": details}


def stored_boundaries(settings, result):
    with closing(sqlite3.connect(settings.database_path)) as connection:
        saved = connection.execute("SELECT result_json FROM scans WHERE id = ?", (result.id,)).fetchone()
        indexed = connection.execute("SELECT * FROM findings WHERE scan_id = ?", (result.id,)).fetchall()
    assert saved is not None
    assert len(indexed) == len(result.findings)
    disk = (settings.scans_dir / result.id / "result.json").read_text(encoding="utf-8")
    assert_no_raw_values({"SQLite result": saved[0], "disk result.json": disk})
    assert json.loads(saved[0]) == json.loads(disk) == result.to_dict()
    return {
        "ScanResult serialization": json.dumps(result.to_dict()),
        "SQLite scans.result_json": saved[0],
        "SQLite findings visible fields": json.dumps(indexed),
        "disk result.json": disk,
        "saved diagnostics": json.dumps(result.warnings),
    }


def assert_default_contract(saved_snapshot):
    overview = saved_snapshot["overview"]
    assert overview["status"] == "success" and overview["scan_status"] == "completed"
    assert overview["summary"] == EXPECTED_SUMMARY
    assert overview["by_type"] == EXPECTED_TYPES
    assert overview["pagination"] == {"page": 1, "page_size": 20, "total": 5}
    assert len(overview["items"]) == 5
    for item in overview["items"]:
        path, line, column, rule, severity, confidence, mask = EXPECTED_ITEMS[item["secret_type"]]
        assert item["rule_id"] == rule
        assert item["severity"] == severity and item["confidence"] == pytest.approx(confidence)
        assert item["location"]["file_path"] == path and item["location"]["line"] == line
        assert item["location"]["column_start"] == column
        assert item["masked_value"] == mask and item["occurrence_count"] == 1
        detail = saved_snapshot["details"][item["finding_id"]]
        assert detail["finding_id"] == item["finding_id"]
        assert detail["scan_id"] == overview["scan_id"]
        for key in ("rule_id", "secret_type", "severity", "confidence", "location", "masked_value", "message"):
            assert detail[key] == item[key]
        assert detail["message"]
        assert detail["evidence"] == [{
            "location": item["location"], "masked_value": mask, "masked_excerpt": mask,
        }]
        assert detail["remediation"]["title"] and len(detail["remediation"]["steps"]) >= 3
    private = next(item for item in overview["items"] if item["secret_type"] == "private_key")
    assert private["location"]["end_line"] == 5 and private["location"]["column_end"] == 25
    api_key = next(item for item in overview["items"] if item["secret_type"] == "api_key")
    assert api_key["location"]["column_end"] == 11 + len(RAW_API_KEY)


def test_secret_e2e_scan_persist_query(project, tmp_path, monkeypatch):
    calls = {"scan": 0, "save": 0}
    original_scan, original_save = ScanEngine.scan, ScanStore.save

    def scan_once(self, *args, **kwargs):
        calls["scan"] += 1
        return original_scan(self, *args, **kwargs)

    def save_once(self, result):
        calls["save"] += 1
        return original_save(self, result)

    monkeypatch.setattr(ScanEngine, "scan", scan_once)
    monkeypatch.setattr(ScanStore, "save", save_once)
    settings = Settings(data_dir=tmp_path / "state")
    engine = ScanEngine(settings)
    result = engine.scan(project)
    assert result.metadata["scanners"]["secret"]["status"] == "success"
    assert result.summary.secrets == 5
    secrets = [finding for finding in result.findings if finding.category == FindingCategory.SECRET]
    assert len(secrets) == 5
    assert all(e.source_span.path != "normal.py" for finding in secrets for e in finding.evidence)
    # JWT contains JSON objects and a synthetic, decodable signature, no real identity.
    header, payload, signature = RAW_JWT.split(".")
    decoded = [base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)) for part in (header, payload, signature)]
    assert json.loads(decoded[0])["alg"] == "HS256"
    assert json.loads(decoded[1]) == {"sub": "synthetic-user"}
    assert decoded[2] == b"SyntheticSignatureOnly"
    assert_no_raw_values(stored_boundaries(settings, result))
    with TestClient(create_app(settings)) as client:
        assert_default_contract(snapshot(client, result.id))
    assert calls == {"scan": 1, "save": 1}


def test_secret_e2e_survives_store_restart(project, tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    engine = ScanEngine(settings)
    old_store = engine.store
    result = engine.scan(project)
    scan_id, serialized = result.id, json.dumps(result.to_dict(), sort_keys=True)
    old_app = create_app(settings)
    with TestClient(old_app) as client:
        before = snapshot(client, scan_id)
    refs = (weakref.ref(engine), weakref.ref(old_store), weakref.ref(old_app))
    del client, old_app, engine, old_store, result, settings
    gc.collect()
    assert all(reference() is None for reference in refs)

    restarted_settings = Settings(data_dir=tmp_path / "state")
    new_store = ScanStore(restarted_settings)
    restored = new_store.get(scan_id)
    assert json.dumps(restored.to_dict(), sort_keys=True) == serialized
    with TestClient(create_app(restarted_settings)) as new_client:
        after = snapshot(new_client, scan_id)
    assert_default_contract(after)
    assert after == before


def test_secret_query_does_not_rescan_after_restart(project, tmp_path, monkeypatch):
    settings = Settings(data_dir=tmp_path / "state")
    engine = ScanEngine(settings)
    result = engine.scan(project)
    scan_id = result.id
    del engine, result
    gc.collect()
    restarted_settings = Settings(data_dir=tmp_path / "state")
    restored = ScanStore(restarted_settings).get(scan_id)
    app = create_app(restarted_settings)  # Application startup may read its own rule resources.

    def forbidden(*args, **kwargs):
        pytest.fail("Saved-result query attempted a scan, source read or save", pytrace=False)

    monkeypatch.setattr(ScanEngine, "scan", forbidden)
    for name in ("scan", "scan_file", "matches", "redactor_for", "redact_text"):
        monkeypatch.setattr(SecretScanner, name, forbidden)
    monkeypatch.setattr(ScanStore, "save", forbidden)
    for name in ("open", "read_text", "read_bytes", "rglob"):
        monkeypatch.setattr(Path, name, forbidden)
    with TestClient(app) as client:
        first = snapshot(client, scan_id)
        second = snapshot(client, scan_id)
    assert len(first["details"]) == restored.summary.secrets == 5
    assert_default_contract(first)
    assert first == second


def test_secret_e2e_no_raw_secret_leak(project, tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    settings = Settings(data_dir=tmp_path / "state")
    engine = ScanEngine(settings)
    result = engine.scan(project)
    outputs = stored_boundaries(settings, result)
    scan_id = result.id
    del engine, result
    gc.collect()
    restored = ScanStore(Settings(data_dir=tmp_path / "state")).get(scan_id)
    outputs["restarted Store serialization"] = json.dumps(restored.to_dict())
    with TestClient(create_app(Settings(data_dir=tmp_path / "state"))) as client:
        responses = snapshot(client, scan_id)
        outputs["all Overview and Detail JSON"] = json.dumps(responses)
        missing = client.get(f"/api/scans/{scan_id}/secrets/missing")
        invalid = client.get(f"/api/scans/{scan_id}/secrets", params={"page": 0})
        assert missing.status_code == 404 and invalid.status_code == 422
        outputs["HTTP error diagnostics"] = missing.text + invalid.text
    captured = capsys.readouterr()
    outputs.update({"logs": caplog.text, "stdout": captured.out, "stderr": captured.err})
    assert_no_raw_values(outputs)


def test_secret_e2e_partial_preserves_findings(project, tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    settings = Settings(data_dir=tmp_path / "state")
    engine = ScanEngine(settings)
    visited = []
    original = engine.secret_scanner.scan_file

    def fail_one_file(file):
        visited.append(file.relative_path)
        if file.relative_path == ".env":
            raise RuntimeError("Synthetic error: " + RAW_PASSWORD + " " + RAW_DB_PASSWORD + " " + RAW_API_KEY)
        return original(file)

    with monkeypatch.context() as patch:
        patch.setattr(engine.secret_scanner, "scan_file", fail_one_file)
        result = engine.scan(project)
    assert set(visited) == {"app.py", "config.py", ".env", "docker-compose.yml", "normal.py"}
    assert result.status == "partial"
    assert result.metadata["scanners"]["secret"]["status"] == "partial"
    assert result.metadata["scanners"]["secret"]["providers"]["builtin-secret"] == "partial"
    assert result.metadata["scanners"]["agent_security"]["status"] == "success"
    assert result.summary.secrets == 4
    assert {f.metadata["secret_type"] for f in result.findings if f.category == FindingCategory.SECRET} == {
        "api_key", "jwt", "private_key", "database_credential",
    }
    assert "builtin-secret: file failed; diagnostic details suppressed" in result.warnings
    outputs = stored_boundaries(settings, result)
    expected_ids = {f.id for f in result.findings if f.category == FindingCategory.SECRET}
    with TestClient(create_app(Settings(data_dir=tmp_path / "state"))) as client:
        responses = snapshot(client, result.id)
    overview = responses["overview"]
    assert overview["status"] == overview["scan_status"] == "partial"
    assert overview["summary"] == dict(total=4, critical=1, high=2, medium=1, low=0, info=0)
    assert overview["by_type"] == {kind: count for kind, count in EXPECTED_TYPES.items() if kind != "password"}
    assert {item["finding_id"] for item in overview["items"]} == expected_ids
    assert all(item["status"] == "partial" for item in responses["details"].values())
    captured = capsys.readouterr()
    outputs.update({"partial API responses": json.dumps(responses), "logs": caplog.text,
                    "stdout": captured.out, "stderr": captured.err})
    assert_no_raw_values(outputs)


def test_secret_e2e_result_order_is_stable(project, tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    result = ScanEngine(settings).scan(project)
    with TestClient(create_app(Settings(data_dir=tmp_path / "state"))) as client:
        first = snapshot(client, result.id)
        second = snapshot(client, result.id)
    assert first == second
    assert [item["secret_type"] for item in first["overview"]["items"]] == [
        "private_key", "api_key", "database_credential", "password", "jwt",
    ]


def test_secret_e2e_cross_scan_finding_isolation(project, tmp_path):
    settings = Settings(data_dir=tmp_path / "state")
    engine = ScanEngine(settings)
    scan_a = engine.scan(project)
    other = tmp_path / "other-project"
    shutil.copytree(FIXTURE, other)
    (other / "config.py").write_text('API_KEY = "YOUR_API_KEY"\n', encoding="utf-8")
    # Same password/path/HMAC retains a Finding ID while the source location changes.
    env = other / ".env"
    env.write_text("# Added synthetic comment\n" + env.read_text(encoding="utf-8"), encoding="utf-8")
    scan_b = engine.scan(other)
    by_type_a = {f.metadata["secret_type"]: f for f in scan_a.findings if f.category == FindingCategory.SECRET}
    by_type_b = {f.metadata["secret_type"]: f for f in scan_b.findings if f.category == FindingCategory.SECRET}
    assert scan_a.id != scan_b.id and scan_b.summary.secrets == 4
    shared = by_type_a["password"].id
    assert shared == by_type_b["password"].id
    with TestClient(create_app(Settings(data_dir=tmp_path / "state"))) as client:
        wrong = client.get(f"/api/scans/{scan_b.id}/secrets/{by_type_a['api_key'].id}")
        assert wrong.status_code == 404
        assert wrong.json() == {"detail": "Secret finding not found in this scan"}
        detail_a = client.get(f"/api/scans/{scan_a.id}/secrets/{shared}")
        detail_b = client.get(f"/api/scans/{scan_b.id}/secrets/{shared}")
        assert detail_a.status_code == detail_b.status_code == 200
        assert detail_a.json()["scan_id"] == scan_a.id and detail_a.json()["location"]["line"] == 2
        assert detail_b.json()["scan_id"] == scan_b.id and detail_b.json()["location"]["line"] == 3
        assert_no_raw_values({"cross-scan HTTP": wrong.text + detail_a.text + detail_b.text})

