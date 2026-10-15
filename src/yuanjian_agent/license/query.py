from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from ..models import Finding, FindingCategory, ScanResult, Severity
from ..storage import ScanStore


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
SUPPORTED_INVENTORY_SCHEMA = 1
SEVERITY_RANK = {severity: rank for rank, severity in enumerate(Severity)}


class LicenseQueryError(Exception):
    """Fixed public errors without stored values, identifiers, or exception text."""

    status_code = 500
    detail = "License results could not be loaded"

    def __init__(self) -> None:
        super().__init__(self.detail)


class ScanNotFound(LicenseQueryError):
    status_code = 404
    detail = "Scan not found"


class LicenseAssessmentNotFound(LicenseQueryError):
    status_code = 404
    detail = "License assessment not found in this scan"


class ScanNotReady(LicenseQueryError):
    status_code = 409
    detail = "Scan results are not final"


class UnsupportedLicenseSchema(LicenseQueryError):
    status_code = 409
    detail = "License inventory schema is not supported"


class InvalidLicenseQuery(LicenseQueryError):
    status_code = 422
    detail = "Invalid License query parameters"


@dataclass(frozen=True, slots=True)
class LicenseQuery:
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    classification: str | None = field(default=None, repr=False)
    severity: Severity | None = None
    manual_review_required: bool | None = None
    package_name: str | None = field(default=None, repr=False)
    license_expression: str | None = field(default=None, repr=False)
    file_path: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (type(self.page) is not int or self.page < 1
                or type(self.page_size) is not int or not 1 <= self.page_size <= MAX_PAGE_SIZE):
            raise InvalidLicenseQuery()
        if self.severity is not None and not isinstance(self.severity, Severity):
            raise InvalidLicenseQuery()
        if self.manual_review_required is not None and type(self.manual_review_required) is not bool:
            raise InvalidLicenseQuery()
        for value in (
            self.classification, self.package_name, self.license_expression, self.file_path,
        ):
            if value is not None and (
                not isinstance(value, str) or not value.strip() or len(value) > 256
            ):
                raise InvalidLicenseQuery()


@dataclass(frozen=True, slots=True)
class LicenseInventoryIndex:
    scan: ScanResult = field(repr=False)
    available: bool
    inventory: dict[str, Any] = field(repr=False)
    packages_by_id: dict[str, dict[str, Any]] = field(repr=False)
    licenses_by_id: dict[str, dict[str, Any]] = field(repr=False)
    assessments_by_id: dict[str, dict[str, Any]] = field(repr=False)
    findings_by_id: dict[str, Finding] = field(repr=False)
    missing_references: bool = False
    dangling_finding_references: bool = False


@dataclass(frozen=True, slots=True)
class LicensePage:
    items: tuple[dict[str, Any], ...] = field(repr=False)
    total: int


def _identifier(value: Any, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value or len(value) > 256:
        raise LicenseQueryError()
    return value


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise LicenseQueryError()
    return value


def _index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        identifier = _identifier(row.get("id"))
        if identifier in result:
            raise LicenseQueryError()
        result[identifier] = row
    return result


def safe_location_path(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise LicenseQueryError()
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value)
    if windows.is_absolute() or posix.is_absolute() or windows.drive or ".." in windows.parts:
        raise LicenseQueryError()
    return value


def package_for(index: LicenseInventoryIndex, assessment: dict[str, Any]) -> dict[str, Any] | None:
    package_id = _identifier(assessment.get("package_id"), optional=True)
    return index.packages_by_id.get(package_id) if package_id is not None else None


def license_for(index: LicenseInventoryIndex, assessment: dict[str, Any]) -> dict[str, Any] | None:
    license_id = _identifier(assessment.get("license_id"), optional=True)
    return index.licenses_by_id.get(license_id) if license_id is not None else None


def normalization_for(license_row: dict[str, Any] | None) -> dict[str, Any] | None:
    if license_row is None:
        return None
    normalization = license_row.get("normalization")
    if normalization is None:
        return None
    if not isinstance(normalization, dict):
        raise LicenseQueryError()
    return normalization


def location_path(license_row: dict[str, Any] | None) -> str | None:
    if license_row is None:
        return None
    location = license_row.get("location")
    if location is None:
        return None
    if not isinstance(location, dict):
        raise LicenseQueryError()
    return safe_location_path(location.get("path"))


def _optional_text(value: Any, *, maximum: int = 4096) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum:
        raise LicenseQueryError()
    return value


def _assessment_sort_key(index: LicenseInventoryIndex, assessment: dict[str, Any]) -> tuple:
    raw_severity = assessment.get("severity")
    if raw_severity is None:
        severity_key = 1
    else:
        try:
            severity_key = -SEVERITY_RANK[Severity(raw_severity)]
        except (TypeError, ValueError, KeyError):
            raise LicenseQueryError() from None
    manual = assessment.get("manual_review_required")
    if type(manual) is not bool:
        raise LicenseQueryError()
    package = package_for(index, assessment)
    license_row = license_for(index, assessment)
    normalization = normalization_for(license_row)
    package_name = _optional_text(package.get("name") if package else None, maximum=1024) or ""
    canonical = _optional_text(
        normalization.get("canonical_expression") if normalization else None
    ) or _optional_text(normalization.get("original_expression") if normalization else None) or ""
    return (
        severity_key, -int(manual), package_name.casefold(), canonical.casefold(),
        (location_path(license_row) or "").casefold(), _identifier(assessment.get("id")),
    )


class LicenseQueryRepository:
    """One persisted ScanResult read followed by bounded in-memory joins."""

    def __init__(self, store: ScanStore) -> None:
        self.store = store

    def load(self, scan_id: str) -> ScanResult:
        try:
            scan = self.store.get(scan_id)
        except KeyError as error:
            if error.args == (f"Unknown scan: {scan_id}",):
                raise ScanNotFound() from None
            raise LicenseQueryError() from None
        if scan.id != scan_id:
            raise LicenseQueryError()
        return scan

    @staticmethod
    def inventory(scan: ScanResult) -> LicenseInventoryIndex:
        if not isinstance(scan.metadata, dict):
            raise LicenseQueryError()
        module_data = scan.metadata.get("module_data")
        if module_data is None or (isinstance(module_data, dict) and "license" not in module_data):
            return LicenseInventoryIndex(scan, False, {}, {}, {}, {}, {})
        if not isinstance(module_data, dict):
            raise LicenseQueryError()
        inventory = module_data.get("license")
        if not isinstance(inventory, dict):
            raise LicenseQueryError()
        schema_version = inventory.get("schema_version")
        if type(schema_version) is int and schema_version != SUPPORTED_INVENTORY_SCHEMA:
            raise UnsupportedLicenseSchema()
        if type(schema_version) is not int:
            raise LicenseQueryError()
        packages = _index(_rows(inventory.get("packages")))
        licenses = _index(_rows(inventory.get("licenses")))
        assessments = _index(_rows(inventory.get("assessments")))
        _rows(inventory.get("dependencies"))
        _rows(inventory.get("providers"))
        if not isinstance(inventory.get("summary"), dict) or not isinstance(inventory.get("coverage"), dict):
            raise LicenseQueryError()
        findings: dict[str, Finding] = {}
        for finding in scan.findings:
            if finding.category != FindingCategory.LICENSE:
                continue
            if finding.id in findings:
                raise LicenseQueryError()
            findings[finding.id] = finding
        missing = False
        dangling = False
        for assessment in assessments.values():
            package_id = _identifier(assessment.get("package_id"), optional=True)
            license_id = _identifier(assessment.get("license_id"), optional=True)
            if package_id is not None and package_id not in packages:
                missing = True
            if license_id is not None and license_id not in licenses:
                missing = True
            finding_ids = assessment.get("finding_ids")
            if not isinstance(finding_ids, list):
                raise LicenseQueryError()
            for finding_id in finding_ids:
                identifier = _identifier(finding_id)
                if identifier not in findings:
                    dangling = True
        return LicenseInventoryIndex(
            scan, True, inventory, packages, licenses, assessments, findings, missing, dangling,
        )

    @staticmethod
    def page(index: LicenseInventoryIndex, query: LicenseQuery) -> LicensePage:
        selected = []
        for assessment in index.assessments_by_id.values():
            package = package_for(index, assessment)
            license_row = license_for(index, assessment)
            normalization = normalization_for(license_row)
            package_name = _optional_text(package.get("name") if package else None, maximum=1024)
            expression = _optional_text(
                normalization.get("canonical_expression") if normalization else None
            ) or _optional_text(normalization.get("original_expression") if normalization else None)
            classification = _optional_text(assessment.get("classification"), maximum=128)
            manual = assessment.get("manual_review_required")
            if type(manual) is not bool:
                raise LicenseQueryError()
            severity = assessment.get("severity")
            if severity is not None:
                try:
                    severity = Severity(severity)
                except (TypeError, ValueError):
                    raise LicenseQueryError() from None
            path = location_path(license_row)
            if ((query.classification is None or classification == query.classification)
                    and (query.severity is None or severity == query.severity)
                    and (query.manual_review_required is None or manual is query.manual_review_required)
                    and (query.package_name is None or (
                        package_name is not None and query.package_name.casefold() in package_name.casefold()
                    ))
                    and (query.license_expression is None or (
                        expression is not None
                        and query.license_expression.casefold() in expression.casefold()
                    ))
                    and (query.file_path is None or (
                        path is not None and query.file_path.casefold() in path.casefold()
                    ))):
                selected.append(assessment)
        selected.sort(key=lambda item: _assessment_sort_key(index, item))
        offset = (query.page - 1) * query.page_size
        return LicensePage(tuple(selected[offset:offset + query.page_size]), len(selected))

    @staticmethod
    def find(index: LicenseInventoryIndex, assessment_id: str) -> dict[str, Any]:
        assessment = index.assessments_by_id.get(assessment_id)
        if assessment is None:
            raise LicenseAssessmentNotFound()
        return assessment
