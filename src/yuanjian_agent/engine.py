from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence

from .analysis import CapabilityAnalyzer, ContextRiskScorer
from .agent_security.risk import AgentRiskAnalyzer, _severity_for_exposure
from .agent_security.scanner import AgentSecurityScanner
from .core.context import ScanContext
from .core.normalizer import deduplicate
from .core.metadata import safe_module_metadata
from .core.redaction import sanitize_value
from .core.registry import ScannerRegistry
from .core.scanner import ScannerResult, ScanStatus, SecurityModule
from .license.scanner import LicenseScanner
from .secret.scanner import SecretScanner as SecretPipeline
from .config import Settings
from .component_security import ComponentSecurityPipeline, EvidenceConstrainedScorer
from .files import iter_text_files
from .models import (
    AgentSpec,
    Finding,
    FindingCategory,
    ReviewStatus,
    ScanResult,
    ScanSummary,
    Severity,
    ToolSpec,
)
from .parsers import ProjectParser
from .safe_import import prepare_project
from .secrets import SecretScanner, load_or_create_fingerprint_key
from .storage import ScanStore
from .scan_profiles import PROFILE_VERSION, detect_inputs, empty_component_result, resolve_profile


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summary(findings: list[Finding]) -> ScanSummary:
    by_severity: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity.value] = by_severity.get(finding.severity.value, 0) + 1
    return ScanSummary(
        total_findings=len(findings),
        secrets=sum(finding.category == FindingCategory.SECRET for finding in findings),
        tool_exposures=sum(finding.category == FindingCategory.TOOL_EXPOSURE for finding in findings),
        unresolved=sum(finding.category == FindingCategory.UNRESOLVED for finding in findings),
        by_severity=by_severity,
        licenses=sum(f.category == FindingCategory.LICENSE for f in findings),
        agent_security=sum(f.category in {
            FindingCategory.AGENT_SECURITY, FindingCategory.TOOL_EXPOSURE, FindingCategory.UNRESOLVED
        } for f in findings),
        tool_capabilities=sum(f.category == FindingCategory.TOOL_CAPABILITY for f in findings),
    )


_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class ScanEngine:
    def __init__(
        self, settings: Settings | None = None, model_bundle: dict | None = None,
        *, registry: ScannerRegistry | None = None, agent_providers: Sequence[ProjectParser] = (),
        component_scorer: EvidenceConstrainedScorer | None = None,
        enable_component_security: bool | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.settings.ensure_directories()
        self.store = ScanStore(self.settings)
        key = load_or_create_fingerprint_key(self.settings.fingerprint_key_path)
        self.secret_scanner = SecretScanner(key)
        self.capability_analyzer = CapabilityAnalyzer()
        self.context_scorer = ContextRiskScorer(model_bundle=model_bundle)
        self.agent_scanner = AgentSecurityScanner(
            self.capability_analyzer, self.context_scorer, providers=agent_providers
        )
        if component_scorer is None and self.settings.component_model_dir is not None:
            component_scorer = EvidenceConstrainedScorer.from_local_model(
                self.settings.component_model_dir
            )
        if enable_component_security is None:
            enable_component_security = registry is None
        self.component_security = (
            ComponentSecurityPipeline(scorer=component_scorer)
            if enable_component_security else None
        )
        self.registry = registry if registry is not None else ScannerRegistry()
        if registry is None:
            self.registry.register(SecretPipeline(self.secret_scanner))
            self.registry.register(LicenseScanner())
            self.registry.register(self.agent_scanner)

    def scan(
        self, path: str | Path, parent_scan_id: str | None = None,
        *, project_name: str | None = None, scene: str | None = None,
        profile: str | None = None,
    ) -> ScanResult:
        plan, scene = resolve_profile(profile, scene)
        scan_id = uuid.uuid4().hex[:16]
        scan_workspace = self.settings.scans_dir / scan_id
        scan_workspace.mkdir(parents=True, exist_ok=False)
        source = prepare_project(path, self.settings.limits, workspace=scan_workspace)
        files, file_warnings = iter_text_files(source.root, self.settings.limits)
        redactor = self.secret_scanner.redactor_for(files)
        context = ScanContext(
            scan_id=scan_id, project_root=source.root,
            source_type="zip" if source.temporary else "directory",
            config=self.settings, temp_dir=scan_workspace, files=files,
        )
        findings = []
        agents, tools, bindings = [], [], []
        warnings = source.warnings + file_warnings
        module_statuses = {}
        module_data = {}
        executed_modules = []
        detected = detect_inputs(files) if plan else None
        enabled = {
            SecurityModule.SECRET: self.settings.scanners.enable_secret,
            SecurityModule.LICENSE: self.settings.scanners.enable_license,
            SecurityModule.AGENT_SECURITY: self.settings.scanners.enable_agent,
        }
        for scanner in self.registry:
            if plan and scanner.name not in plan.modules:
                module_statuses[scanner.name] = {"status": ScanStatus.DISABLED, "providers": {},
                                                  "reason": "not_requested_by_profile"}
                continue
            if not enabled[scanner.name]:
                module_statuses[scanner.name] = {"status": ScanStatus.DISABLED, "providers": {}}
                continue
            if plan and scanner.name == SecurityModule.AGENT_SECURITY and not detected["agent_detected"]:
                uncertain = (detected["agent_hint"] or detected["python_syntax_errors"]
                             or detected["unsupported_code_files"] or detected["structure_detection_incomplete"])
                module_statuses[scanner.name] = {
                    "status": ScanStatus.PARTIAL if uncertain else ScanStatus.NOT_APPLICABLE,
                    "providers": {}, "reason": "agent_structure_unresolved" if uncertain else "no_supported_agent_structure",
                }
                continue
            try:
                executed_modules.append(str(scanner.name))
                context.upstream_findings = tuple(findings)
                context.upstream_statuses = {name: item["status"] for name, item in module_statuses.items()}
                output = scanner.scan(context)
                if not isinstance(output, ScannerResult):
                    raise TypeError("Invalid scanner output")
                # Domain normalizers must mask before return; also sanitize at collection.
                sanitize_value(output.findings, redactor)
                if output.metadata:
                    try:
                        module_data[str(scanner.name)] = safe_module_metadata(output.metadata, redactor, source.root)
                    except Exception:
                        output.status = ScanStatus.PARTIAL if output.findings else ScanStatus.FAILED
                        output.warnings.append(f"{scanner.name}: module data rejected; diagnostic details suppressed")
            except Exception:
                # Never stringify/log target-derived errors, including unknown exceptions.
                output = ScannerResult(status=ScanStatus.FAILED)
                output.warnings.append(f"{scanner.name}: failed; diagnostic details suppressed")
            module_statuses[scanner.name] = {"status": output.status, "providers": output.providers}
            findings.extend(output.findings)
            agents.extend(output.agents)
            tools.extend(output.tools)
            bindings.extend(output.bindings)
            warnings.extend(output.warnings)
        component_key = "tool_capability" if plan and plan.id == "download" else "component_security"
        run_components = self.component_security is not None and (not plan or plan.component_scope is not None)
        if plan and plan.id == "agent" and (not enabled[SecurityModule.AGENT_SECURITY] or not detected["agent_detected"]):
            run_components = False
            state = module_statuses.get(SecurityModule.AGENT_SECURITY, {})
            module_statuses[component_key] = {"status": state.get("status", ScanStatus.UNAVAILABLE),
                                              "reason": state.get("reason", "host_disabled"), "providers": {}}
            module_data["component_security"] = empty_component_result(scene, str(module_statuses[component_key]["status"]),
                                                                       module_statuses[component_key]["reason"])
        elif plan and plan.component_scope is None:
            module_statuses[component_key] = {"status": ScanStatus.DISABLED, "reason": "not_requested_by_profile", "providers": {}}
            module_data["component_security"] = empty_component_result(scene, "disabled", "not_requested_by_profile")
        elif plan and not run_components:
            module_statuses[component_key] = {"status": ScanStatus.UNAVAILABLE, "reason": "component_pipeline_unavailable", "providers": {}}
            module_data["component_security"] = empty_component_result(scene, "unavailable", "component_pipeline_unavailable")
        if run_components:
            executed_modules.append(component_key)
            try:
                component_options = {"scope": plan.component_scope} if plan else {}
                component_data, component_findings, component_warnings = self.component_security.run(
                    scan_id=scan_id,
                    scene=scene,
                    files=files,
                    **component_options,
                )
                if plan and detected["unsupported_code_files"]:
                    component_data["status"] = "partial"
                    component_warnings.append("unsupported_source_language")
                    component_data["warnings"] = sorted(set(component_data["warnings"] + component_warnings))
                module_data["component_security"] = safe_module_metadata(
                    component_data, redactor, source.root
                )
                findings.extend(component_findings)
                warnings.extend(f"component_security:{warning}" for warning in component_warnings)
            except Exception:
                module_data["component_security"] = {
                    "schema_version": "1.0",
                    "scene": scene,
                    "status": "failed",
                    "components": [],
                    "summary": {"components": 0, "assessments": 0, "inconsistent": 0, "needs_review": 0},
                    "warnings": ["component_security_pipeline_failed"],
                }
                warnings.append("component_security:failed; diagnostic details suppressed")
            if plan:
                module_statuses[component_key] = {"status": module_data["component_security"]["status"],
                                                 "providers": {}, "reason": "static_component_analysis"}
        for module in SecurityModule:
            if module not in module_statuses:
                module_statuses[module] = {
                    "status": ScanStatus.UNAVAILABLE if enabled[module] else ScanStatus.DISABLED,
                    "providers": {},
                }
        findings = deduplicate(findings)
        self._sanitize_parsed_context(agents, tools, findings)
        statuses = [item["status"] for item in module_statuses.values()]
        status = "partial" if any(s in {ScanStatus.FAILED, ScanStatus.PARTIAL} for s in statuses) else "completed"
        if ScanStatus.FAILED in statuses and not any(s in {ScanStatus.SUCCESS, ScanStatus.PARTIAL} for s in statuses):
            status = "failed"
        elif ScanStatus.UNAVAILABLE in statuses and not any(s in {ScanStatus.SUCCESS, ScanStatus.PARTIAL} for s in statuses):
            status = "unavailable"
        if plan:
            applicable = [module_statuses.get(key, {}).get("status", ScanStatus.UNAVAILABLE)
                          for key in plan.modules]
            relevant = [value for value in applicable if value != ScanStatus.NOT_APPLICABLE]
            status = "completed" if relevant and all(v == ScanStatus.SUCCESS for v in relevant) else "partial"
            if relevant and all(v == ScanStatus.FAILED for v in relevant):
                status = "failed"
        result = ScanResult(
            id=scan_id,
            project_name=project_name or source.display_name,
            source_path=str(source.root),
            created_at=_utc_now(),
            status=status,
            version=self.settings.app_version,
            agents=agents,
            tools=tools,
            bindings=bindings,
            findings=sorted(
                findings,
                key=lambda item: (_SEVERITY_RANK[item.severity], item.confidence),
                reverse=True,
            ),
            warnings=warnings,
            parent_scan_id=parent_scan_id,
            metadata={
                "secret_rules_version": str(self.secret_scanner.rules.get("version", "unknown")),
                "tool_rules_version": str(self.capability_analyzer.rules.get("version", "unknown")),
                "context_model": str(
                    (self.context_scorer.model_bundle or {}).get("model_name", "deterministic-context-baseline")
                ),
                "execution_policy": "static-only-never-execute-target",
                "component_security_scene": scene,
                "scanners": module_statuses,
            },
        )
        if module_data:
            result.metadata["module_data"] = module_data
        if plan:
            result.metadata["scan_profile"] = {
                "id": plan.id, "version": PROFILE_VERSION, "scene": scene,
                "requested_modules": list(plan.modules),
                "executed_modules": executed_modules,
                "detected_inputs": detected,
                "agent_review_recommended": plan.id == "project" and bool(detected["agent_detected"] or detected["agent_hint"] or detected["mcp_detected"]),
            }
        if parent_scan_id:
            self._compare(result, self.store.get(parent_scan_id))
        result.summary = _summary(result.findings)
        sanitize_value(result, redactor)
        self.store.save(result)
        return result

    def _sanitize_parsed_context(
        self,
        agents: list[AgentSpec],
        tools: list[ToolSpec],
        findings: list[Finding],
    ) -> None:
        for tool in tools:
            tool.metadata.pop("body_source", None)
            tool.metadata.pop("server_config", None)
        sanitize_value(agents, self.secret_scanner)
        sanitize_value(tools, self.secret_scanner)
        sanitize_value(findings, self.secret_scanner)

    def _sanitize_value(self, value):
        return sanitize_value(value, self.secret_scanner)

    def _tool_findings(self, agents, tools, bindings):
        return self.agent_scanner.risk_analyzer.findings(agents, tools, bindings)

    _tool_remediation = staticmethod(AgentRiskAnalyzer._tool_remediation)

    def _compare(self, current: ScanResult, previous: ScanResult) -> None:
        previous_map = {finding.signature: finding for finding in previous.findings}
        current_map = {finding.signature: finding for finding in current.findings}
        remaining = sorted(previous_map.keys() & current_map.keys())
        resolved = sorted(previous_map.keys() - current_map.keys())
        category_modules = {
            FindingCategory.SECRET: SecurityModule.SECRET,
            FindingCategory.LICENSE: SecurityModule.LICENSE,
            FindingCategory.AGENT_SECURITY: SecurityModule.AGENT_SECURITY,
            FindingCategory.TOOL_EXPOSURE: SecurityModule.AGENT_SECURITY,
            FindingCategory.UNRESOLVED: SecurityModule.AGENT_SECURITY,
            FindingCategory.TOOL_CAPABILITY: "tool_capability",
        }
        statuses = current.metadata.get("scanners", {})
        not_evaluated = [
            signature for signature in resolved
            if statuses.get(
                "component_security" if previous_map[signature].source == "component_security_v1"
                and previous_map[signature].category == FindingCategory.AGENT_SECURITY
                and "component_security" in statuses
                else category_modules[previous_map[signature].category], {}).get("status")
            != ScanStatus.SUCCESS
        ]
        resolved = [signature for signature in resolved if signature not in not_evaluated]
        new = sorted(current_map.keys() - previous_map.keys())
        for signature in remaining:
            current_map[signature].review_status = ReviewStatus.REMAINING
        for signature in new:
            current_map[signature].review_status = ReviewStatus.NEW
        current.comparison = {
            "parent_scan_id": previous.id,
            "remaining": remaining,
            "resolved": resolved,
            "new": new,
            "not_evaluated": not_evaluated,
            "incomplete": bool(not_evaluated),
            "resolved_findings": [
                {"id": previous_map[signature].id, "title": previous_map[signature].title, "status": "resolved"}
                for signature in resolved
            ],
            "remaining_findings": [
                {"id": current_map[signature].id, "title": current_map[signature].title, "status": "remaining"}
                for signature in remaining
            ],
            "new_findings": [
                {"id": current_map[signature].id, "title": current_map[signature].title, "status": "new"}
                for signature in new
            ],
            "counts": {"remaining": len(remaining), "resolved": len(resolved), "new": len(new)},
        }
