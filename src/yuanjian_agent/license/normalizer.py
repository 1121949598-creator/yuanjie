from dataclasses import asdict

from ..models import Finding, FindingCategory
from ..core.identifiers import stable_id
from .models import LicenseEvidence, LicensePolicyDecision


def normalize_license(evidence: LicenseEvidence, decision: LicensePolicyDecision, *, assessment=None, license_id=None) -> Finding:
    """Map an explicit policy decision to the existing shared Finding."""
    span = evidence.evidence.source_span
    package = evidence.package
    signature = stable_id(
        "sig", "license", span.path, str(span.start_line), decision.rule_id,
        evidence.license_expression or "", package.name if package else "",
        (package.version or "") if package else "", (package.purl or "") if package else "",
    )
    if license_id is not None:
        signature = stable_id("sig", "license-l2", license_id, decision.rule_id)
    metadata = {
        "license_expression": evidence.license_expression,
        "package": asdict(package) if package else None,
        "dependencies": [asdict(item) for item in evidence.dependencies] if license_id is None else [],
    }
    if evidence.normalization is not None:
        metadata["normalization"] = asdict(evidence.normalization)
        metadata["canonical_expression"] = evidence.normalization.canonical_expression
    if assessment is not None:
        metadata["assessment"] = asdict(assessment)
    if license_id is not None:
        metadata.update(license_id=license_id, assessment_id=stable_id("assessment", license_id))
    return Finding(
        id=stable_id("finding", signature), signature=signature,
        category=FindingCategory.LICENSE, rule_id=decision.rule_id,
        severity=decision.severity, confidence=decision.confidence,
        title=decision.title, evidence=[evidence.evidence],
        rationale=decision.rationale, remediation=decision.remediation,
        source=evidence.source,
        metadata=metadata,
    )
