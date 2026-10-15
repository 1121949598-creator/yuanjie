"""Member B Final Freeze / Handoff validation.

Proves that a small frozen set of representative static facts (Skill, MCP,
Agent, cross-file, multi-agent, partial) are produced by the real member B
production path and validate against the frozen Contract 1.0
(``IntentCapabilityInput.from_mapping``).

This file does NOT call member C's scorer, persistence, or any web layer. It
only proves ``B -> Contract 1.0`` is stable and handoff-ready.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from yuanjian_agent.component_security import IntentCapabilityAdapter, SCHEMA_VERSION
from yuanjian_agent.files import iter_text_files
from yuanjian_agent.models import ScanLimits

FX = pathlib.Path(__file__).parent / "fixtures" / "component_security_v4"
HANDOFF = pathlib.Path(__file__).parent / "fixtures" / "component_security_handoff"
C_CONTRACT_PATH = pathlib.Path(r"D:\ai_anquan_xiangmu\tmp\c-handoff-readonly\src\yuanjian_agent\component_security\contract.py")

adapter = IntentCapabilityAdapter()


def _files(root: pathlib.Path):
    files, _warnings = iter_text_files(root, ScanLimits())
    return files


@pytest.fixture(scope="module")
def contract_module():
    if not C_CONTRACT_PATH.exists():
        pytest.skip("member C handoff contract not present")
    import sys

    spec = importlib.util.spec_from_file_location("c_contract_member_handoff", C_CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- Final handoff payload files ------------------------------------------------


HANDOFF_FILES = [
    HANDOFF / "skill.json",
    HANDOFF / "mcp.json",
    HANDOFF / "agent_single.json",
    HANDOFF / "agent_cross_file.json",
    HANDOFF / "agent_multi.json",
    HANDOFF / "partial.json",
]


@pytest.mark.parametrize("path", HANDOFF_FILES, ids=lambda p: p.stem)
def test_handoff_payload_validates_through_contract(path, contract_module):
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    assert items, f"expected at least one payload in {path.name}"
    for payload in items:
        source = contract_module.IntentCapabilityInput.from_mapping(payload)
        assert source.payload["schema_version"] == SCHEMA_VERSION
        assert source.payload["component"]["component_type"] in {
            "skill", "mcp_server", "agent", "project",
        }
        assert source.payload["parser"]["status"] in {
            "success", "partial", "unavailable", "failed",
        }


# --- Evidence integrity across every handoff payload ---------------------------


@pytest.mark.parametrize("path", HANDOFF_FILES, ids=lambda p: p.stem)
def test_handoff_evidence_no_dangling_refs(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    for payload in items:
        known = {e["evidence_id"] for e in payload["evidence"]}
        for cap in payload["capabilities"]:
            assert set(cap["evidence_refs"]) <= known
        for boundary in payload["boundaries"]:
            assert set(boundary["evidence_refs"]) <= known


# --- Multi-agent isolation (final check) ---------------------------------------


def test_final_multi_agent_isolation_via_production_path():
    payloads = adapter.build_agents(
        scan_id="final-multi", scene="release_precheck",
        files=_files(FX / "fixture_b_crossfile_isolated"),
    )
    by_name = {p["component"]["name"]: {c["capability"] for c in p["capabilities"]} for p in payloads}
    assert by_name["reader"] == {"file_read"}
    assert by_name["admin"] == {"shell_execute"}
    assert "shell_execute" not in by_name["reader"]
    assert "file_read" not in by_name["admin"]


# --- Stable IDs / determinism --------------------------------------------------


def test_final_stable_ids_repeat():
    files = _files(FX / "fixture_project")
    p1 = adapter.build_agents(scan_id="det", scene="release_precheck", files=files)
    p2 = adapter.build_agents(scan_id="det", scene="release_precheck", files=files)
    assert p1 == p2


def test_final_file_order_invariance():
    files = _files(FX / "fixture_project")
    p1 = adapter.build_agents(scan_id="ord", scene="release_precheck", files=files)
    p2 = adapter.build_agents(scan_id="ord", scene="release_precheck", files=list(reversed(files)))
    by_id = {p["component"]["component_id"]: p for p in p1}
    for p in p2:
        assert by_id[p["component"]["component_id"]] == p


# --- Static safety: malicious fixture never executes ----------------------------


def test_final_malicious_module_never_executes():
    # evil_tool.py raises RuntimeError at import; resolving must not trigger it.
    payloads = adapter.build_agents(
        scan_id="mal", scene="release_precheck",
        files=_files(FX / "fixture_k_malicious"),
    )
    assert payloads
    blob = repr(payloads)
    assert "THIS MODULE MUST NEVER EXECUTE" not in blob


def test_final_target_modules_not_imported():
    import sys as _sys

    for name in ("evil_tool", "tools", "agents"):
        _sys.modules.pop(name, None)
    adapter.build_agents(
        scan_id="safe", scene="release_precheck",
        files=_files(FX / "fixture_k_malicious"),
    )
    for name in ("evil_tool",):
        assert name not in _sys.modules


# --- Partial semantics: good static facts preserved -----------------------------


def test_final_partial_preserves_good_static_facts():
    payloads = adapter.build_agents(
        scan_id="part", scene="release_precheck",
        files=_files(FX / "fixture_m_mixed"),
    )
    assert len(payloads) == 1
    # mixed fixture keeps the statically-bound file_read while dynamic caps never guessed
    names = {c["capability"] for c in payloads[0]["capabilities"]}
    assert names == {"file_read"}
    assert payloads[0]["parser"]["status"] == "partial"
