from contextlib import closing
from copy import deepcopy
from dataclasses import asdict
import gc
import json
from pathlib import Path
import socket
import sqlite3
import weakref

import pytest
from fastapi.testclient import TestClient

from yuanjian_agent.config import LicenseProviderSettings, Settings
from yuanjian_agent.core.scanner import ScanStatus
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.license.adapters.ort import OrtResultProvider
from yuanjian_agent.license.adapters.ort_parser import OrtResultParser
from yuanjian_agent.license.adapters.scancode import ScanCodeAdapter, ScanCodeResultParser
from yuanjian_agent.license.models import LicenseProviderResult, PackageEvidence
from yuanjian_agent.license.policy import DefaultLicensePolicy, UnavailableLicensePolicy
from yuanjian_agent.license.scanner import LicenseScanner
from yuanjian_agent.serialization import scan_result_from_dict
from yuanjian_agent.storage import ScanStore
from yuanjian_agent.web import create_app
from license_provider_support import RAW, SCANCODE, ORT, FakeExecutableRunner, context_for


class StaticProvider:
    def __init__(self, result):
        self.name, self.result = result.name, result

    def collect(self, context):
        return deepcopy(self.result)


def parsed_scancode(expression="MIT"):
    data = {"headers": [{"tool_name": "scancode-toolkit", "tool_version": "32.5.0"}],
            "files": [], "packages": [{"name": "example", "version": "1.0",
                "purl": "pkg:pypi/example@1.0", "datafile_paths": ["pyproject.toml"],
                "declared_license_expression_spdx": expression}]}
    return ScanCodeResultParser().parse(data, LicenseProviderSettings())


@pytest.mark.parametrize("provider", ["scancode", "ort", "both"])
def test_real_adapters_to_default_policy_inventory(provider, tmp_path):
    context = context_for(tmp_path)
    context.config.scanners.enable_scancode = provider != "ort"
    context.config.scanners.enable_ort = provider != "scancode"
    scanner = LicenseScanner(providers=(ScanCodeAdapter(FakeExecutableRunner()), OrtResultProvider()))
    assert isinstance(scanner.policy, DefaultLicensePolicy)
    result = scanner.scan(context)
    assert result.status == "success"
    assert result.metadata["packages"] and result.metadata["dependencies"]
    assert any(a["classification"] == "permissive" and not a["finding_ids"] for a in result.metadata["assessments"])
    # The existing ORT fixture declares MIT throughout, plus an unresolved
    # dependency observation; the ScanCode fixture also contains GPL.
    expected_rule = "LICENSE_UNKNOWN_REVIEW" if provider == "ort" else "LICENSE_STRONG_COPYLEFT_REVIEW"
    assert any(f.rule_id == expected_rule for f in result.findings)
    check_links(result.metadata, result.findings)


def check_links(inventory, findings):
    packages = {p["id"] for p in inventory["packages"]}
    licenses = {l["id"] for l in inventory["licenses"]}
    by_id = {f.id: f for f in findings}
    for dep in inventory["dependencies"]:
        assert dep["package_id"] in packages
    linked = set()
    for assessment in inventory["assessments"]:
        assert assessment["package_id"] is None or assessment["package_id"] in packages
        assert assessment["license_id"] is None or assessment["license_id"] in licenses
        for key in assessment["finding_ids"]:
            linked.add(key)
            assert by_id[key].metadata["assessment_id"] == assessment["id"]
            assert by_id[key].metadata["license_id"] == assessment["license_id"]
    assert linked == set(by_id)


@pytest.mark.parametrize("expression,status,rule", [
    ("mit", "canonical", None), ("GPL-3.0-only", "canonical", "LICENSE_STRONG_COPYLEFT_REVIEW"),
    ("MIT OR GPL-3.0-only", "canonical", "LICENSE_ALTERNATIVE_TERMS_REVIEW"),
    ("LicenseRef-Custom", "license_ref", "LICENSE_UNKNOWN_REVIEW"),
    ("MIT OR", "invalid", "LICENSE_INVALID_EXPRESSION"),
    ("MIT & Apache-2.0", "invalid", "LICENSE_INVALID_EXPRESSION"),
    (None, "missing", "LICENSE_UNKNOWN_REVIEW"),
    ("MIT " * 1500, "unsupported", "LICENSE_UNKNOWN_REVIEW"),
    ("(" * 17 + "MIT" + ")" * 17, "unsupported", "LICENSE_UNKNOWN_REVIEW"),
])
def test_invalid_and_missing_observations_are_not_dropped(expression, status, rule, tmp_path):
    context = context_for(tmp_path)
    output = LicenseScanner(providers=[StaticProvider(parsed_scancode(expression))]).scan(context)
    assert output.status == "success"
    assert len(output.metadata["licenses"]) == len(output.metadata["assessments"]) == 1
    assert output.metadata["licenses"][0]["normalization"]["status"] == status
    assert [f.rule_id for f in output.findings] == ([rule] if rule else [])
    check_links(output.metadata, output.findings)


def test_direct_and_wrapped_scancode_have_one_assessment(tmp_path):
    context = context_for(tmp_path)
    scanner = LicenseScanner(providers=(ScanCodeAdapter(FakeExecutableRunner()), OrtResultProvider()))
    output = scanner.scan(context)
    detected = [l for l in output.metadata["licenses"] if l["source_kind"] == "detected_license"
                and l["location"]["path"] == "LICENSE"]
    assert len(detected) == 1
    assert {p["provider"] for p in detected[0]["provenance"]} == {"scancode", "ort"}
    assert len([a for a in output.metadata["assessments"] if a["license_id"] == detected[0]["id"]]) == 1


@pytest.mark.parametrize("expression,rule", [("GPL-3.0-only", "LICENSE_STRONG_COPYLEFT_REVIEW"),
    ("MIT OR GPL-3.0-only", "LICENSE_ALTERNATIVE_TERMS_REVIEW"),
    ("GPL-2.0-only WITH Classpath-exception-2.0", "LICENSE_STRONG_COPYLEFT_REVIEW"),
    ("MIT OR", "LICENSE_INVALID_EXPRESSION"), ("MIT & Apache-2.0", "LICENSE_INVALID_EXPRESSION")])
def test_ort_import_expression_to_policy(expression, rule, tmp_path):
    context = context_for(tmp_path)
    context.config.scanners.enable_scancode = False
    data = json.loads(ORT.read_text())
    data["scanner"]["scan_results"][0]["summary"]["licenses"][0]["license"] = expression
    context.config.license_providers.ort_result_path.write_text(json.dumps(data))
    output = LicenseScanner().scan(context)
    detected = [l for l in output.metadata["licenses"] if l["source_kind"] == "detected_license"]
    assert len(detected) == 1
    assessments = [a for a in output.metadata["assessments"] if a["license_id"] == detected[0]["id"]]
    assert len(assessments) == 1 and assessments[0]["manual_review_required"]
    assert [f.rule_id for f in output.findings if f.id in assessments[0]["finding_ids"]] == [rule]
    if "WITH" in expression:
        assert detected[0]["normalization"]["canonical_expression"] == expression


@pytest.mark.parametrize("other_status", [ScanStatus.UNAVAILABLE, ScanStatus.FAILED, ScanStatus.PARTIAL])
def test_provider_partial_failure_preserves_inventory(other_status, tmp_path):
    context = context_for(tmp_path)
    scanner = LicenseScanner(providers=[StaticProvider(parsed_scancode("GPL-3.0-only")),
        StaticProvider(LicenseProviderResult("ort", status=other_status))])
    output = scanner.scan(context)
    assert output.status == "partial" and len(output.findings) == 1
    assert len(output.metadata["licenses"]) == 1
    assert output.providers["scancode"] == "success"


@pytest.mark.parametrize("mode", ["disabled", "unavailable", "no-providers"])
def test_no_execution_never_means_clean(mode, tmp_path):
    context = context_for(tmp_path)
    if mode == "disabled":
        context.config.scanners.enable_scancode = context.config.scanners.enable_ort = False
    providers = [] if mode == "no-providers" else [StaticProvider(LicenseProviderResult("scancode")),
                                                 StaticProvider(LicenseProviderResult("ort"))]
    output = LicenseScanner(providers=providers).scan(context)
    assert output.status == "unavailable" and not output.findings
    assert output.metadata["coverage"]["providers_complete"] is False


def test_unavailable_policy_retains_normalized_inventory(tmp_path):
    output = LicenseScanner(UnavailableLicensePolicy(), providers=[StaticProvider(parsed_scancode())]).scan(context_for(tmp_path))
    assert output.status == "unavailable" and output.findings == []
    assert output.metadata["licenses"][0]["normalization"]["canonical_expression"] == "MIT"
    assert output.metadata["assessments"][0]["policy_status"] == "unavailable"


@pytest.mark.parametrize("first_expression", ["GPL-3.0-only", "MIT"])
def test_policy_failure_keeps_other_assessments_and_diagnostic_safe(first_expression, tmp_path):
    provider = parsed_scancode(first_expression)
    second = deepcopy(provider.licenses[0])
    second.license_expression = "MPL-2.0"
    provider.licenses.append(second)

    class BrokenPolicy(DefaultLicensePolicy):
        def assess(self, evidence):
            if evidence.license_expression == "MPL-2.0":
                raise RuntimeError("PRIVATE-DIAGNOSTIC")
            return super().assess(evidence)

    output = LicenseScanner(BrokenPolicy(), providers=[StaticProvider(provider)]).scan(context_for(tmp_path))
    assert output.status == "partial" and len(output.findings) == (1 if first_expression == "GPL-3.0-only" else 0)
    assert {a["policy_status"] for a in output.metadata["assessments"]} == {"success", "failed"}
    assert "PRIVATE-DIAGNOSTIC" not in repr(output)


@pytest.mark.parametrize("limit", ["count", "bytes"])
def test_inventory_truncation_is_explicit_and_links_stay_valid(limit, tmp_path, monkeypatch):
    from yuanjian_agent.license import inventory
    monkeypatch.setattr(inventory, "MAX_INVENTORY_RECORDS" if limit == "count" else "MAX_INVENTORY_BYTES",
                        1 if limit == "count" else 400)
    context = context_for(tmp_path)
    result = LicenseScanner(providers=[StaticProvider(ScanCodeResultParser().parse(
        json.loads(SCANCODE.read_text()), LicenseProviderSettings()))]).scan(context)
    assert result.status == "partial"
    assert result.metadata["coverage"]["inventory_complete"] is False
    assert result.metadata["coverage"]["dropped_records"] > 0
    check_links(result.metadata, result.findings)


def test_orphan_package_is_reviewable_without_fabricated_location(tmp_path):
    provider = LicenseProviderResult("scancode", status=ScanStatus.SUCCESS,
                                     packages=[PackageEvidence("orphan", "1.0")])
    output = LicenseScanner(providers=[StaticProvider(provider)]).scan(context_for(tmp_path))
    assert not output.findings and output.metadata["licenses"] == []
    assert output.status == "partial"
    assessment = output.metadata["assessments"][0]
    assert assessment["manual_review_required"] and assessment["license_id"] is None
    assert assessment["reason"] == "no_located_license_fact"


def test_persistence_engine_store_app_recreation_and_offline_boundary(tmp_path, monkeypatch, capsys, caplog):
    context = context_for(tmp_path)
    # Default Engine uses real ORT import and the real default policy.
    context.config.scanners.enable_scancode = False
    context.config.scanners.enable_secret = False
    marker = tmp_path / "plugin-executed"
    for name in (".ort.yml", ".scancode.yml"):
        (context.project_root / name).write_text(f"command: {marker}\n")

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected network or target execution")

    monkeypatch.setattr("yuanjian_agent.license.adapters.process.ScanCodeProcessRunner.run", forbidden)
    engine = ScanEngine(context.config)
    with monkeypatch.context() as network:
        network.setattr(socket, "create_connection", forbidden)
        network.setattr(socket.socket, "connect", forbidden)
        result = engine.scan(context.project_root)
    inventory = result.metadata["module_data"]["license"]
    assert result.metadata["scanners"]["license"]["status"] == "success"
    assert inventory["summary"]["packages"] and inventory["summary"]["dependencies"]
    assert inventory["summary"]["licenses"] == inventory["summary"]["assessments"]
    check_links(inventory, result.findings)
    payload = result.to_dict()
    file_payload = json.loads(engine.store.result_path(result.id).read_text(encoding="utf-8"))
    assert scan_result_from_dict(file_payload).metadata["module_data"]["license"] == inventory
    with closing(sqlite3.connect(context.config.database_path)) as connection:
        sqlite_payload = json.loads(connection.execute("SELECT result_json FROM scans WHERE id=?", (result.id,)).fetchone()[0])
        assert sqlite_payload == file_payload == payload
        assert {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {"scans", "findings"}
    app = create_app(context.config)
    with TestClient(app) as client:
        before = client.get(f"/api/scans/{result.id}").json()
    scan_id, data_dir = result.id, context.config.data_dir
    old = [weakref.ref(obj) for obj in (engine, engine.store, app)]
    del client, app, result, engine
    gc.collect()
    assert all(ref() is None for ref in old)

    settings = Settings(data_dir=data_dir)
    store = ScanStore(settings)
    restored = store.get(scan_id)
    assert restored.metadata["module_data"]["license"] == inventory
    check_links(inventory, restored.findings)
    new_app = create_app(settings)
    monkeypatch.setattr(ScanEngine, "scan", forbidden)
    monkeypatch.setattr(LicenseScanner, "scan", forbidden)
    monkeypatch.setattr(OrtResultProvider, "collect", forbidden)
    monkeypatch.setattr(ScanStore, "save", forbidden)
    for name in ("read_text", "read_bytes", "open", "rglob"):
        monkeypatch.setattr(Path, name, forbidden)
    with TestClient(new_app) as client:
        assert client.get(f"/api/scans/{scan_id}").json() == before
        assert client.get(f"/api/scans/{scan_id}").json() == before
    assert not marker.exists() and not (tmp_path / "target-executed").exists()
    new_output = json.dumps({"inventory": inventory, "findings": payload["findings"]}, ensure_ascii=False)
    assert str(context.project_root) not in new_output
    assert context.project_root.as_posix() not in new_output
    captured = capsys.readouterr()
    boundaries = new_output + json.dumps(sqlite_payload) + json.dumps(before) + caplog.text + captured.out + captured.err
    assert all(raw not in boundaries for raw in RAW)
    assert "stdout" not in new_output and "stderr" not in new_output


def test_fact_identity_preserves_scope_kind_and_is_stable(tmp_path):
    provider = parsed_scancode("GPL-3.0-only")
    second = deepcopy(provider.licenses[0])
    second.evidence.details["source_kind"] = "detected_license"
    provider.licenses.append(second)
    scanner = LicenseScanner(providers=[StaticProvider(provider)])
    context = context_for(tmp_path)
    first, second = scanner.scan(context), scanner.scan(context)
    assert [f.id for f in first.findings] == [f.id for f in second.findings]
    assert len({f.id for f in first.findings}) == 2
    assert first.metadata == second.metadata


def test_inventory_projects_only_safe_fields_and_redacts_without_secret_module(tmp_path):
    context = context_for(tmp_path)
    context.config.scanners.enable_secret = False
    raw = "Synthetic_License_Secret_2190Zab"
    (context.project_root / "input.py").write_text(f'password="{raw}"\n')
    from yuanjian_agent.files import iter_text_files
    context.files, _ = iter_text_files(context.project_root, context.config.limits)
    provider = parsed_scancode(raw)
    provider.licenses[0].evidence.masked_excerpt = "RAW-LARGE-CONTEXT"
    provider.licenses[0].evidence.details.update(raw_json={"private": "RAW-UPSTREAM-BLOB"},
        stdout="FULL-STDOUT", stderr="FULL-STDERR", absolute_root=str(context.project_root))
    output = LicenseScanner(providers=[StaticProvider(provider)]).scan(context)
    payload = json.dumps(asdict(output))
    assert all(item not in payload for item in (raw, "RAW-LARGE-CONTEXT", "RAW-UPSTREAM-BLOB", "FULL-STDOUT", "FULL-STDERR"))
    assert str(context.project_root) not in payload
    assert output.metadata["assessments"][0]["manual_review_required"]


def test_packaging_is_a_direct_pinned_range_dependency():
    import tomllib
    project = Path(__file__).parents[1]
    config = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert "packaging>=26.3,<27" in config["project"]["dependencies"]
