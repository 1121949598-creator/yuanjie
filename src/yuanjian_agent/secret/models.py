from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import Evidence, ReviewStatus, Severity


@dataclass(slots=True)
class SecretEvidence:
    """Only masked evidence and HMAC; raw candidates never enter this contract."""

    evidence: Evidence
    rule_id: str
    title: str
    severity: Severity
    confidence: float
    rationale: list[str]
    review_status: ReviewStatus
    metadata: dict[str, Any]
    source: str = "builtin-secret"
