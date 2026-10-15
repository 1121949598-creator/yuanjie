from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Evidence, Severity
from ..core.scanner import ScanStatus


EXPRESSION_WITHHELD = "[license expression withheld]"
EXPRESSION_LIMIT = "[license expression exceeds length limit]"


@dataclass(slots=True)
class SpdxNormalizationResult:
    original_expression: str | None
    canonical_expression: str | None
    status: str
    manual_review_required: bool
    reason: str
    license_ids: list[str] = field(default_factory=list)
    exception_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LicenseAssessment:
    classification: str
    severity: Severity | None
    manual_review_required: bool
    reason: str
    component_categories: list[str] = field(default_factory=list)
    alternative_terms: bool = False
    exception_review: bool = False
    policy_status: str = "success"


@dataclass(slots=True)
class ProviderProvenance:
    provider: str
    provider_version: str | None
    origin_provider: str
    source_kind: str
    scan_mode: str
    origin_version: str | None = None


@dataclass(slots=True)
class PackageEvidence:
    name: str
    version: str | None = None
    purl: str | None = None
    provenance: list[ProviderProvenance] = field(default_factory=list)
    identifier: str | None = None


@dataclass(slots=True)
class DependencyEvidence:
    manifest_path: str
    package: PackageEvidence
    relationship: str = "declared"
    scope: str | None = None
    requirement: str | None = None
    from_package: str | None = None
    provenance: list[ProviderProvenance] = field(default_factory=list)


@dataclass(slots=True)
class LicenseEvidence:
    """Static facts only. A detected license is not automatically a violation."""

    evidence: Evidence
    source: str
    license_expression: str | None = None
    package: PackageEvidence | None = None
    dependencies: list[DependencyEvidence] = field(default_factory=list)
    provenance: list[ProviderProvenance] = field(default_factory=list)
    confidence: float | None = None
    normalization: SpdxNormalizationResult | None = None


@dataclass(slots=True)
class LicenseProviderResult:
    """Safe facts, not policy conclusions. No raw output or exception payloads."""

    name: str
    version: str | None = None
    execution_mode: str = "result-import"
    status: ScanStatus = ScanStatus.UNAVAILABLE
    reason_code: str = "result_not_configured"
    warnings: list[str] = field(default_factory=list)
    scan_error_count: int = 0
    packages: list[PackageEvidence] = field(default_factory=list)
    dependencies: list[DependencyEvidence] = field(default_factory=list)
    licenses: list[LicenseEvidence] = field(default_factory=list)


@dataclass(slots=True)
class LicensePolicyDecision:
    rule_id: str
    severity: Severity
    confidence: float
    title: str
    rationale: list[str]
    remediation: list[str]
