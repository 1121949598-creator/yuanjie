import pytest

from yuanjian_agent.license.catalog import LICENSE_CATEGORIES
from yuanjian_agent.license.models import LicenseEvidence
from yuanjian_agent.license.policy import DefaultLicensePolicy
from yuanjian_agent.models import Evidence, SourceSpan


def fact(expression):
    return LicenseEvidence(Evidence(SourceSpan("LICENSE", 1, 1), "fixture"), "scancode", expression)


@pytest.mark.parametrize("license_id,category", list(LICENSE_CATEGORIES.items()))
def test_every_catalog_entry(license_id, category):
    policy = DefaultLicensePolicy()
    evidence = fact(license_id)
    assessment = policy.assess(evidence)
    decisions = policy.evaluate(evidence)
    assert assessment.classification == category
    if category == "permissive":
        assert decisions == [] and not assessment.manual_review_required
        assert assessment.severity is None
    else:
        assert assessment.manual_review_required and len(decisions) == 1
        assert decisions[0].severity == ("medium" if category == "weak_copyleft" else "high")
        assert decisions[0].rule_id == "LICENSE_" + category.upper() + "_REVIEW"
        assert decisions[0].remediation and "not legal advice" in decisions[0].rationale[-1]


@pytest.mark.parametrize("expression,rule", [
    (None, "LICENSE_UNKNOWN_REVIEW"), ("LicenseRef-Custom", "LICENSE_UNKNOWN_REVIEW"),
    ("Unlicense", "LICENSE_UNKNOWN_REVIEW"), ("Not-a-license-example", "LICENSE_INVALID_EXPRESSION"),
    ("MIT OR", "LICENSE_INVALID_EXPRESSION"), ("MIT" * 2000, "LICENSE_UNKNOWN_REVIEW"),
])
def test_unknown_cannot_be_clean(expression, rule):
    policy = DefaultLicensePolicy()
    assessment = policy.assess(fact(expression))
    decisions = policy.evaluate(fact(expression))
    assert assessment.classification == "unknown" and assessment.manual_review_required
    assert decisions[0].severity == "medium" and decisions[0].rule_id == rule


@pytest.mark.parametrize("expression,category,alternative,exception,severity", [
    ("MIT AND GPL-3.0-only", "strong_copyleft", False, False, "high"),
    ("MIT OR GPL-3.0-only", "strong_copyleft", True, False, "high"),
    ("MIT OR Apache-2.0", "permissive", False, False, None),
    ("MPL-2.0 OR LGPL-3.0-only", "weak_copyleft", False, False, "medium"),
    ("GPL-2.0-only WITH Classpath-exception-2.0", "strong_copyleft", False, True, "high"),
    ("MIT WITH LLVM-exception", "permissive", False, True, "medium"),
    ("MIT AND LicenseRef-Custom", "unknown", False, False, "medium"),
    ("GPL-3.0-only AND LicenseRef-Custom", "strong_copyleft", False, False, "high"),
    ("MIT AND (MPL-2.0 OR GPL-3.0-only)", "strong_copyleft", True, False, "high"),
    ("(MIT OR Apache-2.0) AND GPL-3.0-only", "strong_copyleft", False, False, "high"),
    ("GPL-3.0-only OR AGPL-3.0-only", "network_copyleft", True, False, "high"),
    ("MIT OR Apache-2.0 AND GPL-3.0-only", "strong_copyleft", True, False, "high"),
])
def test_combinations_are_conservative(expression, category, alternative, exception, severity):
    policy = DefaultLicensePolicy()
    assessment = policy.assess(fact(expression))
    assert assessment.classification == category and assessment.severity == severity
    assert assessment.alternative_terms == alternative and assessment.exception_review == exception
    if alternative:
        assert policy.evaluate(fact(expression))[0].rule_id == "LICENSE_ALTERNATIVE_TERMS_REVIEW"
    if severity:
        assert assessment.manual_review_required


def test_policy_uses_only_normalized_facts_and_does_not_mutate_input():
    evidence = fact("MIT")
    evidence.evidence.details["raw_json"] = {"license": "AGPL-3.0-only"}
    assert DefaultLicensePolicy().evaluate(evidence) == []
    assert evidence.normalization is None and evidence.license_expression == "MIT"
