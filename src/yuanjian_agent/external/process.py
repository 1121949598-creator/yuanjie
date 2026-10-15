from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

from ..core.context import ScanContext
from ..core.exceptions import ExternalToolUnavailable


@dataclass(frozen=True, slots=True)
class ProcessRequest:
    executable: str
    arguments: tuple[str, ...] = field(default=(), repr=False)
    timeout_seconds: float = 60.0
    cwd: Path | None = None


@dataclass(slots=True)
class ProcessResult:
    """Transient adapter input, never a persisted report or exception payload."""

    exit_code: int
    stdout: str = field(default="", repr=False)
    stderr: str = field(default="", repr=False)
    json_output: Any = field(default=None, repr=False)


class ExternalToolRunner:
    def run(self, request: ProcessRequest) -> ProcessResult:
        """Stub: does not discover executables, spawn processes, or access networks."""
        raise ExternalToolUnavailable()


EvidenceT = TypeVar("EvidenceT")


class ExternalScannerAdapter(Generic[EvidenceT]):
    name: str

    def __init__(self, runner: ExternalToolRunner | None = None) -> None:
        self.runner = runner or ExternalToolRunner()

    def scan(self, context: ScanContext) -> list[EvidenceT]:
        # Deliberately do not invoke even an injected runner in a stub adapter.
        raise ExternalToolUnavailable()
