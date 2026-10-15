from typing import Protocol
import re

from ..core.exceptions import ExternalToolUnavailable
from ..models import Severity
from .models import LicenseAssessment, LicenseEvidence, LicensePolicyDecision
from .catalog import CATEGORY_RANK, LICENSE_CATEGORIES
from .spdx import normalize_spdx
from .profile import LicensePolicyProfile


POLICY_VERSION = "1"


class DefaultLicensePolicy:
    """Conservative engineering review priorities; not legal advice.

    packaging validates syntax. This bounded iterative reduction only computes
    categories (WITH > AND > OR), never expands alternatives or selects a license.
    """

    def category_for(self, license_id: str) -> str:
        return LICENSE_CATEGORIES.get(license_id, "unknown")

    def adjust_assessment(self, assessment: LicenseAssessment) -> LicenseAssessment:
        return assessment

    def assess(self, evidence: LicenseEvidence) -> LicenseAssessment:
        normalized = evidence.normalization or normalize_spdx(evidence.license_expression)
        if normalized.canonical_expression is None:
            return self.adjust_assessment(LicenseAssessment("unknown", Severity.MEDIUM, True, normalized.reason))
        values, operators = [], []
        alternative, exception = False, False

        def combine():
            nonlocal alternative
            operator = operators.pop()
            right, left = values.pop(), values.pop()
            if operator == "OR" and left != right:
                alternative = True
            values.append(left | right)

        tokens = re.findall(r"\(|\)|[^\s()]+", normalized.canonical_expression)
        precedence = {"OR": 1, "AND": 2}
        for i, token in enumerate(tokens):
            if token == "WITH":
                exception = True
            elif i and tokens[i - 1] == "WITH":
                continue
            elif token == "(":
                operators.append(token)
            elif token == ")":
                while operators[-1] != "(":
                    combine()
                operators.pop()
            elif token in precedence:
                while operators and operators[-1] != "(" and precedence[operators[-1]] >= precedence[token]:
                    combine()
                operators.append(token)
            else:
                values.append({self.category_for(token)})
        while operators:
            combine()
        components = sorted(values[0], key=CATEGORY_RANK.__getitem__)
        category = components[-1]
        manual = category != "permissive" or alternative or exception or "unknown" in components
        severity = (Severity.HIGH if category in {"strong_copyleft", "network_copyleft"}
                    else Severity.MEDIUM if manual else None)
        reason = ("alternative_terms_require_review" if alternative else "exception_terms_require_review" if exception
                  else "unknown_license_review" if "unknown" in components else category + "_review" if manual
                  else "catalog_permissive")
        return self.adjust_assessment(
            LicenseAssessment(category, severity, manual, reason, components, alternative, exception)
        )

    def decisions(self, assessment: LicenseAssessment, evidence: LicenseEvidence) -> list[LicensePolicyDecision]:
        if not assessment.manual_review_required:
            return []
        normalized = evidence.normalization or normalize_spdx(evidence.license_expression)
        rule = ("LICENSE_ALTERNATIVE_TERMS_REVIEW" if assessment.alternative_terms
                else "LICENSE_INVALID_EXPRESSION" if normalized.status == "invalid"
                else {"weak_copyleft": "LICENSE_WEAK_COPYLEFT_REVIEW",
                      "strong_copyleft": "LICENSE_STRONG_COPYLEFT_REVIEW",
                      "network_copyleft": "LICENSE_NETWORK_COPYLEFT_REVIEW"}.get(
                          assessment.classification, "LICENSE_UNKNOWN_REVIEW"))
        return [LicensePolicyDecision(
            rule, assessment.severity or Severity.MEDIUM,
            evidence.confidence if evidence.confidence is not None else 0.8,
            "Alternative license terms require review" if assessment.alternative_terms else "License terms require manual review",
            [assessment.reason, "Engineering compliance review priority; not legal advice"],
            ["Confirm the applicable license terms and the actual use, modification and distribution context",
             "Review attribution, source availability and other obligations with the responsible compliance reviewer",
             "Confirm any chosen alternative or exception before relying on it"],
        )]

    def evaluate(self, evidence: LicenseEvidence) -> list[LicensePolicyDecision]:
        return self.decisions(self.assess(evidence), evidence)


class ProfiledLicensePolicy(DefaultLicensePolicy):
    """Default policy plus bounded, administrator-controlled overrides."""

    def __init__(self, profile: LicensePolicyProfile) -> None:
        self.profile = profile

    def category_for(self, license_id: str) -> str:
        return self.profile.license_overrides.get(license_id, super().category_for(license_id))

    def adjust_assessment(self, assessment: LicenseAssessment) -> LicenseAssessment:
        override = self.profile.classification_overrides.get(assessment.classification)
        if override is None:
            return assessment
        manual = (assessment.manual_review_required if override.manual_review_required is None
                  else override.manual_review_required)
        severity = override.severity if override.severity is not None else assessment.severity
        if not manual:
            severity = None
        elif severity is None:
            severity = Severity.MEDIUM
        return LicenseAssessment(
            assessment.classification, severity, manual, "profile_classification_override",
            assessment.component_categories, assessment.alternative_terms,
            assessment.exception_review, assessment.policy_status,
        )


class LicensePolicy(Protocol):
    def evaluate(self, evidence: LicenseEvidence) -> list[LicensePolicyDecision]: ...


class UnavailableLicensePolicy:
    def evaluate(self, evidence: LicenseEvidence) -> list[LicensePolicyDecision]:
        # Explicit opt-out remains available for callers without a risk policy.
        raise ExternalToolUnavailable()
