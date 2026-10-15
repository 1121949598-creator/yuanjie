from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from ..files import TextFile
from ..models import Finding


@dataclass(slots=True)
class ScanContext:
    """One invocation's static input. Never serialize source text or this context."""

    scan_id: str
    project_root: Path
    source_type: str
    config: Settings = field(repr=False)
    temp_dir: Path
    files: list[TextFile] = field(default_factory=list, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)
    upstream_findings: tuple[Finding, ...] = field(default=(), repr=False)
    upstream_statuses: dict[str, str] = field(default_factory=dict)
