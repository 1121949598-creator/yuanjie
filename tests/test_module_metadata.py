from copy import deepcopy
import json
from pathlib import Path

import pytest

from yuanjian_agent.config import Settings
from yuanjian_agent.core import metadata
from yuanjian_agent.core.registry import ScannerRegistry
from yuanjian_agent.core.scanner import ScannerResult, SecurityModule
from yuanjian_agent.engine import ScanEngine
from yuanjian_agent.models import Evidence, Finding, FindingCategory, Severity, SourceSpan


class IdentityRedactor:
    def redact_text(self, text):
        return text


def cycle():
    value = {}
    value["self"] = value
    return value


def deep_tree():
    value = {}
    for _ in range(18):
        value = {"child": value}
    return value


@pytest.mark.parametrize("value", [
    {"value": object()}, {"value": float("nan")}, {"value": float("inf")},
    {"value": 2 ** 100}, {1: "bad"}, {"raw_json": {}}, {"stdout": "hidden"},
    {"environment": "hidden"}, {"value": "x" * 4097}, {"value": [0] * 20_001},
    cycle(), deep_tree(), {"value": Path("relative")}, {"value": {1, 2}},
])
def test_unsafe_metadata_is_rejected_without_stringification(value):
    with pytest.raises(metadata.InvalidModuleMetadata, match="diagnostic details suppressed"):
        metadata.safe_module_metadata(value, IdentityRedactor(), Path("C:/target"))


@pytest.mark.parametrize("limit,value", [("MAX_METADATA_NODES", {"list": [1, 2, 3, 4]}),
                                         ("MAX_METADATA_BYTES", {"value": "abcdefgh"})])
def test_total_budgets(limit, value, monkeypatch):
    monkeypatch.setattr(metadata, limit, 3)
    with pytest.raises(metadata.InvalidModuleMetadata):
        metadata.safe_module_metadata(value, IdentityRedactor(), Path("C:/target"))


def test_metadata_copy_withholds_paths_and_urls():
    payload = {"value": "C:/private/target/path", "url": "https://user:password@host", "safe": [1, True, None]}
    original = deepcopy(payload)
    output = metadata.safe_module_metadata(payload, IdentityRedactor(), Path("C:/private/target"))
    assert payload == original and output is not payload
    assert "C:/private/target" not in json.dumps(output)
    assert "password" not in json.dumps(output)
    assert output["safe"] == [1, True, None]


def test_scanner_metadata_defaults_are_independent():
    one, two = ScannerResult(), ScannerResult()
    one.metadata["extra"] = 1
    assert two.metadata == {}


@pytest.mark.parametrize("mode", ["empty", "valid", "cycle", "invalid_with_finding"])
def test_engine_metadata_compatibility_failure_isolation_and_redaction(mode, tmp_path):
    raw = "Synthetic_Metadata_Credential_9182abcQ"
    project = tmp_path / "project"
    project.mkdir()
    (project / "input.py").write_text(f'password="{raw}"\n')
    payload = {"name": raw} if mode == "valid" else cycle() if mode == "cycle" else {}
    findings = []
    if mode == "invalid_with_finding":
        payload = {"value": object()}
        findings = [Finding("fixture", "sig", FindingCategory.LICENSE, "fixture", Severity.MEDIUM, 0.8,
                            "Fixture", [Evidence(SourceSpan("input.py", 1, 1), "safe")], [], [])]

    class License:
        name = SecurityModule.LICENSE
        def scan(self, context):
            return ScannerResult(metadata=payload, findings=findings)

    class Agent:
        name = SecurityModule.AGENT_SECURITY
        def scan(self, context):
            return ScannerResult()

    registry = ScannerRegistry()
    registry.register(License())
    registry.register(Agent())
    engine = ScanEngine(Settings(data_dir=tmp_path / "state"), registry=registry)
    result = engine.scan(project)
    assert result.metadata["scanners"]["agent_security"]["status"] == "success"
    expected = {"empty": "success", "valid": "success", "cycle": "failed", "invalid_with_finding": "partial"}
    assert result.metadata["scanners"]["license"]["status"] == expected[mode]
    if mode == "valid":
        assert raw not in json.dumps(result.metadata) and "license" in result.metadata["module_data"]
        assert engine.store.get(result.id).metadata == result.metadata
    else:
        assert "module_data" not in result.metadata
    if mode == "invalid_with_finding":
        assert [f.id for f in result.findings] == ["fixture"]
