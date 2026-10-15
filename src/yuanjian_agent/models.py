from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Framework(StrEnum):
    LANGCHAIN = "langchain"
    CREWAI = "crewai"
    MCP = "mcp"
    GENERIC = "generic"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingCategory(StrEnum):
    SECRET = "secret"
    LICENSE = "license"
    AGENT_SECURITY = "agent_security"
    TOOL_CAPABILITY = "tool_capability"
    TOOL_EXPOSURE = "tool_exposure"
    UNRESOLVED = "unresolved"


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    RESOLVED_BY_NAME = "resolved_by_name"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class ReviewStatus(StrEnum):
    OPEN = "open"
    NEEDS_REVIEW = "needs_review"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"
    REMAINING = "remaining"
    NEW = "new"


@dataclass(slots=True)
class SourceSpan:
    path: str
    start_line: int
    end_line: int
    start_column: int = 0
    end_column: int = 0


@dataclass(slots=True)
class CapabilityEvidence:
    capability: str
    impact: int
    source_span: SourceSpan
    symbol: str
    rationale: str
    rule_id: str = ""
    rule_version: str = ""


@dataclass(slots=True)
class AgentSpec:
    id: str
    framework: Framework
    name: str
    task_text: str
    source_spans: list[SourceSpan] = field(default_factory=list)
    extraction_status: str = "resolved"
    extraction_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolSpec:
    id: str
    framework: Framework
    name: str
    description: str
    parameters: list[str]
    source_spans: list[SourceSpan] = field(default_factory=list)
    capabilities: list[CapabilityEvidence] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    body_calls: list[str] = field(default_factory=list)
    extraction_status: str = "resolved"
    extraction_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentToolBinding:
    agent_id: str
    tool_id: str | None
    tool_name: str
    registration_span: SourceSpan
    resolution_status: ResolutionStatus
    resolution_reason: str = ""


@dataclass(slots=True)
class Evidence:
    source_span: SourceSpan
    masked_excerpt: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Finding:
    id: str
    signature: str
    category: FindingCategory
    rule_id: str
    severity: Severity
    confidence: float
    title: str
    evidence: list[Evidence]
    rationale: list[str]
    remediation: list[str]
    review_status: ReviewStatus = ReviewStatus.OPEN
    scan_version: str = "1"
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "builtin"
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = (
                self.evidence[0].details.get("fingerprint", self.signature)
                if self.evidence else self.signature
            )

    @property
    def location(self) -> SourceSpan | None:
        return self.evidence[0].source_span if self.evidence else None


@dataclass(slots=True)
class ScanSummary:
    total_findings: int = 0
    secrets: int = 0
    tool_exposures: int = 0
    unresolved: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    licenses: int = 0
    agent_security: int = 0
    tool_capabilities: int = 0


@dataclass(slots=True)
class ScanResult:
    id: str
    project_name: str
    source_path: str
    created_at: str
    status: str
    version: str
    agents: list[AgentSpec] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    bindings: list[AgentToolBinding] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: ScanSummary = field(default_factory=ScanSummary)
    parent_scan_id: str | None = None
    safe_copy_path: str | None = None
    comparison: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScanLimits:
    max_files: int = 5_000
    max_file_bytes: int = 2 * 1024 * 1024
    max_total_bytes: int = 100 * 1024 * 1024
    max_archive_ratio: float = 200.0


@dataclass(slots=True)
class ProjectSource:
    root: Path
    display_name: str
    original_path: Path
    temporary: bool = False
    warnings: list[str] = field(default_factory=list)
