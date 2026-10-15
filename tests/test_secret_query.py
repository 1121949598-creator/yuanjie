from pathlib import Path

import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.models import Evidence, Finding, FindingCategory, ScanResult, Severity, SourceSpan
from yuanjian_agent.secret.query import (
    InvalidSecretQuery, ScanNotFound, SecretNotFound, SecretQuery, SecretQueryRepository, secret_type,
)
from yuanjian_agent.storage import ScanStore


def finding(identifier, severity=Severity.HIGH, kind="api_key", path="config.py", line=1,
            confidence=0.8, category=FindingCategory.SECRET):
    return Finding(
        id=identifier, signature=identifier, category=category, rule_id="secret.generic-api-key",
        severity=severity, confidence=confidence, title="Potential credential",
        evidence=[Evidence(SourceSpan(path, line, line, 10, 30), "sk-****abcd",
                           {"masked_value": "sk-****abcd"})],
        rationale=[], remediation=[], metadata={"secret_type": kind, "masked_value": "sk-****abcd"},
    )


def scan(identifier="scan-a", findings=(), status="completed", module_status="success"):
    return ScanResult(
        identifier, "synthetic-project", "/source/not-needed", "2026-09-09", status, "1",
        findings=list(findings), metadata={"scanners": {"secret": {"status": module_status, "providers": {}}}},
    )


@pytest.fixture
def store(tmp_path):
    return ScanStore(Settings(data_dir=tmp_path / "state"))


def test_query_reads_saved_secrets_only(store):
    store.save(scan(findings=[finding("a"), finding("b", category=FindingCategory.LICENSE)]))
    repository = SecretQueryRepository(store)
    persisted = repository.load("scan-a")
    assert [f.id for f in repository.findings(persisted)] == ["a"]


def test_query_missing_scan_has_fixed_error(store):
    with pytest.raises(ScanNotFound, match="^Scan not found$"):
        SecretQueryRepository(store).load("absent")


def test_query_composite_scope_and_category(store):
    store.save(scan("a", [finding("other", category=FindingCategory.LICENSE)]))
    store.save(scan("b", [finding("secret-b")]))
    repository = SecretQueryRepository(store)
    for identifier in ("secret-b", "other", "missing"):
        with pytest.raises(SecretNotFound):
            repository.find(repository.load("a"), identifier)


def test_query_same_finding_id_in_two_scans_is_scoped(store):
    store.save(scan("a", [finding("shared", path="a.py")]))
    store.save(scan("b", [finding("shared", path="b.py")]))
    repository = SecretQueryRepository(store)
    assert repository.find(repository.load("a"), "shared").location.path == "a.py"
    assert repository.find(repository.load("b"), "shared").location.path == "b.py"


def test_query_filter_sort_and_page():
    rows = (
        finding("low", Severity.LOW), finding("b", path="b.py"),
        finding("a", path="a.py"), finding("critical", Severity.CRITICAL, kind="private_key"),
    )
    result = SecretQueryRepository.page(rows, SecretQuery(page=2, page_size=1, severity=Severity.HIGH))
    assert result.total == 2 and [item.id for item in result.items] == ["b"]


def test_query_file_filter_uses_all_evidence():
    item = finding("a", path="a.py")
    item.evidence.append(Evidence(SourceSpan("nested/CONFIG.py", 3, 3), "****"))
    page = SecretQueryRepository.page((item,), SecretQuery(file_path="config"))
    assert page.total == 1


def test_query_sort_has_identifier_tiebreaker_and_no_mutation():
    rows = (finding("b"), finding("a"))
    page = SecretQueryRepository.page(rows, SecretQuery())
    assert [f.id for f in page.items] == ["a", "b"]
    assert [f.id for f in rows] == ["b", "a"]


@pytest.mark.parametrize("options", [
    {"page": 0}, {"page_size": 0}, {"page_size": 101}, {"page": 1.5},
    {"severity": "high"}, {"min_confidence": -1}, {"min_confidence": float("nan")},
    {"min_confidence": float("inf")}, {"file_path": ""}, {"secret_type": " "},
])
def test_query_rejects_invalid_parameters(options):
    with pytest.raises(InvalidSecretQuery):
        SecretQuery(**options)


def test_query_legacy_type_and_unknown_fallback():
    old = finding("a")
    old.metadata = {}
    assert secret_type(old) == "api_key"
    old.rule_id = "future.rule"
    assert secret_type(old) == "unknown"
    old.metadata["secret_type"] = "future_type"
    assert secret_type(old) == "future_type"

