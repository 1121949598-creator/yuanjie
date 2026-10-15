from __future__ import annotations

from ..core.context import ScanContext
from ..core.exceptions import ExternalToolUnavailable
from ..core.scanner import ScannerResult, ScanStatus, SecurityModule
from ..secrets import SecretScanner as BuiltinSecretScanner
from .adapters.detect_secrets import DetectSecretsAdapter
from .adapters.gitleaks import GitleaksAdapter
from .adapters.trufflehog import TruffleHogAdapter
from .normalizer import normalize_secret


class SecretScanner:
    """Module coordinator; BuiltinSecretScanner is an alias, not another detector."""

    name = SecurityModule.SECRET

    def __init__(self, builtin: BuiltinSecretScanner) -> None:
        self.builtin = builtin

    def scan(self, context: ScanContext) -> ScannerResult:
        result = ScannerResult(findings=self.builtin.scan(context.files))
        result.warnings.extend(self.builtin.warnings)
        if result.warnings:
            result.status = ScanStatus.PARTIAL
        result.providers["builtin-secret"] = result.status
        config = context.config.scanners
        for enabled, adapter in (
            (config.enable_gitleaks, GitleaksAdapter()),
            (config.enable_detect_secrets, DetectSecretsAdapter()),
            (config.enable_trufflehog, TruffleHogAdapter()),
        ):
            if not enabled:
                result.providers[adapter.name] = ScanStatus.DISABLED
                continue
            try:
                findings = [normalize_secret(item) for item in adapter.scan(context)]
            except ExternalToolUnavailable:
                result.providers[adapter.name] = ScanStatus.UNAVAILABLE
                result.warnings.append(f"{adapter.name}: integration is not implemented")
                result.status = ScanStatus.PARTIAL
            except Exception:
                result.providers[adapter.name] = ScanStatus.FAILED
                result.warnings.append(f"{adapter.name}: failed; diagnostic details suppressed")
                result.status = ScanStatus.PARTIAL
            else:
                result.findings.extend(findings)
                result.providers[adapter.name] = ScanStatus.SUCCESS
        return result
