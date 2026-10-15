from copy import deepcopy

import pytest
from pydantic import ValidationError

from test_secret_query import finding, scan
from yuanjian_agent.core.scanner import ScanStatus
from yuanjian_agent.models import Evidence, SourceSpan
from yuanjian_agent.secret.query import ScanNotReady, SecretNotFound, SecretQuery, SecretQueryRepository
from yuanjian_agent.secret.remediation import remediation_for
from yuanjian_agent.secret.schemas import SecretEvidenceResponse, SecretLocationResponse
from yuanjian_agent.secret.service import SecretQueryService


class SavedStore:
    def __init__(self, saved):
        self.saved = saved
        self.reads = 0

    def get(self, scan_id):
        self.reads += 1
        assert scan_id == self.saved.id
        return self.saved


def service(saved):
    return SecretQueryService(SecretQueryRepository(SavedStore(saved)))


def test_service_aggregates_scan_before_filtering():
    saved = scan(findings=[finding("a"), finding("b", kind="token")])
    result = service(saved).overview("scan-a", SecretQuery(secret_type="token"))
    assert result.summary.total == 2
    assert result.by_type == {"api_key": 1, "token": 1}
    assert result.pagination.total == 1
    assert [item.finding_id for item in result.items] == ["b"]


def test_service_one_read_per_request_with_one_hundred_findings():
    repository = SecretQueryRepository(SavedStore(scan(findings=[finding(str(i)) for i in range(100)])))
    query_service = SecretQueryService(repository)
    assert len(query_service.overview("scan-a", SecretQuery(page_size=100)).items) == 100
    assert repository.store.reads == 1
    assert query_service.detail("scan-a", "50").finding_id == "50"
    assert repository.store.reads == 2


def test_service_does_not_mutate_persisted_models():
    saved = scan(findings=[finding("b"), finding("a")])
    before = deepcopy(saved)
    query_service = service(saved)
    query_service.overview("scan-a")
    query_service.detail("scan-a", "a")
    assert saved == before


def test_service_preserves_all_locations_and_multiline_end():
    item = finding("a", path="z.py")
    item.evidence.append(Evidence(SourceSpan("a.pem", 4, 8, 2, 20), "****"))
    result = service(scan(findings=[item])).detail("scan-a", "a")
    assert result.occurrence_count == 2
    assert result.location.file_path == "a.pem"
    assert result.location.end_line == 8 and result.location.column_end == 20
    assert [e.location.file_path for e in result.evidence] == ["a.pem", "z.py"]


def test_service_handles_missing_legacy_location_and_mask():
    item = finding("a")
    item.evidence = []
    item.metadata = {}
    saved = scan(findings=[item])
    saved.metadata = {}
    result = service(saved).detail("scan-a", "a")
    assert result.location is None and result.evidence == []
    assert result.masked_value == "****" and result.secret_type == "api_key"
    assert result.status == ScanStatus.UNAVAILABLE


def test_service_missing_scoped_secret():
    with pytest.raises(SecretNotFound):
        service(scan(findings=[finding("a")])).detail("scan-a", "b")


@pytest.mark.parametrize("state", ["pending", "running", "queued", "scanning", "unknown"])
def test_service_unfinished_scan_is_not_presented_as_complete(state):
    with pytest.raises(ScanNotReady):
        service(scan(status=state)).overview("scan-a")


@pytest.mark.parametrize("kind", ["private_key", "aws_access_key", "api_key",
    "database_credential", "jwt", "password", "token", "future_type"])
def test_remediation_mapping_and_fallback(kind):
    result = remediation_for(kind)
    assert result.title and len(result.steps) >= 3
    assert any("rotat" in step.lower() or "change" in step.lower() or "revoke" in step.lower()
               for step in result.steps)


def test_remediation_returns_independent_steps():
    first = remediation_for("api_key")
    first.steps.clear()
    assert remediation_for("api_key").steps


@pytest.mark.parametrize("mask", ["****", "sk-****abcd", "abc************xyz"])
def test_schema_accepts_existing_compact_masks(mask):
    location = SecretLocationResponse(file_path="a.py", line=1, end_line=1, column_start=0, column_end=8)
    evidence = SecretEvidenceResponse(location=location, masked_value=mask, masked_excerpt=mask)
    assert evidence.masked_value == evidence.masked_excerpt == mask


@pytest.mark.parametrize("value", ["unmasked-synthetic-value", 'API_KEY="sk-****abcd"; other="sensitive"',
                                    "sk-****abcd\n", None])
def test_schema_withholds_noncompact_evidence(value):
    location = SecretLocationResponse(file_path="a.py", line=1, end_line=1, column_start=0, column_end=8)
    evidence = SecretEvidenceResponse(location=location, masked_value=value, masked_excerpt=value)
    assert evidence.masked_value == evidence.masked_excerpt == "****"


def test_schema_rejects_internal_extra_fields_without_printing_input():
    with pytest.raises(ValidationError) as error:
        SecretLocationResponse(file_path="a.py", line=1, end_line=1, column_start=0, column_end=8,
                               raw_value="synthetic-input-must-not-be-printed")
    assert "synthetic-input-must-not-be-printed" not in str(error.value)

