import json

import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.license.models import LicenseEvidence, LicenseProviderResult
from yuanjian_agent.license.policy import DefaultLicensePolicy, ProfiledLicensePolicy
from yuanjian_agent.license.profile import (
    MAX_PROFILE_BYTES, InvalidLicensePolicyProfile, parse_license_policy_profile,
)
from yuanjian_agent.license.scanner import LicenseScanner
from yuanjian_agent.models import Evidence, SourceSpan
from yuanjian_agent.core.scanner import ScanStatus
from license_provider_support import context_for


class StaticProvider:
    name = "scancode"

    def __init__(self, result):
        self.result = result

    def collect(self, context):
        return self.result


def fact(expression):
    return LicenseEvidence(Evidence(SourceSpan("LICENSE", 1, 1), "fixture"), "scancode", expression)


def profile(**changes):
    data = {"schema_version": 1, "license_overrides": {}, "classification_overrides": {}}
    data.update(changes)
    return parse_license_policy_profile(json.dumps(data).encode())


def test_default_policy_is_unchanged_without_profile():
    assert DefaultLicensePolicy().assess(fact("AGPL-3.0-only")).classification == "network_copyleft"


def test_profile_custom_classification_severity_and_manual_review():
    policy = ProfiledLicensePolicy(profile(
        license_overrides={"AGPL-3.0-only": "weak_copyleft"},
        classification_overrides={"weak_copyleft": {"severity": "critical", "manual_review_required": True}},
    ))
    assessment = policy.assess(fact("AGPL-3.0-only"))
    assert assessment.classification == "weak_copyleft"
    assert assessment.severity == "critical" and assessment.manual_review_required
    assert policy.evaluate(fact("AGPL-3.0-only"))[0].severity == "critical"


def test_profile_can_require_review_for_permissive_classification():
    policy = ProfiledLicensePolicy(profile(
        classification_overrides={"permissive": {"severity": "low", "manual_review_required": True}}
    ))
    assessment = policy.assess(fact("MIT"))
    assert assessment.severity == "low" and assessment.manual_review_required
    assert policy.evaluate(fact("MIT"))[0].severity == "low"


def test_profile_does_not_make_unspecified_unknown_license_clean():
    policy = ProfiledLicensePolicy(profile())
    assessment = policy.assess(fact("Unlicense"))
    assert assessment.classification == "unknown"
    assert assessment.severity == "medium" and assessment.manual_review_required


@pytest.mark.parametrize("raw", [
    b"{}",
    b'{"schema_version":1,"unknown":{}}',
    b'{"schema_version":1,"license_overrides":{"MIT":"bad"}}',
    b'{"schema_version":1,"license_overrides":{"MIT":"permissive","MIT":"unknown"}}',
    b'{"schema_version":1,"classification_overrides":{"permissive":{"severity":"urgent"}}}',
    b'{"schema_version":1,"classification_overrides":{"permissive":{"unknown":true}}}',
    b'{"schema_version":1,"license_overrides":{"MIT OR Apache-2.0":"permissive"}}',
    b"x" * (MAX_PROFILE_BYTES + 1),
], ids=["missing-version", "unknown-root-field", "bad-classification", "duplicate-license",
        "invalid-severity", "unknown-nested-field", "expression-key", "oversized"])
def test_invalid_profiles_fail_closed(raw):
    with pytest.raises(InvalidLicensePolicyProfile):
        parse_license_policy_profile(raw)


def test_target_repository_cannot_supply_policy(tmp_path):
    context = context_for(tmp_path)
    policy_path = context.project_root / "license-policy.json"
    policy_path.write_text(json.dumps({"schema_version": 1, "license_overrides": {"AGPL-3.0-only": "permissive"}}))
    context.config.license_policy_profile = policy_path
    provider = LicenseProviderResult("scancode", status=ScanStatus.SUCCESS, licenses=[fact("AGPL-3.0-only")])
    result = LicenseScanner(providers=[StaticProvider(provider)]).scan(context)
    assert result.status == "failed"
    assert result.metadata["policy_name"] == "invalid_profile"
    assert not result.findings
    assert result.metadata["assessments"][0]["policy_status"] == "unavailable"
    assert "AGPL-3.0-only" not in "".join(result.warnings)


def test_trusted_profile_is_opt_in_and_applied(tmp_path):
    context = context_for(tmp_path)
    policy_path = tmp_path / "trusted-policy.json"
    policy_path.write_text(json.dumps({
        "schema_version": 1,
        "license_overrides": {"AGPL-3.0-only": "permissive"},
        "classification_overrides": {},
    }))
    context.config.license_policy_profile = policy_path
    provider = LicenseProviderResult("scancode", status=ScanStatus.SUCCESS, licenses=[fact("AGPL-3.0-only")])
    result = LicenseScanner(providers=[StaticProvider(provider)]).scan(context)
    assert result.status == "success" and result.findings == []
    assert result.metadata["policy_name"] == "profile"
    assert result.metadata["assessments"][0]["classification"] == "permissive"
