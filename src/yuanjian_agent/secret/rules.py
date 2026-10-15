from __future__ import annotations

import importlib.resources
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Pattern

import yaml

from ..models import Severity


@dataclass(frozen=True, slots=True)
class SecretRule:
    id: str
    name: str
    secret_type: str
    pattern: Pattern[str]
    severity: Severity
    confidence: float
    validator: str = "literal"
    min_length: int = 0
    min_entropy: float = 0.0
    priority: int = 100


def load_secret_rules(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    resource = importlib.resources.files("yuanjian_agent.default_rules").joinpath("secrets.yml")
    return yaml.safe_load(resource.read_text(encoding="utf-8"))


def compile_rules(config: dict[str, Any]) -> tuple[SecretRule, ...]:
    """Compile the existing YAML registry into typed, immutable rules."""
    try:
        return tuple(SecretRule(
            id=item["id"], name=item["description"],
            secret_type=item.get("secret_type", "secret"),
            pattern=re.compile(item["pattern"]),
            severity=Severity(item.get("severity", "medium")),
            confidence=float(item.get("confidence", 0.6)),
            validator=item.get("validator", "literal"),
            min_length=int(item.get("min_length", 0)),
            min_entropy=float(item.get("min_entropy", 0)),
            priority=int(item.get("priority", 100)),
        ) for item in config.get("rules", []))
    except (KeyError, TypeError, ValueError, re.error):
        raise ValueError("Invalid Secret rule configuration; diagnostic details suppressed") from None


SECRET_RULES = compile_rules(load_secret_rules())

# Validation expressions live beside detection expressions, never in the scan loop.
PLACEHOLDER_WORDS = re.compile(r"[^a-z0-9]+")
REPEATED_VALUE = re.compile(r"(.)\1{2,}\Z", re.DOTALL)
TEMPLATE = re.compile(r"\$\{|\{\{|<[^>]+>|\$[A-Za-z_]\w*|%[A-Za-z_]\w*%")
ENV_REFERENCE = re.compile(r"(?i)^(?:os\.(?:getenv|environ)|getenv|env\(|process\.env|System\.getenv|ENV\[)")
UUID_VALUE = re.compile(r"(?i)[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\Z")
HASH_VALUE = re.compile(r"(?i)(?:[a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64}|[a-f0-9]{128})\Z")
