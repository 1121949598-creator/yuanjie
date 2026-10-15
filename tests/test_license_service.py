from copy import deepcopy
import json
import socket

import pytest
from pydantic import ValidationError

from test_license_query import inventory, license_finding, license_scan
from yuanjian_agent.core.scanner import ScanStatus
from yuanjian_agent.license.query import (
    LicenseAssessmentNotFound, LicenseQuery, LicenseQueryError, LicenseQueryRepository, ScanNotReady,
)
from yuanjian_agent.license.schemas import LicenseLocationResponse
from yuanjian_agent.license.service import LicenseQueryService
from yuanjian_agent.models import FindingCategory, Severity


class SavedStore:
    def __init__(self, saved):
        self.saved = saved
        self.reads = 0

    def get(self, scan_id):
        self.reads += 1
        if scan_id != self.saved.id:
            raise KeyError(scan_id)
        return self.saved


def service(saved):
    return LicenseQueryService(LicenseQueryRepository(SavedStore(saved)))


def test_overview_projects_saved_summary_coverage_providers_and_items():
    result = service(license_scan()).overview("scan-a")
    assert result.inventory_available and result.inventory.schema_version == 1
    assert result.summary.model_dump() == {
        "packages": 3, "dependencies": 1, "licenses": 3, "assessments": 4,
        "manual_review_required": 3,
        "by_classification": {"network_copyleft": 1, "permissive": 1,
                              "strong_copyleft": 1, "unknown": 1},
    }
    assert result.coverage.status == ScanStatus.SUCCESS
    assert [(p.name, p.status) for p in result.providers] == [
        ("scancode", ScanStatus.SUCCESS), ("ort", ScanStatus.DISABLED)
    ]
    assert result.items[0].assessment_id == "assess-strong"
    assert result.items[0].package_name == "Alpha"
    assert result.items[0].canonical_expression == "GPL-3.0-only"
    assert result.items[0].finding_count == 1


def test_overview_summary_is_whole_inventory_before_filters():
    result = service(license_scan()).overview(
        "scan-a", LicenseQuery(classification="permissive")
    )
    assert result.summary.assessments == 4 and result.pagination.total == 1
    assert [item.assessment_id for item in result.items] == ["assess-permissive"]


def test_detail_projects_assessment_package_license_normalization_location_and_refs():
    data = inventory()
    data["licenses"][0]["normalization"] = {
        **data["licenses"][0]["normalization"],
        "original_expression": "GPL-2.0-only WITH Classpath-exception-2.0",
        "canonical_expression": "GPL-2.0-only WITH Classpath-exception-2.0",
        "license_ids": ["GPL-2.0-only"], "exception_ids": ["Classpath-exception-2.0"],
        "manual_review_required": True, "reason": "canonicalized",
    }
    result = service(license_scan(inventory_data=data)).detail("scan-a", "assess-strong")
    assert result.assessment.assessment_id == "assess-strong"
    assert result.package.id == "pkg-alpha" and result.package.identifier == "PyPI::alpha:1.0"
    assert result.license.id == "lic-strong" and result.license.source_kind == "detected_license"
    assert result.location.file_path == "src/license.py" and result.location.line == 3
    assert result.normalization.license_ids == ["GPL-2.0-only"]
    assert result.normalization.exception_ids == ["Classpath-exception-2.0"]
    assert [ref.finding_id for ref in result.finding_refs] == ["finding-strong"]
    assert [provider.name for provider in result.provider_refs] == ["scancode"]


def test_permissive_detail_keeps_null_severity_and_no_finding():
    result = service(license_scan()).detail("scan-a", "assess-permissive")
    assert result.assessment.severity is None
    assert not result.assessment.manual_review_required
    assert result.assessment.finding_ids == [] and result.finding_refs == []


@pytest.mark.parametrize(("classification", "normalization_status", "expression", "reason"), [
    ("unknown", "canonical", "Unlicense", "unknown_license_review"),
    ("unknown", "invalid", None, "invalid_expression_or_identifier"),
    ("unknown", "license_ref", "LicenseRef-Internal", "license_reference_review"),
])
def test_unknown_invalid_and_license_ref_assessments_are_preserved(
    classification, normalization_status, expression, reason,
):
    data = inventory()
    assessment = data["assessments"][2]
    assessment.update(classification=classification, severity="medium", manual_review_required=True,
                      reason=reason, component_categories=[classification], finding_ids=[])
    normalized = data["licenses"][2]["normalization"]
    normalized.update(original_expression=expression, canonical_expression=expression,
                      status=normalization_status, manual_review_required=True, reason=reason,
                      license_ids=[expression] if expression else [])
    result = service(license_scan(inventory_data=data)).detail("scan-a", "assess-permissive")
    assert result.assessment.classification == classification
    assert result.assessment.severity == Severity.MEDIUM
    assert result.normalization.status == normalization_status
    assert result.normalization.canonical_expression == expression
    assert result.normalization.reason == reason


def test_unlocated_assessment_has_no_fabricated_license_or_location():
    result = service(license_scan()).detail("scan-a", "assess-unlocated")
    assert result.package.name == "Orphan"
    assert result.license is None and result.normalization is None and result.location is None
    assert [provider.name for provider in result.provider_refs] == ["ort"]


def test_missing_package_and_license_join_return_null_with_fixed_diagnostic():
    data = inventory()
    data["assessments"][0].update(package_id="missing", license_id="missing")
    result = service(license_scan(inventory_data=data)).detail("scan-a", "assess-strong")
    assert result.package is None and result.license is None and result.location is None
    assert "Some License inventory references could not be resolved." in result.diagnostics


def test_multiple_finding_ids_are_scoped_and_dangling_references_are_ignored():
    data = inventory()
    data["assessments"][0]["finding_ids"] = ["finding-strong", "finding-low", "wrong", "missing"]
    wrong = license_finding("wrong")
    wrong.category = FindingCategory.SECRET
    result = service(license_scan(
        inventory_data=data,
        findings=[license_finding("finding-strong"), license_finding("finding-low"), wrong],
    )).detail("scan-a", "assess-strong")
    assert [ref.finding_id for ref in result.finding_refs] == ["finding-strong", "finding-low"]
    assert result.assessment.finding_ids == ["finding-strong", "finding-low"]
    assert "Some referenced License findings were unavailable." in result.diagnostics


@pytest.mark.parametrize("status", list(ScanStatus))
def test_module_states_return_saved_inventory_without_http_failure(status):
    data = inventory(str(status))
    data["coverage"].update(inventory_complete=False, providers_complete=False,
                            assessment_complete=False)
    result = service(license_scan(status="partial", inventory_data=data)).overview("scan-a")
    assert result.status == status and result.items
    if status != ScanStatus.SUCCESS:
        assert result.diagnostics


def test_partial_inventory_preserves_dropped_records_and_safe_issue_codes():
    data = inventory("partial")
    data["coverage"].update(dropped_records=7, issues=["inventory_limit", "unlocated_package_review"])
    result = service(license_scan(status="partial", inventory_data=data)).overview("scan-a")
    assert result.coverage.dropped_records == 7
    assert result.coverage.issues == ["inventory_limit", "unlocated_package_review"]
    assert result.pagination.total == 4


def test_unknown_coverage_issue_is_not_reflected():
    marker = "arbitrary-exception-text-must-not-return"
    data = inventory("partial")
    data["coverage"]["issues"] = [marker]
    result = service(license_scan(inventory_data=data)).overview("scan-a")
    assert result.coverage.issues == ["unknown_inventory_issue"]
    assert marker not in result.model_dump_json()


def test_historical_scan_is_unavailable_not_clean_success():
    result = service(license_scan(include_inventory=False, findings=[])).overview("scan-a")
    assert result.status == ScanStatus.UNAVAILABLE and not result.inventory_available
    assert result.items == [] and result.summary.assessments == 0
    assert result.diagnostics[0] == "License inventory was not recorded for this scan."


@pytest.mark.parametrize("state", ["pending", "queued", "running", "scanning", "unknown"])
def test_unfinished_scan_is_rejected(state):
    with pytest.raises(ScanNotReady):
        service(license_scan(status=state)).overview("scan-a")


def test_missing_assessment_has_fixed_error():
    with pytest.raises(LicenseAssessmentNotFound):
        service(license_scan()).detail("scan-a", "missing")


def test_each_request_loads_the_complete_scan_once():
    repository = LicenseQueryRepository(SavedStore(license_scan()))
    query_service = LicenseQueryService(repository)
    assert query_service.overview("scan-a").pagination.total == 4
    assert repository.store.reads == 1
    assert query_service.detail("scan-a", "assess-strong").assessment.assessment_id == "assess-strong"
    assert repository.store.reads == 2


def test_service_does_not_mutate_persisted_result():
    saved = license_scan()
    before = deepcopy(saved)
    query_service = service(saved)
    query_service.overview("scan-a")
    query_service.detail("scan-a", "assess-strong")
    assert saved == before


def test_explicit_dtos_do_not_return_raw_metadata_or_evidence_details():
    marker = "raw-provider-or-parser-payload"
    saved = license_scan()
    saved.metadata["module_data"]["license"]["raw_json"] = marker
    saved.metadata["module_data"]["license"]["packages"][0]["raw"] = marker
    saved.metadata["module_data"]["license"]["providers"][0].update(
        stdout=marker, stderr=marker, command=marker, env=marker, raw_json=marker,
    )
    saved.findings[0].metadata["raw"] = marker
    saved.findings[0].evidence[0].details["raw"] = marker
    outputs = [service(saved).overview("scan-a"), service(saved).detail("scan-a", "assess-strong")]
    assert all(marker not in result.model_dump_json() for result in outputs)
    assert all("source_path" not in result.model_dump_json() for result in outputs)


def test_absolute_inventory_location_is_never_returned():
    data = inventory()
    data["licenses"][0]["location"]["path"] = "C:/private/target/LICENSE"
    with pytest.raises(LicenseQueryError, match="^License results could not be loaded$"):
        service(license_scan(inventory_data=data)).overview("scan-a")


def test_response_models_forbid_extra_and_hide_input():
    marker = "input-must-not-be-rendered"
    with pytest.raises(ValidationError) as error:
        LicenseLocationResponse(file_path="a", line=1, end_line=1, column_start=0, column_end=0,
                                raw=marker)
    assert marker not in str(error.value)


def test_service_never_opens_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("License query attempted network access")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    query_service = service(license_scan())
    assert query_service.overview("scan-a").pagination.total == 4
    assert query_service.detail("scan-a", "assess-strong").finding_refs


def test_damaged_saved_summary_is_safe_conversion_failure():
    data = inventory()
    data["summary"]["packages"] = -1
    with pytest.raises(LicenseQueryError, match="^License results could not be loaded$"):
        service(license_scan(inventory_data=data)).overview("scan-a")
