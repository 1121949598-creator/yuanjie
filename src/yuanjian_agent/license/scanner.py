from __future__ import annotations

from ..core.context import ScanContext
from ..core.exceptions import ExternalToolUnavailable
from ..core.scanner import ScannerResult, ScanStatus, SecurityModule
from ..core.redaction import sanitize_value
from ..core.metadata import safe_module_metadata
from ..secrets import SecretScanner as TextSecretScanner
from .adapters.ort import OrtAdapter
from .adapters.scancode import ScanCodeAdapter
from .normalizer import normalize_license
from .policy import DefaultLicensePolicy, LicensePolicy, ProfiledLicensePolicy, UnavailableLicensePolicy
from .profile import InvalidLicensePolicyProfile, load_license_policy_profile
from .models import LicenseAssessment, LicenseProviderResult
from .adapters.base import deduplicate_facts
from .inventory import LicenseInventory, fact_id, prepare_fact
from ..models import Severity


class LicenseScanner:
    name = SecurityModule.LICENSE

    def __init__(self, policy: LicensePolicy | None = None, *, providers=None) -> None:
        self.policy = policy if policy is not None else DefaultLicensePolicy()
        self.providers = tuple(providers) if providers is not None else (ScanCodeAdapter(), OrtAdapter())
        if [p.name for p in self.providers] != [n for n in ("scancode", "ort") if any(p.name == n for p in self.providers)]:
            raise ValueError("License providers must be unique and in ScanCode/ORT order")

    def collect(self, context: ScanContext) -> list[LicenseProviderResult]:
        """Expose safe upstream facts before policy, without persisting raw JSON."""
        results = []
        for provider in self.providers:
            enabled = getattr(context.config.scanners, "enable_" + provider.name)
            if not enabled:
                results.append(LicenseProviderResult(provider.name, status=ScanStatus.DISABLED, reason_code="disabled"))
                continue
            try:
                output = provider.collect(context)
                if not isinstance(output, LicenseProviderResult) or output.name != provider.name:
                    raise TypeError("Invalid provider contract")
            except Exception:
                output = LicenseProviderResult(provider.name, status=ScanStatus.FAILED, reason_code="execution_failed")
            results.append(output)
        return results

    def scan(self, context: ScanContext) -> ScannerResult:
        result = ScannerResult(status=ScanStatus.UNAVAILABLE)
        active_policy = self.policy
        profile_configured = False
        profile_failed = False
        if type(self.policy) is DefaultLicensePolicy and context.config.license_policy_profile is not None:
            profile_configured = True
            try:
                active_policy = ProfiledLicensePolicy(load_license_policy_profile(
                    context.config.license_policy_profile, context.project_root
                ))
            except InvalidLicensePolicyProfile:
                active_policy = UnavailableLicensePolicy()
                profile_failed = True
        outputs = self.collect(context)
        for output in outputs:
            result.providers[output.name] = output.status
            if output.status != ScanStatus.DISABLED:
                result.warnings.append(
                    f"license-provider: {output.name}; version={output.version or 'unknown'}; "
                    f"mode={output.execution_mode}; status={output.status}; reason={output.reason_code}"
                )
        policy_unavailable = isinstance(active_policy, UnavailableLicensePolicy)
        policy_failed = profile_failed
        policy_completed = 0
        inventory = LicenseInventory()
        for output in outputs:
            if output.status not in {ScanStatus.SUCCESS, ScanStatus.PARTIAL}:
                continue
            for package in output.packages:
                try:
                    inventory.add_package(package)
                except Exception:
                    inventory.issues.add("invalid_package_projection")
            for dependency in output.dependencies:
                try:
                    inventory.add_dependency(dependency)
                except Exception:
                    inventory.issues.add("invalid_dependency_projection")
        for raw_fact in deduplicate_facts(outputs):
            try:
                evidence = prepare_fact(raw_fact)
            except Exception:
                inventory.issues.add("invalid_fact_projection")
                continue
            assessment = LicenseAssessment("unknown", Severity.MEDIUM, True,
                                           "policy_unavailable", policy_status="unavailable")
            findings = []
            try:
                if isinstance(active_policy, DefaultLicensePolicy):
                    assessment = active_policy.assess(evidence)
                    decisions = active_policy.decisions(assessment, evidence)
                elif not policy_unavailable:
                    decisions = active_policy.evaluate(evidence)
                    assessment = LicenseAssessment("unknown", Severity.MEDIUM, True,
                                                   "custom_policy_review", policy_status="custom")
                else:
                    decisions = []
                findings = [normalize_license(evidence, decision, assessment=assessment,
                                              license_id=fact_id(evidence)) for decision in decisions]
                if assessment.policy_status in {"success", "custom"}:
                    policy_completed += 1
            except ExternalToolUnavailable:
                policy_unavailable = True
            except Exception:
                policy_failed = True
                assessment = LicenseAssessment("unknown", Severity.MEDIUM, True,
                                               "policy_failed", policy_status="failed")
            if inventory.add_fact(evidence, assessment, findings):
                result.findings.extend(findings)
        statuses = set(result.providers.values())
        if statuses & {ScanStatus.SUCCESS, ScanStatus.PARTIAL}:
            result.status = (
                ScanStatus.PARTIAL if statuses & {ScanStatus.FAILED, ScanStatus.UNAVAILABLE, ScanStatus.PARTIAL}
                else ScanStatus.SUCCESS
            )
        elif ScanStatus.FAILED in statuses:
            result.status = ScanStatus.FAILED
        if policy_unavailable and result.status in {ScanStatus.SUCCESS, ScanStatus.PARTIAL}:
            result.status = ScanStatus.PARTIAL if policy_completed else ScanStatus.UNAVAILABLE
        if policy_failed:
            result.status = ScanStatus.PARTIAL if policy_completed else ScanStatus.FAILED
        result.metadata = inventory.finish(outputs, result.status)
        result.metadata["policy_name"] = (
            "invalid_profile" if profile_failed else "profile" if profile_configured
            else "default" if isinstance(self.policy, DefaultLicensePolicy)
            else "unavailable" if isinstance(self.policy, UnavailableLicensePolicy) else "custom"
        )
        if result.metadata["policy_name"] not in {"default", "profile"}:
            result.metadata["policy_version"] = None
        if inventory.issues:
            result.status = ScanStatus.PARTIAL
            result.metadata["coverage"]["status"] = str(result.status)
        if result.status != ScanStatus.SUCCESS:
            result.warnings.append("License coverage is incomplete: policy_unavailable" if policy_unavailable
                                   else "License coverage is incomplete: provider_or_policy_incomplete")
        if profile_failed:
            result.warnings.append("License policy profile failed: invalid_configuration")
        redactor = TextSecretScanner(b"license-l2-projection-no-fingerprints").redactor_for(context.files)
        result.metadata = safe_module_metadata(result.metadata, redactor, context.project_root)
        sanitize_value(result, redactor)
        return result
