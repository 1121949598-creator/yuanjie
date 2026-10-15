from __future__ import annotations

from typing import Any

from ..core.scanner import ScanStatus
from ..models import Severity
from .query import (
    LicenseInventoryIndex, LicenseQuery, LicenseQueryError, LicenseQueryRepository, ScanNotReady,
    license_for, normalization_for, package_for, safe_location_path,
)
from .schemas import (
    LicenseAssessmentItem, LicenseAssessmentResponse, LicenseCoverageResponse,
    LicenseDetailResponse, LicenseFindingReferenceResponse, LicenseInventoryMetadataResponse,
    LicenseLocationResponse, LicenseNormalizationResponse, LicenseObservationResponse,
    LicenseOverviewResponse, LicensePackageResponse, LicensePaginationResponse,
    LicenseProviderResponse, LicenseSummaryResponse,
)


_FINAL_SCAN_STATUSES = frozenset({"completed", "partial", "failed", "unavailable"})
_STATUS_DIAGNOSTICS = {
    ScanStatus.SUCCESS: (),
    ScanStatus.PARTIAL: ("License coverage is partial; available inventory is retained.",),
    ScanStatus.FAILED: ("License processing failed; this result does not establish a clean scan.",),
    ScanStatus.DISABLED: ("License processing was disabled for this scan.",),
    ScanStatus.UNAVAILABLE: ("License coverage is unavailable.",),
    ScanStatus.NOT_APPLICABLE: ("License processing was recorded as not applicable; no clearance is implied.",),
}
_SAFE_ISSUES = frozenset({
    "invalid_package_projection", "invalid_dependency_projection", "invalid_fact_projection",
    "inventory_limit", "unlocated_package_review",
})


def _text(value: Any, *, optional: bool = False, maximum: int = 4096) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise LicenseQueryError()
    return value


def _optional_text(value: Any, *, maximum: int = 4096) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum:
        raise LicenseQueryError()
    return value


def _integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise LicenseQueryError()
    return value


def _boolean(value: Any) -> bool:
    if type(value) is not bool:
        raise LicenseQueryError()
    return value


def _string_list(value: Any, *, maximum: int = 256) -> list[str]:
    if not isinstance(value, list):
        raise LicenseQueryError()
    result = []
    for item in value:
        text = _text(item, maximum=maximum)
        result.append(text)
    return result


class LicenseQueryService:
    def __init__(self, repository: LicenseQueryRepository) -> None:
        self.repository = repository

    def _load(self, scan_id: str) -> LicenseInventoryIndex:
        scan = self.repository.load(scan_id)
        if scan.status not in _FINAL_SCAN_STATUSES:
            raise ScanNotReady()
        return self.repository.inventory(scan)

    @staticmethod
    def _inventory_metadata(index: LicenseInventoryIndex) -> LicenseInventoryMetadataResponse:
        if not index.available:
            return LicenseInventoryMetadataResponse()
        inventory = index.inventory
        return LicenseInventoryMetadataResponse(
            schema_version=inventory["schema_version"],
            policy_name=_optional_text(inventory.get("policy_name"), maximum=128),
            policy_version=_optional_text(inventory.get("policy_version"), maximum=128),
            catalog_version=_optional_text(inventory.get("catalog_version"), maximum=128),
            normalizer_version=_optional_text(inventory.get("normalizer_version"), maximum=128),
            packaging_version=_optional_text(inventory.get("packaging_version"), maximum=128),
        )

    @staticmethod
    def _coverage(index: LicenseInventoryIndex) -> tuple[LicenseCoverageResponse, list[str]]:
        if not index.available:
            coverage = LicenseCoverageResponse(
                status=ScanStatus.UNAVAILABLE, inventory_complete=False, providers_complete=False,
                assessment_complete=False, dropped_records=0, issues=[],
            )
            diagnostics = ["License inventory was not recorded for this scan."]
        else:
            raw = index.inventory["coverage"]
            try:
                status = ScanStatus(raw.get("status"))
            except (TypeError, ValueError):
                raise LicenseQueryError() from None
            raw_issues = raw.get("issues")
            if not isinstance(raw_issues, list):
                raise LicenseQueryError()
            issues = []
            unknown_issue = False
            for issue in raw_issues:
                if issue in _SAFE_ISSUES:
                    if issue not in issues:
                        issues.append(issue)
                else:
                    unknown_issue = True
            if unknown_issue:
                issues.append("unknown_inventory_issue")
            coverage = LicenseCoverageResponse(
                status=status,
                inventory_complete=_boolean(raw.get("inventory_complete")),
                providers_complete=_boolean(raw.get("providers_complete")),
                assessment_complete=_boolean(raw.get("assessment_complete")),
                dropped_records=_integer(raw.get("dropped_records")), issues=issues,
            )
            diagnostics = list(_STATUS_DIAGNOSTICS[status])
            if issues:
                diagnostics.append("The saved License inventory reports incomplete coverage.")
        if index.missing_references:
            diagnostics.append("Some License inventory references could not be resolved.")
        if index.dangling_finding_references:
            diagnostics.append("Some referenced License findings were unavailable.")
        if index.scan.warnings:
            diagnostics.append("The saved scan contains warnings; review overall scan coverage.")
        return coverage, diagnostics

    @staticmethod
    def _summary(index: LicenseInventoryIndex) -> LicenseSummaryResponse:
        if not index.available:
            return LicenseSummaryResponse(
                packages=0, dependencies=0, licenses=0, assessments=0,
                manual_review_required=0, by_classification={},
            )
        raw = index.inventory["summary"]
        by_classification = raw.get("by_classification")
        if not isinstance(by_classification, dict):
            raise LicenseQueryError()
        projected = {}
        for key, value in by_classification.items():
            projected[_text(key, maximum=128)] = _integer(value)
        return LicenseSummaryResponse(
            packages=_integer(raw.get("packages")), dependencies=_integer(raw.get("dependencies")),
            licenses=_integer(raw.get("licenses")), assessments=_integer(raw.get("assessments")),
            manual_review_required=_integer(raw.get("manual_review_required")),
            by_classification=dict(sorted(projected.items())),
        )

    @staticmethod
    def _providers(index: LicenseInventoryIndex) -> list[LicenseProviderResponse]:
        if not index.available:
            return []
        providers = []
        for raw in index.inventory["providers"]:
            try:
                status = ScanStatus(raw.get("status"))
            except (AttributeError, TypeError, ValueError):
                raise LicenseQueryError() from None
            providers.append(LicenseProviderResponse(
                name=_text(raw.get("name"), maximum=128), status=status,
                reason=_optional_text(raw.get("reason"), maximum=128),
                version=_optional_text(raw.get("version"), maximum=128),
                execution_mode=_text(raw.get("execution_mode"), maximum=128),
                scan_error_count=_integer(raw.get("scan_error_count", 0)),
            ))
        return providers

    @staticmethod
    def _location(license_row: dict[str, Any] | None) -> LicenseLocationResponse | None:
        if license_row is None or license_row.get("location") is None:
            return None
        raw = license_row["location"]
        if not isinstance(raw, dict):
            raise LicenseQueryError()
        path = _text(raw.get("path"), maximum=4096)
        path = safe_location_path(path)
        line = raw.get("start_line")
        end_line = raw.get("end_line")
        start_column = raw.get("start_column", 0)
        end_column = raw.get("end_column", 0)
        if (type(line) is not int or type(end_line) is not int or type(start_column) is not int
                or type(end_column) is not int or line < 1 or end_line < line
                or start_column < 0 or end_column < 0):
            raise LicenseQueryError()
        return LicenseLocationResponse(
            file_path=path, line=line, end_line=end_line,
            column_start=start_column, column_end=end_column,
        )

    @staticmethod
    def _normalization(raw: dict[str, Any] | None) -> LicenseNormalizationResponse | None:
        if raw is None:
            return None
        return LicenseNormalizationResponse(
            original_expression=_optional_text(raw.get("original_expression")),
            canonical_expression=_optional_text(raw.get("canonical_expression")),
            status=_text(raw.get("status"), maximum=128),
            manual_review_required=_boolean(raw.get("manual_review_required")),
            reason=_text(raw.get("reason"), maximum=128),
            license_ids=_string_list(raw.get("license_ids")),
            exception_ids=_string_list(raw.get("exception_ids")),
        )

    @staticmethod
    def _valid_finding_ids(index: LicenseInventoryIndex, assessment: dict[str, Any]) -> list[str]:
        identifiers = _string_list(assessment.get("finding_ids"))
        return list(dict.fromkeys(identifier for identifier in identifiers if identifier in index.findings_by_id))

    def _assessment(
        self, index: LicenseInventoryIndex, raw: dict[str, Any], finding_ids: list[str],
    ) -> LicenseAssessmentResponse:
        severity = raw.get("severity")
        try:
            severity_value = Severity(severity) if severity is not None else None
        except (TypeError, ValueError):
            raise LicenseQueryError() from None
        return LicenseAssessmentResponse(
            assessment_id=_text(raw.get("id"), maximum=256),
            license_id=_optional_text(raw.get("license_id"), maximum=256),
            package_id=_optional_text(raw.get("package_id"), maximum=256),
            classification=_text(raw.get("classification"), maximum=128),
            severity=severity_value,
            manual_review_required=_boolean(raw.get("manual_review_required")),
            reason=_text(raw.get("reason"), maximum=128),
            component_categories=_string_list(raw.get("component_categories"), maximum=128),
            alternative_terms=_boolean(raw.get("alternative_terms")),
            exception_review=_boolean(raw.get("exception_review")),
            policy_status=_text(raw.get("policy_status"), maximum=128), finding_ids=finding_ids,
        )

    def _item(self, index: LicenseInventoryIndex, raw: dict[str, Any]) -> LicenseAssessmentItem:
        package = package_for(index, raw)
        license_row = license_for(index, raw)
        normalization = self._normalization(normalization_for(license_row))
        finding_ids = self._valid_finding_ids(index, raw)
        assessment = self._assessment(index, raw, finding_ids)
        return LicenseAssessmentItem(
            **assessment.model_dump(),
            package_name=_optional_text(package.get("name"), maximum=1024) if package else None,
            package_version=_optional_text(package.get("version"), maximum=1024) if package else None,
            package_purl=_optional_text(package.get("purl"), maximum=2048) if package else None,
            original_expression=normalization.original_expression if normalization else None,
            canonical_expression=normalization.canonical_expression if normalization else None,
            normalization_status=normalization.status if normalization else None,
            location=self._location(license_row),
            source=_optional_text(license_row.get("source"), maximum=128) if license_row else None,
            source_kind=_optional_text(license_row.get("source_kind"), maximum=128) if license_row else None,
            source_scope=_optional_text(license_row.get("source_scope"), maximum=128) if license_row else None,
            finding_count=len(finding_ids),
        )

    @staticmethod
    def _package(raw: dict[str, Any] | None) -> LicensePackageResponse | None:
        if raw is None:
            return None
        return LicensePackageResponse(
            id=_text(raw.get("id"), maximum=256), name=_text(raw.get("name"), maximum=1024),
            version=_optional_text(raw.get("version"), maximum=1024),
            purl=_optional_text(raw.get("purl"), maximum=2048),
            identifier=_optional_text(raw.get("identifier"), maximum=2048),
        )

    @staticmethod
    def _license(raw: dict[str, Any] | None) -> LicenseObservationResponse | None:
        if raw is None:
            return None
        return LicenseObservationResponse(
            id=_text(raw.get("id"), maximum=256),
            package_id=_optional_text(raw.get("package_id"), maximum=256),
            source=_optional_text(raw.get("source"), maximum=128),
            source_kind=_optional_text(raw.get("source_kind"), maximum=128),
            source_scope=_optional_text(raw.get("source_scope"), maximum=128),
            location_precision=_optional_text(raw.get("location_precision"), maximum=128),
        )

    def _provider_refs(
        self, index: LicenseInventoryIndex, package: dict[str, Any] | None,
        license_row: dict[str, Any] | None,
    ) -> list[LicenseProviderResponse]:
        names = set()
        for row in (license_row, package):
            if row is None:
                continue
            provenance = row.get("provenance", [])
            if not isinstance(provenance, list):
                raise LicenseQueryError()
            for item in provenance:
                if not isinstance(item, dict):
                    raise LicenseQueryError()
                for key in ("provider", "origin_provider"):
                    value = item.get(key)
                    if value is not None:
                        names.add(_text(value, maximum=128))
        return [provider for provider in self._providers(index) if provider.name in names]

    def overview(self, scan_id: str, query: LicenseQuery | None = None) -> LicenseOverviewResponse:
        query = query or LicenseQuery()
        index = self._load(scan_id)
        page = self.repository.page(index, query)
        coverage, diagnostics = self._coverage(index)
        return LicenseOverviewResponse(
            scan_id=index.scan.id, status=coverage.status, scan_status=index.scan.status,
            diagnostics=diagnostics, inventory_available=index.available,
            inventory=self._inventory_metadata(index), coverage=coverage, summary=self._summary(index),
            providers=self._providers(index),
            pagination=LicensePaginationResponse(page=query.page, page_size=query.page_size, total=page.total),
            items=[self._item(index, assessment) for assessment in page.items],
        )

    def detail(self, scan_id: str, assessment_id: str) -> LicenseDetailResponse:
        index = self._load(scan_id)
        raw = self.repository.find(index, assessment_id)
        package = package_for(index, raw)
        license_row = license_for(index, raw)
        finding_ids = self._valid_finding_ids(index, raw)
        coverage, diagnostics = self._coverage(index)
        finding_refs = [LicenseFindingReferenceResponse(
            finding_id=identifier, rule_id=index.findings_by_id[identifier].rule_id,
            severity=index.findings_by_id[identifier].severity,
            title=index.findings_by_id[identifier].title,
        ) for identifier in finding_ids]
        return LicenseDetailResponse(
            scan_id=index.scan.id, status=coverage.status, scan_status=index.scan.status,
            diagnostics=diagnostics, assessment=self._assessment(index, raw, finding_ids),
            package=self._package(package), license=self._license(license_row),
            normalization=self._normalization(normalization_for(license_row)),
            location=self._location(license_row), finding_refs=finding_refs,
            provider_refs=self._provider_refs(index, package, license_row),
        )
