from __future__ import annotations

from collections import Counter

from ..core.scanner import ScanStatus, SecurityModule
from ..models import Evidence, Finding, ScanResult, SourceSpan
from .query import (
    ScanNotReady, SecretQuery, SecretQueryRepository, ordered_evidence, secret_type,
)
from .remediation import remediation_for
from .schemas import (
    SecretDetailResponse, SecretEvidenceResponse, SecretFindingItem, SecretLocationResponse,
    SecretOverviewResponse, SecretPaginationResponse, SecretSummaryResponse, compact_mask,
)


_FINAL_SCAN_STATUSES = frozenset({"completed", "partial", "failed", "unavailable"})
_STATUS_DIAGNOSTICS = {
    ScanStatus.SUCCESS: (),
    ScanStatus.PARTIAL: ("Secret coverage is partial; available findings are retained.",),
    ScanStatus.FAILED: ("Secret scanning failed; this result does not establish a clean scan.",),
    ScanStatus.DISABLED: ("Secret scanning was disabled for this scan.",),
    ScanStatus.UNAVAILABLE: ("Secret coverage is unavailable or was not recorded.",),
    ScanStatus.NOT_APPLICABLE: ("Secret scanning was recorded as not applicable; this is not a clean-scan result.",),
}


class SecretQueryService:
    def __init__(self, repository: SecretQueryRepository) -> None:
        self.repository = repository

    def _load(self, scan_id: str) -> ScanResult:
        scan = self.repository.load(scan_id)
        if scan.status not in _FINAL_SCAN_STATUSES:
            raise ScanNotReady()
        return scan

    @staticmethod
    def _coverage(scan: ScanResult) -> tuple[ScanStatus, list[str]]:
        state = scan.metadata.get("scanners", {}).get(SecurityModule.SECRET, {}).get("status")
        try:
            status = ScanStatus(state)
        except (TypeError, ValueError):
            status = ScanStatus.UNAVAILABLE
        diagnostics = list(_STATUS_DIAGNOSTICS[status])
        if scan.warnings:
            # Warnings may contain old diagnostic payloads; do not reflect their contents.
            diagnostics.append("The saved scan contains warnings; review overall scan coverage.")
        return status, diagnostics

    @staticmethod
    def _location(span: SourceSpan) -> SecretLocationResponse:
        return SecretLocationResponse(
            file_path=span.path, line=span.start_line, end_line=span.end_line,
            column_start=span.start_column, column_end=span.end_column,
        )

    @staticmethod
    def _masked_value(finding: Finding, evidence: Evidence | None) -> str:
        # Never extract a source line or parse arbitrary details for a value.
        if evidence is not None:
            value = evidence.details.get("masked_value")
            if value is not None:
                return compact_mask(value)
        value = finding.metadata.get("masked_value")
        if value is not None:
            return compact_mask(value)
        return compact_mask(evidence.masked_excerpt if evidence is not None else None)

    def _item(self, finding: Finding) -> SecretFindingItem:
        occurrences = ordered_evidence(finding)
        primary = occurrences[0] if occurrences else None
        return SecretFindingItem(
            finding_id=finding.id, rule_id=finding.rule_id, secret_type=secret_type(finding),
            severity=finding.severity, confidence=finding.confidence, message=finding.title,
            location=self._location(primary.source_span) if primary else None,
            masked_value=self._masked_value(finding, primary), occurrence_count=len(occurrences),
        )

    def overview(self, scan_id: str, query: SecretQuery | None = None) -> SecretOverviewResponse:
        query = query or SecretQuery()
        scan = self._load(scan_id)
        findings = self.repository.findings(scan)
        page = self.repository.page(findings, query)
        severities = Counter(item.severity.value for item in findings)
        types = Counter(secret_type(item) for item in findings)
        status, diagnostics = self._coverage(scan)
        return SecretOverviewResponse(
            scan_id=scan.id, status=status, scan_status=scan.status, diagnostics=diagnostics,
            summary=SecretSummaryResponse(total=len(findings), **severities),
            by_type=dict(sorted(types.items())),
            pagination=SecretPaginationResponse(page=query.page, page_size=query.page_size, total=page.total),
            items=[self._item(item) for item in page.items],
        )

    def detail(self, scan_id: str, finding_id: str) -> SecretDetailResponse:
        scan = self._load(scan_id)
        finding = self.repository.find(scan, finding_id)
        status, diagnostics = self._coverage(scan)
        evidence = []
        for occurrence in ordered_evidence(finding):
            value = self._masked_value(finding, occurrence)
            # Both fields remain compact; historical excerpts cannot disclose neighbours.
            excerpt = compact_mask(occurrence.masked_excerpt)
            evidence.append(SecretEvidenceResponse(
                location=self._location(occurrence.source_span),
                masked_value=value, masked_excerpt=excerpt,
            ))
        item = self._item(finding)
        return SecretDetailResponse(
            **item.model_dump(), scan_id=scan.id, status=status, scan_status=scan.status,
            diagnostics=diagnostics, evidence=evidence, remediation=remediation_for(item.secret_type),
        )
