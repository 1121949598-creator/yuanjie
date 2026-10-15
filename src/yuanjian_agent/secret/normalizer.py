from __future__ import annotations

from ..models import Finding, FindingCategory
from ..core.identifiers import stable_id
from .models import SecretEvidence


def normalize_secret(observation: SecretEvidence) -> Finding:
    fingerprint = observation.evidence.details["fingerprint"]
    signature = stable_id(
        "sig", "secret", observation.evidence.source_span.path, observation.rule_id, fingerprint
    )
    return Finding(
        id=stable_id("finding", signature), signature=signature,
        category=FindingCategory.SECRET, rule_id=observation.rule_id,
        severity=observation.severity, confidence=observation.confidence,
        title=observation.title, evidence=[observation.evidence],
        rationale=observation.rationale,
        remediation=[
            "Move the value to an environment variable or a dedicated secret manager",
            "Replace the repository value with a documented placeholder",
            "Rotate the credential if a real value has already been published",
        ],
        review_status=observation.review_status, metadata=observation.metadata,
        source=observation.source, fingerprint=fingerprint,
    )
