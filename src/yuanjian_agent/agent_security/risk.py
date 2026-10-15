from __future__ import annotations

from ..analysis import ContextRiskScorer, ExposureScore
from ..models import (
    AgentSpec, AgentToolBinding, Evidence, Finding, FindingCategory,
    ResolutionStatus, ReviewStatus, Severity, ToolSpec,
)
from ..core.identifiers import stable_id


def _severity_for_exposure(score: ExposureScore) -> Severity:
    if score.score >= 4.0:
        return Severity.CRITICAL
    if score.score >= 3.0:
        return Severity.HIGH
    if score.score >= 1.8:
        return Severity.MEDIUM
    return Severity.LOW


class AgentRiskAnalyzer:
    """Existing Agent finding construction and score thresholds, moved unchanged."""

    def __init__(self, context_scorer: ContextRiskScorer) -> None:
        self.context_scorer = context_scorer
        self.rules_version = str(context_scorer.rules.get("version", "unknown"))

    def findings(
        self,
        agents: list[AgentSpec],
        tools: list[ToolSpec],
        bindings: list[AgentToolBinding],
    ) -> list[Finding]:
        findings: list[Finding] = []
        agent_map = {agent.id: agent for agent in agents}
        tool_map = {tool.id: tool for tool in tools}
        for binding in bindings:
            agent = agent_map.get(binding.agent_id)
            tool = tool_map.get(binding.tool_id) if binding.tool_id else None
            if binding.resolution_status in {ResolutionStatus.UNRESOLVED, ResolutionStatus.AMBIGUOUS}:
                signature = stable_id(
                    "sig", "unresolved", binding.registration_span.path, binding.agent_id, binding.tool_name
                )
                findings.append(
                    Finding(
                        id=stable_id("finding", signature),
                        signature=signature,
                        category=FindingCategory.UNRESOLVED,
                        rule_id="agent.binding-unresolved",
                        severity=Severity.LOW,
                        confidence=1.0,
                        title=f"Tool binding could not be resolved statically: {binding.tool_name}",
                        evidence=[
                            Evidence(
                                source_span=binding.registration_span,
                                masked_excerpt=binding.tool_name[:300],
                                details={
                                    "resolution_status": binding.resolution_status.value,
                                    "resolution_reason": binding.resolution_reason,
                                    "agent_id": binding.agent_id,
                                },
                            )
                        ],
                        rationale=[
                            "The tool list is dynamic, ambiguous, or only available after starting an MCP server",
                            "源界 does not execute the project to resolve it",
                        ],
                        remediation=[
                            "Use a literal, reviewable tool allowlist where practical",
                            "Document the runtime tool discovery boundary for manual review",
                        ],
                        review_status=ReviewStatus.NEEDS_REVIEW,
                        metadata={"tool_rules_version": self.rules_version},
                    )
                )
                if tool is None:
                    continue
            if agent is None or tool is None or not tool.capabilities:
                continue
            score = self.context_scorer.score(agent.task_text, tool)
            if score.impact < 3 or score.probability < 0.35:
                continue
            span = tool.source_spans[0] if tool.source_spans else binding.registration_span
            signature = stable_id("sig", "exposure", span.path, agent.name, tool.name)
            capabilities = ", ".join(
                f"{cap.capability}({cap.impact}/5)" for cap in sorted(tool.capabilities, key=lambda item: -item.impact)
            )
            review_status = (
                ReviewStatus.NEEDS_REVIEW
                if score.probability < 0.65 or score.uncertainty_reasons
                else ReviewStatus.OPEN
            )
            binding_evidence = Evidence(
                source_span=binding.registration_span,
                masked_excerpt=f"Agent={agent.name}; registered Tool={binding.tool_name}"[:500],
                details={
                    "agent_id": agent.id,
                    "tool_id": tool.id,
                    "tool_symbol": tool.metadata.get("symbol", binding.tool_name),
                    "resolution_status": binding.resolution_status.value,
                    "resolution_reason": binding.resolution_reason,
                    "evidence_kind": "registration",
                },
            )
            findings.append(
                Finding(
                    id=stable_id("finding", signature),
                    signature=signature,
                    category=FindingCategory.TOOL_EXPOSURE,
                    rule_id="agent.task-tool-overexposure",
                    severity=_severity_for_exposure(score),
                    confidence=score.probability,
                    title=f"Potential over-exposed tool: {tool.name}",
                    evidence=[
                        Evidence(
                            source_span=span,
                            masked_excerpt=f"Agent={agent.name}; Tool={tool.name}; Capabilities={capabilities}"[:500],
                            details={
                                "agent_id": agent.id,
                                "tool_id": tool.id,
                                "impact": score.impact,
                                "necessity_signal": score.similarity,
                                "exposure_score": score.score,
                                "model": score.model,
                                "uncertainty_reasons": score.uncertainty_reasons,
                                "tool_rules_version": self.rules_version,
                                "evidence_kind": "implementation",
                            },
                        ),
                        binding_evidence,
                    ],
                    rationale=score.reasons,
                    remediation=self._tool_remediation(tool),
                    review_status=review_status,
                    metadata={
                        "agent_task": agent.task_text[:1000],
                        "controls": tool.controls,
                        "tool_rules_version": self.rules_version,
                        "scoring_model": score.model,
                        "uncertainty_reasons": score.uncertainty_reasons,
                    },
                )
            )
        return findings

    @staticmethod
    def _tool_remediation(tool: ToolSpec) -> list[str]:
        actions = ["Remove the tool from the agent allowlist if it is not required for the declared task"]
        capability_names = {cap.capability for cap in tool.capabilities}
        if capability_names & {"file_write", "file_delete", "database_modify", "external_state_change"}:
            actions.append("Require human confirmation before irreversible or externally visible actions")
        if capability_names & {"file_read", "file_write", "file_delete"}:
            actions.append("Restrict filesystem access to an explicit project root and reject path traversal")
        if "network_access" in capability_names:
            actions.append("Restrict destinations to an explicit host allowlist and enforce request timeouts")
        if "shell_execute" in capability_names:
            actions.append("Replace general shell execution with a narrow command adapter or sandbox")
        return actions

