from __future__ import annotations

from collections.abc import Sequence

from ..analysis import CapabilityAnalyzer, ContextRiskScorer
from ..core.context import ScanContext
from ..core.scanner import ScannerResult, SecurityModule
from ..parsers import ProjectParser, parse_project
from .risk import AgentRiskAnalyzer
from .demo import feature_metadata


class AgentSecurityScanner:
    name = SecurityModule.AGENT_SECURITY

    def __init__(
        self,
        capability_analyzer: CapabilityAnalyzer,
        context_scorer: ContextRiskScorer,
        providers: Sequence[ProjectParser] = (),
    ) -> None:
        self.capability_analyzer = capability_analyzer
        self.risk_analyzer = AgentRiskAnalyzer(context_scorer)
        self.providers = tuple(providers)

    def scan(self, context: ScanContext) -> ScannerResult:
        parsed = parse_project(context.files, providers=self.providers)
        for tool in parsed.tools:
            self.capability_analyzer.analyze(tool)
        findings = self.risk_analyzer.findings(parsed.agents, parsed.tools, parsed.bindings)
        for finding in findings:
            finding.source = "builtin-agent"
        return ScannerResult(
            agents=parsed.agents, tools=parsed.tools, bindings=parsed.bindings,
            findings=findings, warnings=parsed.warnings,
            providers={"builtin-agent": "success"},
            metadata={
                **feature_metadata(context.config),
                "rules_version": str(self.capability_analyzer.rules.get("version", "unknown")),
                "framework_counts": {
                    framework: sum(agent.framework.value == framework for agent in parsed.agents)
                    for framework in ("langchain", "crewai", "mcp", "generic")
                },
                "unresolved_bindings": sum(
                    binding.resolution_status.value in {"unresolved", "ambiguous"}
                    for binding in parsed.bindings
                ),
            },
        )
