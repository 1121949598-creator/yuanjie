from __future__ import annotations

import hashlib
import hmac
import os
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core.redaction import sanitize_value
from .files import TextFile
from .models import Evidence, Finding, ReviewStatus, Severity, SourceSpan
from .secret.entropy import shannon_entropy
from .secret.masking import mask_secret
from .secret.models import SecretEvidence
from .secret.normalizer import normalize_secret
from .secret.rules import SECRET_RULES, compile_rules, load_secret_rules
from .secret.validator import is_placeholder, validate_candidate


def secret_fingerprint(value: str, key: bytes) -> str:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def load_or_create_fingerprint_key(path: Path) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes()
    key = os.urandom(32)
    temp = path.with_suffix(".tmp")
    temp.write_bytes(key)
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(path)
    return key


@dataclass(slots=True)
class SecretMatch:
    """Transient candidate only: never serialize, log or attach to results."""

    value: str = field(repr=False)
    rule_id: str
    description: str
    severity: Severity
    start: int
    end: int
    entropy: float
    secret_type: str = "secret"
    confidence: float = 0.6
    priority: int = 100


@dataclass(slots=True)
class ScanRedactor:
    """Invocation-local known candidates; never serialized or logged."""

    scanner: SecretScanner = field(repr=False)
    values: tuple[str, ...] = field(repr=False)

    def redact_text(self, text: str) -> str:
        for value in self.values:
            text = text.replace(value, mask_secret(value))
        return self.scanner.redact_text(text)


_SEVERITY_RANK = {severity: rank for rank, severity in enumerate(Severity)}
_RULE_FAILURE = "builtin-secret: rule failed; diagnostic details suppressed"
_FILE_FAILURE = "builtin-secret: file failed; diagnostic details suppressed"


class SecretScanner:
    """Existing built-in detector; the module coordinator owns ScannerResult."""

    def __init__(self, fingerprint_key: bytes, rules: dict[str, Any] | None = None) -> None:
        self.fingerprint_key = fingerprint_key
        self.rules = rules if rules is not None else load_secret_rules()
        self.compiled = compile_rules(rules) if rules is not None else SECRET_RULES
        self.placeholders = {str(value).lower() for value in self.rules.get("placeholders", [])}
        self.warnings: list[str] = []

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def scan(self, files: list[TextFile]) -> list[Finding]:
        self.warnings = []
        findings: list[Finding] = []
        for file in files:
            try:
                findings.extend(self.scan_file(file))
            except Exception:
                # Per-file isolation; never retain exception text or source fragments.
                self._warn(_FILE_FAILURE)
        # Also protect target-controlled paths containing any known credential.
        sanitize_value(findings, self.redactor_for(files))
        return findings

    def scan_file(self, file: TextFile) -> list[Finding]:
        """Scan an already-read TextFile; lines are 1-based, columns 0-based/end-exclusive."""
        matches = self._select_matches(self.matches(file.text))
        line_starts = [0]
        line_starts.extend(index + 1 for index, char in enumerate(file.text) if char == "\n")
        findings = [self._finding(file, match, line_starts) for match in matches]
        sanitize_value(findings, self.redactor_for([file]))
        return findings

    @staticmethod
    def _select_matches(matches: list[SecretMatch]) -> list[SecretMatch]:
        # Prefer specific/full matches over nested generic assignments, retain all locations.
        selected: list[SecretMatch] = []
        for match in sorted(matches, key=lambda item: (
            -item.priority, -_SEVERITY_RANK[item.severity], -item.confidence, -(item.end - item.start)
        )):
            if not any(match.start < item.end and item.start < match.end for item in selected):
                selected.append(match)
        return sorted(selected, key=lambda item: item.start)

    def matches(self, text: str) -> list[SecretMatch]:
        """Return validated candidates in memory, including multiline private keys."""
        return self._matches(text)

    def redactor_for(self, files: list[TextFile]) -> ScanRedactor:
        """Redaction is mandatory even with disabled/failed Secret findings."""
        values: set[str] = set()
        for file in files:
            try:
                for match in self._matches(file.text, validate=False):
                    if not match.value:
                        continue
                    values.add(match.value)
                    if match.secret_type == "private_key":
                        # Agent parsers may detach individual body lines from their PEM block.
                        values.update(line.strip() for line in match.value.splitlines() if line.strip())
            except Exception:
                self._warn(_FILE_FAILURE)
        return ScanRedactor(self, tuple(sorted(values, key=len, reverse=True)))

    def redact_text(self, text: str) -> str:
        """Mask candidate spans; exclude placeholders and executable references."""
        intervals: list[list[int]] = []
        for match in sorted(self._matches(text, validate=False), key=lambda item: item.start):
            if intervals and match.start <= intervals[-1][1]:
                intervals[-1][1] = max(intervals[-1][1], match.end)
            else:
                intervals.append([match.start, match.end])
        for start, end in reversed(intervals):
            text = text[:start] + mask_secret(text[start:end]) + text[end:]
        return text

    def _matches(self, text: str, *, validate: bool = True) -> list[SecretMatch]:
        matches: list[SecretMatch] = []
        for rule in self.compiled:
            try:
                for match in rule.pattern.finditer(text):
                    group = next((name for name in ("secret", "bare_secret")
                                  if match.groupdict().get(name) is not None), 0)
                    value = match.group(group)
                    if not value or is_placeholder(value, self.placeholders):
                        continue
                    # These exclusions apply to redaction too: a placeholder such as
                    # "token" must not rewrite result types, keys or fixed messages.
                    if group == "bare_secret" and any(c in value for c in "()[]"):
                        continue
                    if not validate and len(value) < rule.min_length:
                        continue
                    if validate:
                        if not validate_candidate(rule, value, self.placeholders):
                            continue
                    matches.append(SecretMatch(
                        value=value, rule_id=rule.id, description=rule.name,
                        severity=rule.severity, start=match.start(group), end=match.end(group),
                        entropy=shannon_entropy(value), secret_type=rule.secret_type,
                        confidence=rule.confidence, priority=rule.priority,
                    ))
            except Exception:
                # Broken rules/validators do not stop other rules or reveal their input.
                self._warn(_RULE_FAILURE)
        return matches

    def _finding(self, file: TextFile, match: SecretMatch, line_starts: list[int]) -> Finding:
        path = Path(file.relative_path.lower())
        doc_or_test = any(part in {"docs", "doc", "examples", "example", "tests", "test"} for part in path.parts)
        env_example = path.name in {".env.example", ".env.sample"}
        config_like = (path.name == ".env" or path.name.startswith((".env.", "config.", "settings."))
                       or path.suffix in {".properties", ".toml", ".ini", ".conf"})
        confidence = max(0.01, min(0.99, match.confidence - 0.18 * doc_or_test
                                  - 0.22 * env_example + 0.13 * config_like))
        fingerprint = secret_fingerprint(match.value, self.fingerprint_key)
        start_line = bisect_right(line_starts, match.start)
        end_line = bisect_right(line_starts, match.end)
        span = SourceSpan(
            file.relative_path, start_line, end_line,
            match.start - line_starts[start_line - 1], match.end - line_starts[end_line - 1],
        )
        masked_value = mask_secret(match.value)
        # Do not copy source context: a neighbouring/unknown secret must never enter evidence.
        return normalize_secret(SecretEvidence(
            evidence=Evidence(
                source_span=span, masked_excerpt=masked_value,
                details={"fingerprint": fingerprint, "entropy": round(match.entropy, 4),
                         "masked_value": masked_value},
            ),
            rule_id=match.rule_id, title=match.description, severity=match.severity,
            confidence=round(confidence, 4),
            rationale=[f"Matched rule {match.rule_id}", "Offline syntax and literal validation",
                       f"Candidate entropy is {match.entropy:.2f}"],
            review_status=ReviewStatus.NEEDS_REVIEW if confidence < 0.7 else ReviewStatus.OPEN,
            metadata={"secret_type": match.secret_type, "masked_value": masked_value,
                      "context": {"doc_or_test": doc_or_test, "env_example": env_example,
                                  "config_like": config_like}},
        ))
