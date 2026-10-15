from __future__ import annotations

import importlib.util
import pathlib

import pytest

from yuanjian_agent.component_security import (
    IntentCapabilityAdapter,
    SCHEMA_VERSION,
    AgentResolver,
    effective_agent_facts,
    resolve_agent_declarations,
)
from yuanjian_agent.files import iter_text_files
from yuanjian_agent.models import ScanLimits

FX = pathlib.Path(__file__).parent / "fixtures" / "component_security_v3"
C_CONTRACT_PATH = pathlib.Path(r"D:\ai_anquan_xiangmu\tmp\c-handoff-readonly\src\yuanjian_agent\component_security\contract.py")

adapter = IntentCapabilityAdapter()


def _files(root: pathlib.Path):
    files, _warnings = iter_text_files(root, ScanLimits())
    return files


def _agents(root: pathlib.Path):
    files = _files(root)
    return adapter.build_agents(scan_id="scan", scene="install_precheck", files=files), files


@pytest.fixture(scope="module")
def contract_module():
    if not C_CONTRACT_PATH.exists():
        pytest.skip("member C handoff contract not present")
    import sys
    spec = importlib.util.spec_from_file_location("c_contract_member_b3", C_CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- Fixture A: single Agent, multiple Tools ---------------------------------


def test_fixture_a_file_read_and_network():
    payloads, _ = _agents(FX / "fixture_a_single_multi")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert "file_read" in names
    assert "network_access" in names


# --- Fixture B: multi-Agent isolation (key acceptance point) -----------------


def test_fixture_b_two_agents():
    payloads, _ = _agents(FX / "fixture_b_multi_isolated")
    assert len(payloads) == 2


def test_fixture_b_distinct_component_ids():
    payloads, _ = _agents(FX / "fixture_b_multi_isolated")
    ids = [p["component"]["component_id"] for p in payloads]
    assert len(ids) == len(set(ids))


def test_fixture_b_agent_component_type():
    payloads, _ = _agents(FX / "fixture_b_multi_isolated")
    assert all(p["component"]["component_type"] == "agent" for p in payloads)


def test_fixture_b_agent_isolation_no_cross_contamination():
    payloads, _ = _agents(FX / "fixture_b_multi_isolated")
    by_name = {p["component"]["name"]: {c["capability"] for c in p["capabilities"]} for p in payloads}
    assert by_name["reader"] == {"file_read"}
    assert by_name["admin"] == {"shell_execute"}
    assert "shell_execute" not in by_name["reader"]
    assert "file_read" not in by_name["admin"]


def test_fixture_b_capability_attribution():
    payloads, files = _agents(FX / "fixture_b_multi_isolated")
    by_name = {p["component"]["name"]: {c["capability"] for c in p["capabilities"]} for p in payloads}
    assert by_name["reader"] == {"file_read"}
    assert by_name["admin"] == {"shell_execute"}


def test_fixture_b_binding_evidence_chain():
    # An Agent capability must be traceable through a Tool implementation
    # evidence AND the Agent->Tool binding evidence (no bare "agent has cap").
    payloads, _ = _agents(FX / "fixture_b_multi_isolated")
    by_name = {p["component"]["name"]: p for p in payloads}
    reader = by_name["reader"]
    known = {e["evidence_id"]: e for e in reader["evidence"]}
    cap = reader["capabilities"][0]
    parsers = {known[r]["details"].get("parser") for r in cap["evidence_refs"] if r in known}
    assert "python-tool-static" in parsers
    assert "python-agent-static" in parsers
    # The tool implementation evidence symbol reflects the actual dangerous call.
    symbols = {known[r]["details"].get("symbol") for r in cap["evidence_refs"] if r in known}
    assert "python-tool-static" in parsers
    assert any(sym for sym in symbols if sym in {"open", "Path.read_text", "subprocess.run", "os.system"})


# --- Fixture C: decorator Tool ----------------------------------------------


def test_fixture_c_decorator_tool():
    payloads, _ = _agents(FX / "fixture_c_decorator")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert "file_read" in names


# --- Fixture D: Tool wrapper -------------------------------------------------


def test_fixture_d_wrapper_tool():
    payloads, _ = _agents(FX / "fixture_d_wrapper")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert "file_read" in names


# --- Fixture E: direct function ---------------------------------------------


def test_fixture_e_direct_function():
    payloads, _ = _agents(FX / "fixture_e_direct_function")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert "file_read" in names


# --- Fixture F: alias --------------------------------------------------------


def test_fixture_f_alias():
    payloads, _ = _agents(FX / "fixture_f_alias")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert "file_read" in names


# --- Fixture G: dynamic unresolved -> partial --------------------------------


def test_fixture_g_dynamic_partial():
    payloads, files = _agents(FX / "fixture_g_dynamic")
    assert len(payloads) == 1
    assert payloads[0]["parser"]["status"] == "partial"
    # dynamic collection must not be guessed into capabilities
    assert payloads[0]["capabilities"] == []


# --- Fixture H: import alias ------------------------------------------------


def test_fixture_h_import_alias():
    payloads, _ = _agents(FX / "fixture_h_import_alias")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert "file_read" in names


# --- Fixture I: malicious never executes ------------------------------------


def test_fixture_i_malicious_capability_and_never_executes():
    payloads, files = _agents(FX / "fixture_i_malicious")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert "shell_execute" in names
    blob = repr(payloads[0])
    assert "THIS MUST NEVER EXECUTE" not in blob
    # The raw shell payload string must never be emitted intact; only the
    # short static call symbol may appearcarry evidence.
    assert "THIS MUST NEVER RUN" not in blob


# --- Negative fixtures -------------------------------------------------------


def test_negative_local_agent_class_not_detected():
    payloads, _ = _agents(FX / "fixture_neg_local_agent")
    assert payloads == []


def test_negative_string_tools_not_detected():
    payloads, _ = _agents(FX / "fixture_neg_string_tools")
    assert payloads == []


# --- Security / registration -------------------------------------------------


def test_security_registration_resolves():
    payloads, _ = _agents(FX / "fixture_security_registration")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert "credential_access" in names


# --- Resolver-level declarations --------------------------------------------


def test_resolver_counts_multi_agent():
    files = _files(FX / "fixture_b_multi_isolated")
    decls = resolve_agent_declarations(files)
    assert {d.symbol for d in decls} == {"reader", "admin"}


def test_resolver_bindings_kinds():
    files = _files(FX / "fixture_b_multi_isolated")
    decls = resolve_agent_declarations(files)
    reader = next(d for d in decls if d.symbol == "reader")
    assert all(b.binding_kind == "constructor_argument" for b in reader.bindings)
    assert reader.bindings[0].tool_symbol in {"read_tool"}


# --- Contract validation for every Batch 3 payload --------------------------


@pytest.mark.parametrize(
    "root",
    [
        "fixture_a_single_multi",
        "fixture_b_multi_isolated",
        "fixture_c_decorator",
        "fixture_d_wrapper",
        "fixture_e_direct_function",
        "fixture_f_alias",
        "fixture_g_dynamic",
        "fixture_h_import_alias",
        "fixture_i_malicious",
        "fixture_security_registration",
    ],
)
def test_contract_validation_all_batch3(root, contract_module):
    payloads, _ = _agents(FX / root)
    assert payloads, f"expected at least one agent payload for {root}"
    for payload in payloads:
        source = contract_module.IntentCapabilityInput.from_mapping(payload)
        assert source.payload["schema_version"] == SCHEMA_VERSION
        assert source.payload["component"]["component_type"] == "agent"
        assert source.payload["parser"]["status"] in {"success", "partial", "unavailable", "failed"}


# --- Cross-reference integrity: no dangling refs, unique ids ----------------


@pytest.mark.parametrize(
    "root",
    [
        "fixture_a_single_multi",
        "fixture_b_multi_isolated",
        "fixture_c_decorator",
        "fixture_d_wrapper",
        "fixture_e_direct_function",
        "fixture_f_alias",
        "fixture_g_dynamic",
        "fixture_h_import_alias",
        "fixture_i_malicious",
    ],
)
def test_no_dangling_refs_batch3(root):
    payloads, _ = _agents(FX / root)
    for payload in payloads:
        known = {e["evidence_id"] for e in payload["evidence"]}
        for cap in payload["capabilities"]:
            assert set(cap["evidence_refs"]) <= known
        for boundary in payload["boundaries"]:
            assert set(boundary["evidence_refs"]) <= known


@pytest.mark.parametrize("root", ["fixture_a_single_multi", "fixture_b_multi_isolated", "fixture_i_malicious"])
def test_ids_unique_batch3(root):
    payloads, _ = _agents(FX / root)
    for payload in payloads:
        for kind, plural in (("capability", "capabilities"), ("boundary", "boundaries"), ("evidence", "evidence")):
            ids = [row[f"{kind}_id"] for row in payload[plural]]
            assert len(ids) == len(set(ids)), kind


# --- Relative path + security -----------------------------------------------


def test_no_absolute_paths_batch3():
    payloads, _ = _agents(FX / "fixture_b_multi_isolated")
    for payload in payloads:
        spans = [e["source_span"] for e in payload["evidence"]]
        spans += payload["component"]["source_spans"]
        for span in spans:
            path = span["path"].replace("\\", "/")
            assert ":" not in path and not path.startswith("/") and ".." not in path


def test_evidence_span_columns_present_batch3():
    payloads, _ = _agents(FX / "fixture_b_multi_isolated")
    for payload in payloads:
        for ev in payload["evidence"]:
            span = ev["source_span"]
            for key in ("start_line", "end_line", "start_column", "end_column"):
                assert isinstance(span[key], int)
            assert span["start_line"] >= 1


# --- Determinism -------------------------------------------------------------


def test_deterministic_batch3():
    p1, files = _agents(FX / "fixture_b_multi_isolated")
    p2, _ = _agents(FX / "fixture_b_multi_isolated")
    assert p1 == p2
    for a, b in zip(p1, p2):
        assert [c["capability_id"] for c in a["capabilities"]] == [c["capability_id"] for c in b["capabilities"]]
        assert [e["evidence_id"] for e in a["evidence"]] == [e["evidence_id"] for e in b["evidence"]]


# --- Registration degrade gracefully ----------------------------------------


def test_registration_with_dynamic_arg_no_crash(tmp_path):
    (tmp_path / "agent.py").write_text(
        "from langchain.agents import create_agent\n"
        "agent = create_agent('m', tools=[read_tool])\n"
        "agent.tools.extend(load_plugins())\n",
        encoding="utf-8",
    )
    files = _files(tmp_path)
    payloads = adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    # unresolved dynamic mutation must degrade to partial but not crash
    assert payloads[0]["parser"]["status"] in {"success", "partial"}


# --- Fixture K: CrewAI BaseTool + multi-Agent isolation ----------------------


def test_fixture_k_crewai_isolated():
    payloads, _ = _agents(FX / "fixture_k_crewai_isolated")
    assert len(payloads) == 2
    by_name = {p["component"]["name"]: {c["capability"] for c in p["capabilities"]} for p in payloads}
    assert by_name["reader"] == {"file_read"}
    assert by_name["admin"] == {"shell_execute"}
    assert "shell_execute" not in by_name["reader"]
    assert "file_read" not in by_name["admin"]


# --- Empty / no agent --------------------------------------------------------


def test_syntax_error_single_file_no_crash(tmp_path):
    (tmp_path / "agent.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    files = _files(tmp_path)
    # A broken Python file must not crash or raise during Agent resolution.
    assert adapter.build_agents(scan_id="scan", scene="install_precheck", files=files) == []


def test_no_agents_empty_payloads(tmp_path):
    (tmp_path / "README.md").write_text("# nothing\n", encoding="utf-8")
    files = _files(tmp_path)
    assert adapter.build_agents(scan_id="scan", scene="install_precheck", files=files) == []
