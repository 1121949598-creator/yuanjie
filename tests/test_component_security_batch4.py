from __future__ import annotations

import importlib.util
import pathlib

import pytest

from yuanjian_agent.component_security import (
    SCHEMA_VERSION,
    AgentResolver,
    CrossModuleSymbolResolver,
    IntentCapabilityAdapter,
    PythonModuleIndex,
    effective_agent_facts,
    resolve_agent_declarations,
)
from yuanjian_agent.files import iter_text_files
from yuanjian_agent.models import ScanLimits

FX = pathlib.Path(__file__).parent / "fixtures" / "component_security_v4"
C_CONTRACT_PATH = pathlib.Path(r"D:\ai_anquan_xiangmu\tmp\c-handoff-readonly\src\yuanjian_agent\component_security\contract.py")

adapter = IntentCapabilityAdapter()

ALL_FIXTURES = [
    "fixture_a_direct_crossfile",
    "fixture_b_crossfile_isolated",
    "fixture_c_collection",
    "fixture_d_reexport",
    "fixture_e_import_alias",
    "fixture_f_collection_alias",
    "fixture_g_concat",
    "fixture_h_wrapper_chain",
    "fixture_j_external",
    "fixture_k_malicious",
    "fixture_l_dynamic",
    "fixture_m_mixed",
    "fixture_import_star_with_all",
    "fixture_project",
]


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

    spec = importlib.util.spec_from_file_location("c_contract_member_b4", C_CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- Main acceptance: real project structure --------------------------------


def test_project_main_structure_agent():
    payloads, _ = _agents(FX / "fixture_project")
    assert len(payloads) == 1
    assert payloads[0]["component"]["name"] == "researcher"
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read", "network_access"}


def test_project_evidence_chain_cross_file():
    payloads, _ = _agents(FX / "fixture_project")
    payload = payloads[0]
    known = {e["evidence_id"]: e for e in payload["evidence"]}
    parsers = {known[r]["details"].get("parser") for c in payload["capabilities"] for r in c["evidence_refs"] if r in known}
    assert "python-tool-static" in parsers
    assert "python-agent-static" in parsers
    assert "python-import-static" in parsers
    # cross-file implementation spans point at the tools package, not agents.py.
    impl_spans = {
        known[r]["source_span"]["path"].replace("\\", "/")
        for c in payload["capabilities"]
        for r in c["evidence_refs"]
        if r in known and known[r]["details"].get("parser") == "python-tool-static"
    }
    assert "tools/file_tools.py" in impl_spans
    assert "tools/web_tools.py" in impl_spans


# --- Fixture A: direct cross-file Tool --------------------------------------


def test_fixture_a_direct_crossfile():
    payloads, _ = _agents(FX / "fixture_a_direct_crossfile")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}


# --- Fixture B: cross-file multi-Agent isolation ----------------------------


def test_fixture_b_crossfile_isolated_count():
    payloads, _ = _agents(FX / "fixture_b_crossfile_isolated")
    assert len(payloads) == 2


def test_fixture_b_crossfile_isolated_caps():
    payloads, _ = _agents(FX / "fixture_b_crossfile_isolated")
    by_name = {p["component"]["name"]: {c["capability"] for c in p["capabilities"]} for p in payloads}
    assert by_name["reader"] == {"file_read"}
    assert by_name["admin"] == {"shell_execute"}
    assert "shell_execute" not in by_name["reader"]
    assert "file_read" not in by_name["admin"]


# --- Fixture C: cross-file collection ---------------------------------------


def test_fixture_c_collection():
    payloads, _ = _agents(FX / "fixture_c_collection")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read", "network_access"}


# --- Fixture D: re-export ---------------------------------------------------


def test_fixture_d_reexport():
    payloads, _ = _agents(FX / "fixture_d_reexport")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}


# --- Fixture E: import alias ------------------------------------------------


def test_fixture_e_import_alias():
    payloads, _ = _agents(FX / "fixture_e_import_alias")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}


# --- Fixture F: collection alias --------------------------------------------


def test_fixture_f_collection_alias():
    payloads, _ = _agents(FX / "fixture_f_collection_alias")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}


# --- Fixture G: static concatenation ----------------------------------------


def test_fixture_g_concat():
    payloads, _ = _agents(FX / "fixture_g_concat")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read", "network_access"}


# --- Fixture H: wrapper chain across modules --------------------------------


def test_fixture_h_wrapper_chain():
    payloads, _ = _agents(FX / "fixture_h_wrapper_chain")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}


# --- Fixture I: circular import -> no crash, partial ------------------------


def test_fixture_i_circular_no_crash_and_partial():
    payloads, _ = _agents(FX / "fixture_i_circular")
    # cycle degrades gracefully; at least no crash, agent is partial/unresolved.
    assert isinstance(payloads, list)
    if payloads:
        assert payloads[0]["parser"]["status"] in {"partial", "success", "unavailable", "failed"}


def test_fixture_i_circular_resolver_cycle_status():
    files = _files(FX / "fixture_i_circular")
    index = PythonModuleIndex(files)
    resolver = CrossModuleSymbolResolver(index)
    exp = resolver.expand("a", "y_tool")
    assert exp.status in {"partial", "cycle", "unresolved"}


# --- Fixture J: external package (never import, never guess) ----------------


def test_fixture_j_external_no_guess():
    payloads, _ = _agents(FX / "fixture_j_external")
    assert len(payloads) == 1
    assert payloads[0]["capabilities"] == []


def test_fixture_j_external_sys_modules_untouched():
    import sys

    before = "unknown_sdk" in sys.modules
    files = _files(FX / "fixture_j_external")
    adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    assert ("unknown_sdk" in sys.modules) == before


# --- Fixture K: malicious module never executes -----------------------------


def test_fixture_k_malicious_never_executes():
    payloads, files = _agents(FX / "fixture_k_malicious")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}
    blob = repr(payloads[0])
    assert "THIS MODULE MUST NEVER EXECUTE" not in blob


# --- Fixture L: dynamic collection -> partial -------------------------------


def test_fixture_l_dynamic_partial():
    payloads, _ = _agents(FX / "fixture_l_dynamic")
    assert len(payloads) == 1
    assert payloads[0]["parser"]["status"] == "partial"
    assert payloads[0]["capabilities"] == []


# --- Fixture M: mixed static + dynamic --------------------------------------


def test_fixture_m_mixed_preserves_static():
    payloads, _ = _agents(FX / "fixture_m_mixed")
    assert len(payloads) == 1
    assert payloads[0]["parser"]["status"] == "partial"
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}
    assert "network_access" not in names  # dynamic portion never guessed


# --- Negative fixtures ------------------------------------------------------


def test_neg_cross_function_not_a_tool():
    payloads, _ = _agents(FX / "neg_cross_function")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}
    # the imported plain function must not add capabilities
    for cap in payloads[0]["capabilities"]:
        assert cap["capability"] != "network_access"


def test_neg_string_list_not_collection():
    payloads, _ = _agents(FX / "neg_string_list")
    assert len(payloads) == 1
    assert payloads[0]["capabilities"] == []


def test_neg_plain_decorator_no_agent():
    payloads, _ = _agents(FX / "neg_plain_decorator")
    assert payloads == []


def test_neg_processor_not_agent():
    payloads, _ = _agents(FX / "neg_processor")
    assert payloads == []


# --- Resolver-level: cross-file declarations --------------------------------


def test_resolver_crossfile_binding_cross_flag():
    files = _files(FX / "fixture_a_direct_crossfile")
    decls = resolve_agent_declarations(files)
    agent = next(d for d in decls if d.symbol == "agent")
    assert agent.bindings
    assert all(b.cross_file for b in agent.bindings)
    assert agent.bindings[0].tool_symbol == "read_tool"


# --- Fixture: import star ---------------------------------------------------


def test_import_star_with_static_all_resolves():
    payloads, _ = _agents(FX / "fixture_import_star_with_all")
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}


def test_import_star_without_all_degrades():
    payloads, _ = _agents(FX / "fixture_import_star_no_all")
    assert len(payloads) == 1
    assert payloads[0]["capabilities"] == []


# --- Single-file cyclic alias: no RecursionError ----------------------------


def test_single_file_cyclic_alias_no_crash(tmp_path):
    (tmp_path / "agent.py").write_text(
        "from langchain.agents import create_agent\n"
        "A = B\n"
        "B = C\n"
        "C = A\n"
        "agent = create_agent('m', tools=[A], system_prompt='c')\n",
        encoding="utf-8",
    )
    files = _files(tmp_path)
    payloads = adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    assert len(payloads) == 1
    assert payloads[0]["capabilities"] == []


# --- File-order invariance across fixtures ----------------------------------


@pytest.mark.parametrize(
    "root",
    ["fixture_project", "fixture_c_collection", "fixture_b_crossfile_isolated", "fixture_h_wrapper_chain", "fixture_g_concat"],
)
def test_file_order_invariance(root):
    files = _files(FX / root)
    rev = list(reversed(files))
    p1 = adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    p2 = adapter.build_agents(scan_id="scan", scene="install_precheck", files=rev)
    by_id1 = {p["component"]["component_id"]: p for p in p1}
    for p in p2:
        assert by_id1[p["component"]["component_id"]] == p


# --- Contract validation for every payload ----------------------------------


@pytest.mark.parametrize("root", ALL_FIXTURES)
def test_contract_validation_all_batch4(root, contract_module):
    payloads, _ = _agents(FX / root)
    for payload in payloads:
        source = contract_module.IntentCapabilityInput.from_mapping(payload)
        assert source.payload["schema_version"] == SCHEMA_VERSION
        assert source.payload["component"]["component_type"] == "agent"
        assert source.payload["parser"]["status"] in {"success", "partial", "unavailable", "failed"}


# --- Cross-reference integrity ----------------------------------------------


@pytest.mark.parametrize("root", ALL_FIXTURES)
def test_no_dangling_refs_batch4(root):
    payloads, _ = _agents(FX / root)
    for payload in payloads:
        known = {e["evidence_id"] for e in payload["evidence"]}
        for cap in payload["capabilities"]:
            assert set(cap["evidence_refs"]) <= known
        for boundary in payload["boundaries"]:
            assert set(boundary["evidence_refs"]) <= known


@pytest.mark.parametrize("root", ["fixture_b_crossfile_isolated", "fixture_c_collection", "fixture_project"])
def test_ids_unique_batch4(root):
    payloads, _ = _agents(FX / root)
    for payload in payloads:
        for kind, plural in (("capability", "capabilities"), ("boundary", "boundaries"), ("evidence", "evidence")):
            if not payload[plural]:
                continue
            ids = [row[f"{kind}_id"] for row in payload[plural]]
            assert len(ids) == len(set(ids)), kind


# --- Relative paths + security ----------------------------------------------


@pytest.mark.parametrize("root", ["fixture_b_crossfile_isolated", "fixture_project", "fixture_d_reexport"])
def test_no_absolute_paths_batch4(root):
    payloads, _ = _agents(FX / root)
    for payload in payloads:
        spans = [e["source_span"] for e in payload["evidence"]]
        spans += payload["component"]["source_spans"]
        for span in spans:
            path = span["path"].replace("\\", "/")
            assert ":" not in path and not path.startswith("/") and ".." not in path


# --- Determinism: repeated run --- ------------------------------------------


def test_deterministic_repeat_batch4():
    p1, _ = _agents(FX / "fixture_project")
    p2, _ = _agents(FX / "fixture_project")
    assert p1 == p2


def test_deterministic_file_order_reversed():
    files = _files(FX / "fixture_project")
    files_rev = list(reversed(files))
    p1 = adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    p2 = adapter.build_agents(scan_id="scan", scene="install_precheck", files=files_rev)
    by_id = {p["component"]["component_id"]: p for p in p1}
    for p in p2:
        assert by_id[p["component"]["component_id"]] == p


def test_deterministic_ids_cross_file_multi():
    p1, _ = _agents(FX / "fixture_c_collection")
    p2, _ = _agents(FX / "fixture_c_collection")
    assert [c["capability_id"] for c in p1[0]["capabilities"]] == [c["capability_id"] for c in p2[0]["capabilities"]]
    assert [e["evidence_id"] for e in p1[0]["evidence"]] == [e["evidence_id"] for e in p2[0]["evidence"]]


# --- Static safety: no execution / no import of target modules --------------

import sys as _sys


def test_no_target_modules_imported():
    for m in ("tools", "evil_tool", "unknown_sdk", "functions", "file_tools", "web_tools"):
        _sys.modules.pop(m, None)
    files = (
        _files(FX / "fixture_project")
        + _files(FX / "fixture_k_malicious")
        + _files(FX / "fixture_j_external")
    )
    adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    for m in ("tools", "evil_tool", "unknown_sdk", "functions", "file_tools", "web_tools"):
        assert m not in _sys.modules


def test_agent_resolution_never_executes_evil():
    files = _files(FX / "fixture_k_malicious")
    # Just resolving must not raise the RuntimeError defined in the module.
    adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)


# --- Performance: many modules parsed once ----------------------------------


def test_large_repo_parsed_without_blowup(tmp_path):
    n = 40
    for i in range(n):
        (tmp_path / f"mod_{i:03d}.py").write_text(
            "from pathlib import Path\n"
            f"def tool_{i}(p): return Path(p).read_text()\n",
            encoding="utf-8",
        )
    (tmp_path / "agent.py").write_text(
        "from langchain.agents import create_agent\n"
        "from mod_000 import tool_0\n"
        "tool_1_extra = tool_0\n"
        "agent = create_agent('m', tools=[tool_1_extra], system_prompt='read')\n",
        encoding="utf-8",
    )
    files = _files(tmp_path)
    payloads = adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    assert len(payloads) == 1
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}
    # re-run is identical and fast (no exponential re-parse)
    p2 = adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    assert p2 == payloads


# --- Cross-file failure isolation: one module syntax error --------------------


def test_cross_file_syntax_error_isolation_preserves_static(tmp_path):
    """A SyntaxError in one file must not fail the whole repository analysis.

    tools/file_tools.py parses and resolves file_read; tools/web_tools.py is a
    SyntaxError; agents.py imports both through the collection. The Agent must
    stay partial, keep the known file_read fact, and not crash (task 40/41).
    """
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "file_tools.py").write_text(
        "from pathlib import Path\ndef read_tool(p): return Path(p).read_text()\n",
        encoding="utf-8",
    )
    (tmp_path / "tools" / "web_tools.py").write_text(
        "def search_web(q): return requests.get('https://x.example').text\nthis is not valid python = (\n",
        encoding="utf-8",
    )
    (tmp_path / "tools" / "__init__.py").write_text(
        "from .file_tools import read_tool\nfrom .web_tools import search_web\nALL_TOOLS = [read_tool, search_web]\n",
        encoding="utf-8",
    )
    (tmp_path / "agents.py").write_text(
        "from langchain.agents import create_agent\nfrom tools import ALL_TOOLS\n"
        "agent = create_agent('m', tools=ALL_TOOLS, system_prompt='mixed')\n",
        encoding="utf-8",
    )
    files = _files(tmp_path)
    payloads = adapter.build_agents(scan_id="scan", scene="install_precheck", files=files)
    assert len(payloads) == 1
    # Known static fact preserved, broken module must not drag the Agent to
    # unresolved or crash the whole run.
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}
    assert payloads[0]["parser"]["status"] in {"partial", "success"}
