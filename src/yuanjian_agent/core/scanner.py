from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from ..models import AgentSpec, AgentToolBinding, Finding, ToolSpec
from .context import ScanContext


class SecurityModule(StrEnum):
    SECRET = "secret"
    LICENSE = "license"
    AGENT_SECURITY = "agent_security"


class ScanStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    NOT_APPLICABLE = "not_applicable"


@dataclass(slots=True)
class ScannerResult:
    """Domain-normalized output; no third-party JSON or raw credentials."""

    findings: list[Finding] = field(default_factory=list)
    agents: list[AgentSpec] = field(default_factory=list)
    tools: list[ToolSpec] = field(default_factory=list)
    bindings: list[AgentToolBinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: ScanStatus = ScanStatus.SUCCESS
    providers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class Scanner(Protocol):
    name: SecurityModule

    def scan(self, context: ScanContext) -> ScannerResult: ...
