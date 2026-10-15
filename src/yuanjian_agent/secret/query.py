from __future__ import annotations

from dataclasses import dataclass, field
import math

from ..models import Evidence, Finding, FindingCategory, ScanResult, Severity
from ..storage import ScanStore


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Compatibility mapping for results saved before secret_type was introduced.
# This is presentation metadata, not a detection-rule registry.
TYPE_BY_RULE = {
    "secret.private-key": "private_key",
    "secret.aws-access-key": "aws_access_key",
    "secret.jwt": "jwt",
    "secret.database-url": "database_credential",
    "secret.generic-assignment": "password",
    "secret.generic-api-key": "api_key",
    "secret.generic-token": "token",
    "secret.high-entropy-assignment": "token",
    "secret.github-token": "api_key",
    "secret.openai-key": "api_key",
}
SEVERITY_RANK = {severity: rank for rank, severity in enumerate(Severity)}


class SecretQueryError(Exception):
    """Fixed public errors; never attach identifiers, stored data or exception text."""

    status_code = 500
    detail = "Secret results could not be loaded"

    def __init__(self) -> None:
        super().__init__(self.detail)


class ScanNotFound(SecretQueryError):
    status_code = 404
    detail = "Scan not found"


class SecretNotFound(SecretQueryError):
    status_code = 404
    detail = "Secret finding not found in this scan"


class ScanNotReady(SecretQueryError):
    status_code = 409
    detail = "Scan results are not final"


class InvalidSecretQuery(SecretQueryError):
    status_code = 422
    detail = "Invalid Secret query parameters"


@dataclass(frozen=True, slots=True)
class SecretQuery:
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    severity: Severity | None = None
    secret_type: str | None = field(default=None, repr=False)
    file_path: str | None = field(default=None, repr=False)
    rule_id: str | None = field(default=None, repr=False)
    min_confidence: float | None = None

    def __post_init__(self) -> None:
        if (type(self.page) is not int or self.page < 1
                or type(self.page_size) is not int or not 1 <= self.page_size <= MAX_PAGE_SIZE):
            raise InvalidSecretQuery()
        if self.severity is not None and not isinstance(self.severity, Severity):
            raise InvalidSecretQuery()
        if self.min_confidence is not None and (
            not math.isfinite(self.min_confidence) or not 0 <= self.min_confidence <= 1
        ):
            raise InvalidSecretQuery()
        for value in (self.secret_type, self.file_path, self.rule_id):
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 256):
                raise InvalidSecretQuery()


@dataclass(frozen=True, slots=True)
class SecretPage:
    items: tuple[Finding, ...] = field(repr=False)
    total: int


def secret_type(finding: Finding) -> str:
    value = finding.metadata.get("secret_type")
    if isinstance(value, str) and value:
        return value
    return TYPE_BY_RULE.get(finding.rule_id, "unknown")


def ordered_evidence(finding: Finding) -> list[Evidence]:
    return sorted(finding.evidence, key=lambda item: (
        item.source_span.path, item.source_span.start_line, item.source_span.start_column,
        item.source_span.end_line, item.source_span.end_column,
    ))


def finding_sort_key(finding: Finding) -> tuple:
    evidence = ordered_evidence(finding)
    span = evidence[0].source_span if evidence else None
    return (
        -SEVERITY_RANK[finding.severity], -finding.confidence,
        span.path if span else "", span.start_line if span else 0,
        span.start_column if span else 0, finding.rule_id, finding.id,
    )


class SecretQueryRepository:
    """Query adapter over ScanStore's existing single saved-result read.

    The result JSON contains all evidence. Filtering in memory avoids a second
    schema or per-finding queries; this class never accesses source files.
    """

    def __init__(self, store: ScanStore) -> None:
        self.store = store

    def load(self, scan_id: str) -> ScanResult:
        try:
            return self.store.get(scan_id)
        except KeyError:
            raise ScanNotFound() from None

    @staticmethod
    def findings(scan: ScanResult) -> tuple[Finding, ...]:
        return tuple(item for item in scan.findings if item.category == FindingCategory.SECRET)

    @staticmethod
    def page(findings: tuple[Finding, ...], query: SecretQuery) -> SecretPage:
        selected = [
            item for item in findings
            if (query.severity is None or item.severity == query.severity)
            and (query.secret_type is None or secret_type(item) == query.secret_type)
            and (query.rule_id is None or item.rule_id == query.rule_id)
            and (query.min_confidence is None or item.confidence >= query.min_confidence)
            and (query.file_path is None or any(
                query.file_path.casefold() in evidence.source_span.path.casefold()
                for evidence in item.evidence
            ))
        ]
        selected.sort(key=finding_sort_key)
        offset = (query.page - 1) * query.page_size
        return SecretPage(tuple(selected[offset:offset + query.page_size]), len(selected))

    @staticmethod
    def find(scan: ScanResult, finding_id: str) -> Finding:
        finding = next((item for item in scan.findings
                        if item.category == FindingCategory.SECRET and item.id == finding_id), None)
        if finding is None:
            raise SecretNotFound()
        return finding

