from copy import deepcopy

import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.models import (
    Evidence, Finding, FindingCategory, ScanResult, Severity, SourceSpan,
)
from yuanjian_agent.license.query import (
    InvalidLicenseQuery, LicenseAssessmentNotFound, LicenseQuery, LicenseQueryError,
    LicenseQueryRepository, ScanNotFound, UnsupportedLicenseSchema,
)
from yuanjian_agent.storage import ScanStore


def provenance(provider="scancode", origin_provider="scancode", source_kind="package"):
    return {
        "provider": provider, "provider_version": "32.5.0", "origin_provider": origin_provider,
        "source_kind": source_kind, "scan_mode": "package",
        "origin_version": "32.5.0",
    }


def normalization(expression, status="canonical", reason="canonicalized", exceptions=None):
    return {
        "original_expression": expression, "canonical_expression": expression,
        "status": status, "manual_review_required": status != "canonical",
        "reason": reason, "license_ids": [expression] if expression else [],
        "exception_ids": list(exceptions or []),
    }


def license_finding(identifier, severity=Severity.HIGH, title="License terms require manual review"):
    return Finding(
        id=identifier, signature=identifier, category=FindingCategory.LICENSE,
        rule_id="LICENSE_STRONG_COPYLEFT_REVIEW", severity=severity, confidence=0.9,
        title=title, evidence=[Evidence(SourceSpan("src/license.py", 3, 3), "withheld")],
        rationale=[], remediation=[],
    )


def inventory(status="success"):
    packages = [
        {"id": "pkg-alpha", "name": "Alpha", "version": "1.0", "purl": "pkg:pypi/alpha@1.0",
         "identifier": "PyPI::alpha:1.0", "provenance": [provenance()]},
        {"id": "pkg-beta", "name": "Beta", "version": None, "purl": "pkg:pypi/beta",
         "identifier": None, "provenance": [provenance("ort", "scancode")]},
        {"id": "pkg-orphan", "name": "Orphan", "version": None, "purl": None,
         "identifier": "PyPI::orphan:", "provenance": [provenance("ort", "ort")]},
    ]
    licenses = [
        {"id": "lic-strong", "package_id": "pkg-alpha",
         "location": {"path": "src/license.py", "start_line": 3, "end_line": 3,
                      "start_column": 0, "end_column": 0},
         "source": "scancode", "source_kind": "detected_license", "source_scope": "file",
         "location_precision": "line", "provenance": [provenance()],
         "normalization": normalization("GPL-3.0-only")},
        {"id": "lic-network", "package_id": "pkg-beta",
         "location": {"path": "requirements.txt", "start_line": 2, "end_line": 2,
                      "start_column": 0, "end_column": 0},
         "source": "ort", "source_kind": "declared_license", "source_scope": "package",
         "location_precision": "line", "provenance": [provenance("ort", "scancode")],
         "normalization": normalization("AGPL-3.0-only")},
        {"id": "lic-permissive", "package_id": "pkg-beta",
         "location": {"path": "LICENSE", "start_line": 1, "end_line": 1,
                      "start_column": 0, "end_column": 0},
         "source": "scancode", "source_kind": "detected_license", "source_scope": "file",
         "location_precision": "line", "provenance": [provenance()],
         "normalization": normalization("MIT")},
    ]
    assessments = [
        {"id": "assess-strong", "license_id": "lic-strong", "package_id": "pkg-alpha",
         "classification": "strong_copyleft", "severity": "high", "manual_review_required": True,
         "reason": "strong_copyleft_review", "component_categories": ["strong_copyleft"],
         "alternative_terms": False, "exception_review": False, "policy_status": "success",
         "finding_ids": ["finding-strong"]},
        {"id": "assess-network", "license_id": "lic-network", "package_id": "pkg-beta",
         "classification": "network_copyleft", "severity": "high", "manual_review_required": True,
         "reason": "network_copyleft_review", "component_categories": ["network_copyleft"],
         "alternative_terms": False, "exception_review": False, "policy_status": "success",
         "finding_ids": ["finding-network"]},
        {"id": "assess-permissive", "license_id": "lic-permissive", "package_id": "pkg-beta",
         "classification": "permissive", "severity": None, "manual_review_required": False,
         "reason": "catalog_permissive", "component_categories": ["permissive"],
         "alternative_terms": False, "exception_review": False, "policy_status": "success",
         "finding_ids": []},
        {"id": "assess-unlocated", "license_id": None, "package_id": "pkg-orphan",
         "classification": "unknown", "severity": "medium", "manual_review_required": True,
         "reason": "no_located_license_fact", "component_categories": [],
         "alternative_terms": False, "exception_review": False, "policy_status": "unavailable",
         "finding_ids": []},
    ]
    return {
        "schema_version": 1, "policy_name": "default", "policy_version": "1",
        "catalog_version": "1", "normalizer_version": "1", "packaging_version": "26.3",
        "summary": {"packages": 3, "dependencies": 1, "licenses": 3, "assessments": 4,
                    "manual_review_required": 3,
                    "by_classification": {"strong_copyleft": 1, "network_copyleft": 1,
                                          "permissive": 1, "unknown": 1}},
        "coverage": {"status": status, "inventory_complete": status == "success",
                     "providers_complete": status == "success", "assessment_complete": status == "success",
                     "dropped_records": 0, "issues": []},
        "providers": [
            {"name": "scancode", "status": "success", "reason": "completed",
             "version": "32.5.0", "execution_mode": "process"},
            {"name": "ort", "status": "disabled", "reason": "disabled",
             "version": None, "execution_mode": "result-import"},
        ],
        "packages": packages,
        "dependencies": [{"id": "dep-1", "package_id": "pkg-alpha",
                          "manifest_path": "requirements.txt", "relationship": "declared",
                          "scope": "runtime", "requirement": "alpha==1.0",
                          "from_package": None, "provenance": [provenance()]}],
        "licenses": licenses, "assessments": assessments,
    }


def license_scan(identifier="scan-a", *, status="completed", inventory_data=None, findings=None,
                 include_inventory=True):
    metadata = {"scanners": {"license": {"status": "success", "providers": {}}}}
    if include_inventory:
        metadata["module_data"] = {"license": inventory_data or inventory()}
    return ScanResult(
        identifier, "synthetic", "C:/absolute/source/must-not-return", "2026-09-10", status, "1",
        findings=list(findings if findings is not None else [
            license_finding("finding-strong"), license_finding("finding-network")
        ]), metadata=metadata,
    )


@pytest.fixture
def store(tmp_path):
    return ScanStore(Settings(data_dir=tmp_path / "state"))


def test_repository_loads_v1_and_builds_scoped_indexes(store):
    store.save(license_scan())
    repository = LicenseQueryRepository(store)
    index = repository.inventory(repository.load("scan-a"))
    assert index.available and set(index.packages_by_id) == {"pkg-alpha", "pkg-beta", "pkg-orphan"}
    assert set(index.licenses_by_id) == {"lic-strong", "lic-network", "lic-permissive"}
    assert set(index.assessments_by_id) == {
        "assess-strong", "assess-network", "assess-permissive", "assess-unlocated"
    }
    assert set(index.findings_by_id) == {"finding-strong", "finding-network"}


def test_repository_missing_scan_has_fixed_error(store):
    with pytest.raises(ScanNotFound, match="^Scan not found$"):
        LicenseQueryRepository(store).load("not-present")


def test_deserialization_key_error_is_not_misreported_as_missing_scan():
    class BrokenStore:
        def get(self, scan_id):
            raise KeyError("damaged stored payload")

    with pytest.raises(LicenseQueryError, match="^License results could not be loaded$"):
        LicenseQueryRepository(BrokenStore()).load("scan-a")


def test_assessment_lookup_is_scoped_to_loaded_scan(store):
    first = license_scan("a")
    second_inventory = inventory()
    second_inventory["assessments"][0]["id"] = "only-b"
    store.save(first)
    store.save(license_scan("b", inventory_data=second_inventory))
    repository = LicenseQueryRepository(store)
    with pytest.raises(LicenseAssessmentNotFound):
        repository.find(repository.inventory(repository.load("a")), "only-b")
    assert repository.find(repository.inventory(repository.load("b")), "only-b")["license_id"] == "lic-strong"


def test_same_assessment_id_can_exist_in_two_scans(store):
    second = inventory()
    second["assessments"][0]["license_id"] = "lic-network"
    store.save(license_scan("a"))
    store.save(license_scan("b", inventory_data=second))
    repository = LicenseQueryRepository(store)
    assert repository.find(repository.inventory(repository.load("a")), "assess-strong")["license_id"] == "lic-strong"
    assert repository.find(repository.inventory(repository.load("b")), "assess-strong")["license_id"] == "lic-network"


def test_missing_package_license_and_dangling_finding_are_tolerated():
    data = inventory()
    data["assessments"][0].update(package_id="missing-package", license_id="missing-license",
                                  finding_ids=["missing", "not-license"])
    scan = license_scan(inventory_data=data, findings=[Finding(
        "not-license", "x", FindingCategory.SECRET, "secret.fixture", Severity.HIGH, .8, "secret",
        [Evidence(SourceSpan("a", 1, 1), "****")], [], [],
    )])
    index = LicenseQueryRepository.inventory(scan)
    assert index.missing_references and index.dangling_finding_references
    assert LicenseQueryRepository.find(index, "assess-strong")["id"] == "assess-strong"


@pytest.mark.parametrize(("options", "expected"), [
    ({"classification": "permissive"}, ["assess-permissive"]),
    ({"severity": Severity.HIGH}, ["assess-strong", "assess-network"]),
    ({"manual_review_required": False}, ["assess-permissive"]),
    ({"package_name": "ALP"}, ["assess-strong"]),
    ({"license_expression": "agpl"}, ["assess-network"]),
    ({"file_path": "LICENSE.PY"}, ["assess-strong"]),
])
def test_all_filters(options, expected):
    index = LicenseQueryRepository.inventory(license_scan())
    page = LicenseQueryRepository.page(index, LicenseQuery(page_size=100, **options))
    assert [row["id"] for row in page.items] == expected


def test_filters_are_combined_with_and():
    index = LicenseQueryRepository.inventory(license_scan())
    page = LicenseQueryRepository.page(index, LicenseQuery(
        severity=Severity.HIGH, manual_review_required=True, package_name="beta",
        license_expression="AGPL", file_path="requirements", classification="network_copyleft",
    ))
    assert [row["id"] for row in page.items] == ["assess-network"]


def test_risk_first_sort_pagination_is_stable_and_null_severity_is_last():
    index = LicenseQueryRepository.inventory(license_scan())
    expected = ["assess-strong", "assess-network", "assess-unlocated", "assess-permissive"]
    first = LicenseQueryRepository.page(index, LicenseQuery(page_size=100))
    second = LicenseQueryRepository.page(index, LicenseQuery(page_size=100))
    assert [row["id"] for row in first.items] == expected
    assert first == second
    page = LicenseQueryRepository.page(index, LicenseQuery(page=2, page_size=2))
    assert page.total == 4 and [row["id"] for row in page.items] == expected[2:]


def test_query_does_not_mutate_inventory():
    scan = license_scan()
    before = deepcopy(scan)
    index = LicenseQueryRepository.inventory(scan)
    LicenseQueryRepository.page(index, LicenseQuery())
    assert scan == before


@pytest.mark.parametrize("options", [
    {"page": 0}, {"page": 1.5}, {"page_size": 0}, {"page_size": 101},
    {"severity": "high"}, {"manual_review_required": 1}, {"classification": ""},
    {"package_name": " "}, {"license_expression": "x" * 257}, {"file_path": ""},
])
def test_query_rejects_invalid_parameters(options):
    with pytest.raises(InvalidLicenseQuery):
        LicenseQuery(**options)


def test_historical_scan_without_inventory_is_explicitly_unavailable():
    index = LicenseQueryRepository.inventory(license_scan(include_inventory=False))
    assert not index.available and not index.assessments_by_id


def test_future_schema_is_not_read_as_v1():
    data = inventory()
    data["schema_version"] = 2
    with pytest.raises(UnsupportedLicenseSchema, match="schema is not supported"):
        LicenseQueryRepository.inventory(license_scan(inventory_data=data))


@pytest.mark.parametrize("schema", [None, "1", True, 1.0])
def test_damaged_schema_is_a_safe_conversion_error(schema):
    data = inventory()
    data["schema_version"] = schema
    with pytest.raises(LicenseQueryError, match="^License results could not be loaded$"):
        LicenseQueryRepository.inventory(license_scan(inventory_data=data))
