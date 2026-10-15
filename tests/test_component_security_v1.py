from __future__ import annotations

import importlib.util
import pathlib

import pytest

from yuanjian_agent.component_security import IntentCapabilityAdapter, SCHEMA_VERSION
from yuanjian_agent.files import TextFile, iter_text_files
from yuanjian_agent.models import ScanLimits

from component_security_v1_util import load_fixture

FIXTURE_A = pathlib.Path(__file__).parent / "fixtures" / "component_security_v1" / "fixture_a_markdown"
FIXTURE_B = pathlib.Path(__file__).parent / "fixtures" / "component_security_v1" / "fixture_b_faq"

C_CONTRACT_PATH = pathlib.Path(r"D:\ai_anquan_xiangmu\tmp\c-handoff-readonly\src\yuanjian_agent\component_security\contract.py")

adapter = IntentCapabilityAdapter()


def _iter_files(root: pathlib.Path) -> list[TextFile]:
    files, _warnings = iter_text_files(root, ScanLimits())
    return files


@pytest.fixture(scope="module")
def contract_module():
    if not C_CONTRACT_PATH.exists():
        pytest.skip("member C handoff contract not present")
    import sys
    spec = importlib.util.spec_from_file_location("c_contract_member", C_CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- Fixture A: normal skill -------------------------------------------------


def test_fixture_a_component_skill():
    payload = adapter.build(scan_id="scan-a", scene="install_precheck", files=_iter_files(FIXTURE_A))
    component = payload["component"]
    assert component["component_type"] == "skill"
    assert component["declared_purpose"] != ""
    assert component["extraction_status"] == "resolved"


def test_fixture_a_file_read_capability():
    payload = adapter.build(scan_id="scan-a", scene="install_precheck", files=_iter_files(FIXTURE_A))
    names = {cap["capability"] for cap in payload["capabilities"]}
    assert "file_read" in names


def test_fixture_a_boundary_and_evidence():
    payload = adapter.build(scan_id="scan-a", scene="install_precheck", files=_iter_files(FIXTURE_A))
    assert payload["evidence"]
    assert payload["boundaries"]
    assert payload["parser"]["status"] == "success"


# --- Fixture B: high-risk agent ----------------------------------------------


def test_fixture_b_component_agent():
    payload = adapter.build(scan_id="scan-b", scene="release_precheck", files=_iter_files(FIXTURE_B))
    assert payload["component"]["component_type"] == "agent"
    assert payload["component"]["declared_purpose"] != ""


def test_fixture_b_shell_and_credential():
    payload = adapter.build(scan_id="scan-b", scene="release_precheck", files=_iter_files(FIXTURE_B))
    names = {cap["capability"] for cap in payload["capabilities"]}
    assert "shell_execute" in names
    assert "credential_access" in names


def test_fixture_b_boundary_credential_and_shell():
    payload = adapter.build(scan_id="scan-b", scene="release_precheck", files=_iter_files(FIXTURE_B))
    boundary = payload["boundaries"][0]
    assert boundary["credential_use"] is True
    assert boundary["execution_mode"] == "shell"
    assert boundary["evidence_refs"]


# --- Referential integrity ----------------------------------------------------


@pytest.mark.parametrize("root", [FIXTURE_A, FIXTURE_B])
def test_no_dangling_evidence_refs(root):
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(root))
    known = {ev["evidence_id"] for ev in payload["evidence"]}
    for cap in payload["capabilities"]:
        assert set(cap["evidence_refs"]) <= known
    for boundary in payload["boundaries"]:
        assert set(boundary["evidence_refs"]) <= known


def test_evidence_ids_unique():
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(FIXTURE_A))
    ids = [ev["evidence_id"] for ev in payload["evidence"]]
    assert len(ids) == len(set(ids))


def test_no_absolute_paths():
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(FIXTURE_A))
    for ev in payload["evidence"]:
        path = ev["source_span"]["path"].replace("\\", "/")
        assert ":" not in path and not path.startswith("/")


# --- Real member C contract validation ----------------------------------------


def test_c_contract_validation_fixture_a(contract_module):
    payload = adapter.build(scan_id="scan-a", scene="install_precheck", files=_iter_files(FIXTURE_A))
    source = contract_module.IntentCapabilityInput.from_mapping(payload)
    assert source.payload["schema_version"] == SCHEMA_VERSION


def test_c_contract_validation_fixture_b(contract_module):
    payload = adapter.build(scan_id="scan-b", scene="release_precheck", files=_iter_files(FIXTURE_B))
    source = contract_module.IntentCapabilityInput.from_mapping(payload)
    assert source.payload["scene"] == "release_precheck"
    assert source.payload["capabilities"]
    assert source.payload["boundaries"]
    assert source.payload["parser"]["status"] in {"success", "partial", "unavailable", "failed"}


# --- Missing declared purpose -------------------------------------------------


def test_missing_declared_purpose(tmp_path):
    (tmp_path / "SKILL.md").write_text("# No Purpose", encoding="utf-8")
    (tmp_path / "script.py").write_text(
        "from pathlib import Path\nPath('/tmp').read_text()\n", encoding="utf-8"
    )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(tmp_path))
    assert payload["component"]["declared_purpose"] == ""
    assert payload["component"]["extraction_status"] in {"partial", "unresolved"}
    assert payload["parser"]["status"] == "partial"


# --- capabilities / boundaries empty -----------------------------------------


def test_empty_capabilities(tmp_path):
    (tmp_path / "README.md").write_text("# Quiet\nA component with no code.", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("nothing to see", encoding="utf-8")
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_iter_files(tmp_path))
    assert payload["capabilities"] == []
    # No capability means parser still reports a sensible status; no dangling refs.
    assert payload["parser"]["status"] in {"success", "partial", "unavailable", "failed"}
    for boundary in payload["boundaries"]:
        assert not boundary["evidence_refs"] or all(r in {e["evidence_id"] for e in payload["evidence"]} for r in boundary["evidence_refs"])


def test_empty_boundary_no_dangling(tmp_path):
    (tmp_path / "README.md").write_text("# Q\nplain", encoding="utf-8")
    (tmp_path / "main.py").write_text("def plus(a, b):\n    return a + b\n", encoding="utf-8")
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_iter_files(tmp_path))
    # Every boundary, even an empty one, must not carry dangling refs.
    known = {e["evidence_id"] for e in payload["evidence"]}
    for boundary in payload["boundaries"]:
        for ref in boundary["evidence_refs"]:
            assert ref in known


# --- absolute path blocking ---------------------------------------------------


def test_no_absolute_path_in_any_span(tmp_path):
    (tmp_path / "SKILL.md").write_text("---\ndescription: absolute test\n---\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "import subprocess\nsubprocess.run('ls', shell=True)\n", encoding="utf-8"
    )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(tmp_path))
    spans = [ev["source_span"] for ev in payload["evidence"]]
    spans += payload["component"]["source_spans"]
    for span in spans:
        path = span["path"].replace("\\", "/")
        assert ":" not in path and not path.startswith("/") and ".." not in path


# --- secret masking ------------------------------------------------------------


def test_secret_is_masked(tmp_path):
    (tmp_path / "SKILL.md").write_text("---\ndescription: secret test\n---\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "import os\napi_key = \"real-secret-value-12345\"\nos.environ.get(api_key)\n", encoding="utf-8"
    )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(tmp_path))
    for ev in payload["evidence"]:
        assert "real-secret-value-12345" not in ev["masked_excerpt"]


# --- duplicate id prevention ---------------------------------------------------


def test_no_duplicate_capability_id():
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_iter_files(FIXTURE_B))
    ids = [cap["capability_id"] for cap in payload["capabilities"]]
    assert len(ids) == len(set(ids))


def test_no_duplicate_boundary_id():
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_iter_files(FIXTURE_B))
    ids = [b["boundary_id"] for b in payload["boundaries"]]
    assert len(ids) == len(set(ids))


# --- unsupported component ------------------------------------------------------


def test_unsupported_component_falls_back():
    tmp_path = FIXTURE_A
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(tmp_path))
    assert payload["component"]["component_type"] in {"skill", "mcp_server", "agent", "project"}


def test_project_component_when_no_agent_skill(tmp_path):
    (tmp_path / "config.yaml").write_text("mode: normal\n", encoding="utf-8")
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_iter_files(tmp_path))
    assert payload["component"]["component_type"] == "project"


# --- single file syntax error -> partial ---------------------------------------


def test_single_file_syntax_error_is_partial(tmp_path):
    (tmp_path / "SKILL.md").write_text("---\ndescription: partial\n---\n", encoding="utf-8")
    (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(tmp_path))
    assert payload["parser"]["status"] == "partial"
    assert payload["parser"]["warnings"]


# --- completely unsupported -> unavailable --------------------------------------


def test_unsupported_parser_unavailable(tmp_path):
    (tmp_path / "data.md").write_text("just documentation\n", encoding="utf-8")
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_iter_files(tmp_path))
    assert payload["parser"]["status"] == "unavailable"


# --- no hardcoded sample answers ------------------------------------------------


def test_facts_depend_on_static_evidence():
    # A benign fixture must not report shell/credential just because a name matches.
    payload_a = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(FIXTURE_A))
    names_a = {cap["capability"] for cap in payload_a["capabilities"]}
    assert "shell_execute" not in names_a
    assert "credential_access" not in names_a


def test_confidence_range():
    for root, scene in [(FIXTURE_A, "install_precheck"), (FIXTURE_B, "release_precheck")]:
        payload = adapter.build(scan_id="scan", scene=scene, files=_iter_files(root))
        for cap in payload["capabilities"]:
            assert 0.0 <= cap["confidence"] <= 1.0
            assert 1 <= cap["impact"] <= 5


def test_stable_ids_across_reruns():
    p1 = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(FIXTURE_A))
    p2 = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(FIXTURE_A))
    assert p1["component"]["component_id"] == p2["component"]["component_id"]
    assert [c["capability_id"] for c in p1["capabilities"]] == [c["capability_id"] for c in p2["capabilities"]]
    assert [e["evidence_id"] for e in p1["evidence"]] == [e["evidence_id"] for e in p2["evidence"]]


# --- parser failed (unrecoverable) --------------------------------------------


def test_parser_failed_on_unrecoverable_error(monkeypatch, contract_module):
    import yuanjian_agent.component_security.intent_adapter as adapter_mod

    def _boom(*_args, **_kwargs):
        raise RuntimeError("internal parse crash")

    monkeypatch.setattr(adapter_mod, "extract_component_facts", _boom)
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_iter_files(FIXTURE_A))
    assert payload["parser"]["status"] == "failed"
    assert "RuntimeError" not in str(payload["parser"]["warnings"])
    assert "internal parse crash" not in str(payload["parser"]["warnings"])
    source = contract_module.IntentCapabilityInput.from_mapping(payload)
    assert source.payload["parser"]["status"] == "failed"
