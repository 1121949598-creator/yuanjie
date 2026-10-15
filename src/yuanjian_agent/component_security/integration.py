"""Application-layer bridge from B's static facts to C's frozen scorer."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..core.identifiers import stable_id
from ..files import TextFile
from ..models import Evidence, Finding, FindingCategory, ReviewStatus, Severity, SourceSpan
from .contract import ContractError
from .intent_adapter import IntentCapabilityAdapter
from .v1 import EvidenceConstrainedScorer


def _failed_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a fixed, non-sensitive failure envelope for an invalid handoff."""
    component = payload.get("component") if isinstance(payload, Mapping) else None
    component_id = component.get("component_id", "component_unknown") if isinstance(component, Mapping) else "component_unknown"
    scene = payload.get("scene", "release_precheck") if isinstance(payload, Mapping) else "release_precheck"
    return {
        "schema_version": "1.0",
        "component_id": component_id,
        "scene": scene,
        "status": "failed",
        "assessments": [],
        "summary": {
            "total": 0,
            "by_relation": {
                "justified": 0,
                "needs_review": 0,
                "inconsistent": 0,
                "insufficient_evidence": 0,
            },
            "max_score": 0.0,
        },
        "warnings": ["contract_validation_failed"],
    }


def _overall_status(statuses: Sequence[str]) -> str:
    if not statuses:
        return "unavailable"
    if all(status == "failed" for status in statuses):
        return "failed"
    if all(status == "unavailable" for status in statuses):
        return "unavailable"
    if any(status != "success" for status in statuses):
        return "partial"
    return "success"


class ComponentSecurityPipeline:
    """Run the frozen B -> C boundary without Web, DB or target execution."""

    def __init__(
        self,
        *,
        adapter: IntentCapabilityAdapter | None = None,
        scorer: EvidenceConstrainedScorer | None = None,
    ) -> None:
        self.adapter = adapter or IntentCapabilityAdapter()
        self.scorer = scorer or EvidenceConstrainedScorer()

    def run(
        self,
        *,
        scan_id: str,
        scene: str,
        files: Sequence[TextFile],
        scope: str = "auto",
    ) -> tuple[dict[str, Any], list[Finding], list[str]]:
        if scope not in {"auto", "tool", "agent"}:
            raise ValueError("unsupported component scope")
        agent_payloads = [] if scope == "tool" else self.adapter.build_agents(
            scan_id=scan_id, scene=scene, files=files)
        payloads = agent_payloads
        if not payloads and scope != "agent":
            payloads = [self.adapter.build(scan_id=scan_id, scene=scene, files=files)]
        if scope == "tool":
            for payload in payloads:
                # README + main.py is not sufficient to call a tool an Agent.
                if payload["component"]["component_type"] == "agent":
                    payload["component"]["component_type"] = "project"
        components: list[dict[str, Any]] = []
        findings: list[Finding] = []
        warnings: list[str] = []
        statuses: list[str] = []

        for payload in payloads:
            try:
                result = self.scorer.score(payload).to_dict()
            except (ContractError, TypeError, ValueError):
                result = _failed_result(payload)
            statuses.append(result["status"])
            warnings.extend(result.get("warnings", []))
            components.append({
                "component": payload.get("component", {}),
                "capabilities": payload.get("capabilities", []),
                "boundaries": payload.get("boundaries", []),
                "evidence": payload.get("evidence", []),
                "parser": payload.get("parser", {}),
                "result": result,
            })
            projected = self._findings(scan_id, scene, payload, result)
            if scope == "tool":
                for finding in projected:
                    finding.category = FindingCategory.TOOL_CAPABILITY
            findings.extend(projected)

        module_data = {
            "schema_version": "1.0",
            "scene": scene,
            "status": _overall_status(statuses),
            "components": components,
            "summary": {
                "components": len(components),
                "assessments": sum(item["result"]["summary"]["total"] for item in components),
                "inconsistent": sum(
                    item["result"]["summary"]["by_relation"]["inconsistent"] for item in components
                ),
                "needs_review": sum(
                    item["result"]["summary"]["by_relation"]["needs_review"] for item in components
                ),
            },
            "warnings": list(dict.fromkeys(warnings)),
        }
        return module_data, findings, module_data["warnings"]

    @staticmethod
    def _findings(
        scan_id: str,
        scene: str,
        payload: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> list[Finding]:
        component = payload.get("component", {})
        capabilities = {
            item["capability_id"]: item for item in payload.get("capabilities", [])
        }
        evidence = {item["evidence_id"]: item for item in payload.get("evidence", [])}
        findings: list[Finding] = []
        for assessment in result.get("assessments", []):
            if assessment.get("relation") != "inconsistent":
                continue
            capability = capabilities.get(assessment.get("capability_id"), {})
            finding_evidence: list[Evidence] = []
            for evidence_id in assessment.get("evidence_refs", []):
                row = evidence.get(evidence_id)
                if not row:
                    continue
                span = row["source_span"]
                finding_evidence.append(Evidence(
                    source_span=SourceSpan(
                        path=span["path"],
                        start_line=span["start_line"],
                        end_line=span["end_line"],
                        start_column=span.get("start_column", 0),
                        end_column=span.get("end_column", 0),
                    ),
                    masked_excerpt=row["masked_excerpt"],
                    details={
                        "component_id": component.get("component_id", "unknown"),
                        "capability_id": assessment.get("capability_id", "unknown"),
                        "evidence_id": evidence_id,
                    },
                ))
            if not finding_evidence:
                continue
            signature = stable_id(
                "component_mismatch",
                str(component.get("component_id", "unknown")),
                str(assessment.get("capability_id", "unknown")),
            )
            score = float(assessment.get("score", 0.0))
            findings.append(Finding(
                id=stable_id("finding", scan_id, signature),
                signature=signature,
                category=FindingCategory.AGENT_SECURITY,
                rule_id="component.intent_capability_mismatch",
                severity=Severity.HIGH if score >= 0.85 else Severity.MEDIUM,
                confidence=float(capability.get("confidence", 0.5)),
                title="组件声明用途与实际能力不一致",
                evidence=finding_evidence,
                rationale=[reason["message"] for reason in assessment.get("reasons", [])],
                remediation=[
                    "确认该能力是否为声明用途所必需；若非必需，请移除或缩小权限范围。",
                    "发布或安装前由维护者复核对应源码证据与边界控制。",
                ],
                review_status=ReviewStatus.NEEDS_REVIEW,
                metadata={
                    "component_id": component.get("component_id", "unknown"),
                    "component_type": component.get("component_type", "project"),
                    "capability_id": assessment.get("capability_id", "unknown"),
                    "relation": "inconsistent",
                    "risk_score": score,
                    "scene": scene,
                },
                source="component_security_v1",
            ))
        return findings
