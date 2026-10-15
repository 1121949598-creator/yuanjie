from __future__ import annotations

from typing import Any

from .models import (
    AgentSpec,
    AgentToolBinding,
    CapabilityEvidence,
    Evidence,
    Finding,
    FindingCategory,
    Framework,
    ResolutionStatus,
    ReviewStatus,
    ScanResult,
    ScanSummary,
    Severity,
    SourceSpan,
    ToolSpec,
)


def _span(data: dict[str, Any]) -> SourceSpan:
    return SourceSpan(**data)


def scan_result_from_dict(data: dict[str, Any]) -> ScanResult:
    agents = [
        AgentSpec(
            id=item["id"],
            framework=Framework(item["framework"]),
            name=item["name"],
            task_text=item["task_text"],
            source_spans=[_span(span) for span in item.get("source_spans", [])],
            extraction_status=item.get("extraction_status", "resolved"),
            extraction_reasons=item.get("extraction_reasons", []),
            metadata=item.get("metadata", {}),
        )
        for item in data.get("agents", [])
    ]
    tools = []
    for item in data.get("tools", []):
        capabilities = [
            CapabilityEvidence(
                capability=cap["capability"],
                impact=int(cap["impact"]),
                source_span=_span(cap["source_span"]),
                symbol=cap["symbol"],
                rationale=cap["rationale"],
                rule_id=cap.get("rule_id", ""),
                rule_version=cap.get("rule_version", ""),
            )
            for cap in item.get("capabilities", [])
        ]
        tools.append(
            ToolSpec(
                id=item["id"],
                framework=Framework(item["framework"]),
                name=item["name"],
                description=item.get("description", ""),
                parameters=item.get("parameters", []),
                source_spans=[_span(span) for span in item.get("source_spans", [])],
                capabilities=capabilities,
                controls=item.get("controls", []),
                body_calls=item.get("body_calls", []),
                extraction_status=item.get("extraction_status", "resolved"),
                extraction_reasons=item.get("extraction_reasons", []),
                metadata=item.get("metadata", {}),
            )
        )
    bindings = [
        AgentToolBinding(
            agent_id=item["agent_id"],
            tool_id=item.get("tool_id"),
            tool_name=item["tool_name"],
            registration_span=_span(item["registration_span"]),
            resolution_status=ResolutionStatus(item["resolution_status"]),
            resolution_reason=item.get("resolution_reason", ""),
        )
        for item in data.get("bindings", [])
    ]
    findings = []
    for item in data.get("findings", []):
        findings.append(
            Finding(
                id=item["id"],
                signature=item["signature"],
                category=FindingCategory(item["category"]),
                rule_id=item["rule_id"],
                severity=Severity(item["severity"]),
                confidence=float(item["confidence"]),
                title=item["title"],
                evidence=[
                    Evidence(
                        source_span=_span(evidence["source_span"]),
                        masked_excerpt=evidence["masked_excerpt"],
                        details=evidence.get("details", {}),
                    )
                    for evidence in item.get("evidence", [])
                ],
                rationale=item.get("rationale", []),
                remediation=item.get("remediation", []),
                review_status=ReviewStatus(item.get("review_status", "open")),
                scan_version=item.get("scan_version", "1"),
                metadata=item.get("metadata", {}),
                source=item.get("source", "builtin"),
                fingerprint=item.get("fingerprint", ""),
            )
        )
    return ScanResult(
        id=data["id"],
        project_name=data["project_name"],
        source_path=data["source_path"],
        created_at=data["created_at"],
        status=data["status"],
        version=data["version"],
        agents=agents,
        tools=tools,
        bindings=bindings,
        findings=findings,
        warnings=data.get("warnings", []),
        summary=ScanSummary(**data.get("summary", {})),
        parent_scan_id=data.get("parent_scan_id"),
        safe_copy_path=data.get("safe_copy_path"),
        comparison=data.get("comparison", {}),
        metadata=data.get("metadata", {}),
    )
