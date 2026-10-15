from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..core.scanner import ScanStatus
from ..models import Severity
from .query import MAX_PAGE_SIZE


class LicenseResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class LicenseErrorResponse(LicenseResponseModel):
    detail: str


class LicenseInventoryMetadataResponse(LicenseResponseModel):
    schema_version: int | None = None
    policy_name: str | None = None
    policy_version: str | None = None
    catalog_version: str | None = None
    normalizer_version: str | None = None
    packaging_version: str | None = None


class LicenseCoverageResponse(LicenseResponseModel):
    status: ScanStatus
    inventory_complete: bool
    providers_complete: bool
    assessment_complete: bool
    dropped_records: int = Field(ge=0)
    issues: list[str]


class LicenseSummaryResponse(LicenseResponseModel):
    packages: int = Field(ge=0)
    dependencies: int = Field(ge=0)
    licenses: int = Field(ge=0)
    assessments: int = Field(ge=0)
    manual_review_required: int = Field(ge=0)
    by_classification: dict[str, int]


class LicensePaginationResponse(LicenseResponseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)
    total: int = Field(ge=0, description="Number of assessments after filters, before pagination")


class LicenseLocationResponse(LicenseResponseModel):
    file_path: str = Field(description="Saved relative path")
    line: int = Field(ge=1, description="1-based start line")
    end_line: int = Field(ge=1, description="1-based end line")
    column_start: int = Field(ge=0, description="0-based start column")
    column_end: int = Field(ge=0, description="Exclusive 0-based end column")


class LicenseProviderResponse(LicenseResponseModel):
    name: str
    status: ScanStatus
    reason: str | None
    version: str | None
    execution_mode: str
    scan_error_count: int = Field(default=0, ge=0)


class LicenseNormalizationResponse(LicenseResponseModel):
    original_expression: str | None
    canonical_expression: str | None
    status: str
    manual_review_required: bool
    reason: str
    license_ids: list[str]
    exception_ids: list[str]


class LicenseAssessmentResponse(LicenseResponseModel):
    assessment_id: str
    license_id: str | None
    package_id: str | None
    classification: str
    severity: Severity | None
    manual_review_required: bool
    reason: str
    component_categories: list[str]
    alternative_terms: bool
    exception_review: bool
    policy_status: str
    finding_ids: list[str]


class LicenseAssessmentItem(LicenseAssessmentResponse):
    package_name: str | None
    package_version: str | None
    package_purl: str | None
    original_expression: str | None
    canonical_expression: str | None
    normalization_status: str | None
    location: LicenseLocationResponse | None
    source: str | None
    source_kind: str | None
    source_scope: str | None
    finding_count: int = Field(ge=0)


class LicensePackageResponse(LicenseResponseModel):
    id: str
    name: str
    version: str | None
    purl: str | None
    identifier: str | None


class LicenseObservationResponse(LicenseResponseModel):
    id: str
    package_id: str | None
    source: str | None
    source_kind: str | None
    source_scope: str | None
    location_precision: str | None


class LicenseFindingReferenceResponse(LicenseResponseModel):
    finding_id: str
    rule_id: str
    severity: Severity
    title: str


class LicenseOverviewResponse(LicenseResponseModel):
    scan_id: str
    module: Literal["license"] = "license"
    status: ScanStatus
    scan_status: str
    diagnostics: list[str]
    inventory_available: bool
    inventory: LicenseInventoryMetadataResponse
    coverage: LicenseCoverageResponse
    summary: LicenseSummaryResponse
    providers: list[LicenseProviderResponse]
    pagination: LicensePaginationResponse
    items: list[LicenseAssessmentItem]


class LicenseDetailResponse(LicenseResponseModel):
    scan_id: str
    module: Literal["license"] = "license"
    status: ScanStatus
    scan_status: str
    diagnostics: list[str]
    assessment: LicenseAssessmentResponse
    package: LicensePackageResponse | None
    license: LicenseObservationResponse | None
    normalization: LicenseNormalizationResponse | None
    location: LicenseLocationResponse | None
    finding_refs: list[LicenseFindingReferenceResponse]
    provider_refs: list[LicenseProviderResponse]
