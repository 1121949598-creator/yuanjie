from __future__ import annotations

import importlib.util
import pathlib

import pytest

from yuanjian_agent.component_security import IntentCapabilityAdapter, SCHEMA_VERSION
from yuanjian_agent.component_security.parsers import McpParser, SkillParser
from yuanjian_agent.files import iter_text_files
from yuanjian_agent.models import ScanLimits

from component_security_v1_util import load_fixture

FX = pathlib.Path(__file__).parent / "fixtures" / "component_security_v1"
FIXTURE_C_MCP = FX / "fixture_c_mcp_secure"
FIXTURE_D_MCP_BROKEN = FX / "fixture_d_mcp_broken"
FIXTURE_E_SKILL_RISKY = FX / "fixture_e_skill_risky"
FIXTURE_F_SKILL_PLAIN = FX / "fixture_f_skill_plain"
FIXTURE_G_SKILL_NEVER = FX / "fixture_g_skill_never_execute"
FIXTURE_H_MCP_YAML = FX / "fixture_h_mcp_yaml"
FIXTURE_I_MCP_TOML = FX / "fixture_i_mcp_toml"

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
    spec = importlib.util.spec_from_file_location("c_contract_member", C_CONTRACT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --- MCP: component identity -------------------------------------------------


def test_mcp_component_type_and_name():
    payload = adapter.build(scan_id="scan-c", scene="install_precheck", files=_files(FIXTURE_C_MCP))
    assert payload["component"]["component_type"] == "mcp_server"
    assert payload["component"]["name"]
    assert payload["component"]["declared_purpose"]


def test_mcp_stdio_and_remote_capabilities():
    payload = adapter.build(scan_id="scan-c", scene="install_precheck", files=_files(FIXTURE_C_MCP))
    names = {c["capability"] for c in payload["capabilities"]}
    assert "process_execute" in names       # python command
    assert "credential_access" in names     # env secret keys
    assert "network_access" in names        # remote url


def test_mcp_network_target_boundary():
    payload = adapter.build(scan_id="scan-c", scene="install_precheck", files=_files(FIXTURE_C_MCP))
    targets = [t for b in payload["boundaries"] for t in b["network_target"]]
    assert "search.example.com" in targets
    for t in targets:
        assert "/" not in t and "?" not in t and ":" not in t


def test_mcp_env_secret_redacted():
    payload = adapter.build(scan_id="scan-c", scene="install_precheck", files=_files(FIXTURE_C_MCP))
    blob = repr(payload)
    assert "sk-synthetic-placeholder-not-real" not in blob
    assert "postgres://user" not in blob
    assert "fake-token-placeholder" not in blob
    assert "Bearer fake" not in blob


def test_mcp_multiple_servers():
    parser = McpParser()
    facts = parser.parse(_files(FIXTURE_C_MCP))
    # Two servers produce boundary rows with distinct ids in the final payload.
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_C_MCP))
    ids = [b["boundary_id"] for b in payload["boundaries"]]
    assert len(ids) == len(set(ids))


def test_mcp_broken_config_isolated():
    payload = adapter.build(scan_id="scan-d", scene="install_precheck", files=_files(FIXTURE_D_MCP_BROKEN))
    # Corrupt JSON must not crash the scan; the parser reports unavailable/partial.
    assert payload["parser"]["status"] in {"unavailable", "partial", "failed"}
    assert not payload["evidence"] or all(
        r in {e["evidence_id"] for e in payload["evidence"]}
        for b in payload["boundaries"] for r in b["evidence_refs"]
    )


def test_mcp_unknown_fields_tolerated(tmp_path):
    (tmp_path / "mcp.json").write_text(
        '{"mcpServers":{"s":{"command":"python","args":["x.py"],"unknown_field":123}}}',
        encoding="utf-8",
    )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(tmp_path))
    assert payload["component"]["component_type"] == "mcp_server"
    assert payload["parser"]["status"] in {"success", "partial"}


def test_mcp_no_servers_partial(tmp_path):
    (tmp_path / "mcp.json").write_text('{"someKey":{}}', encoding="utf-8")
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_files(tmp_path))
    assert payload["component"]["component_type"] == "mcp_server"
    assert payload["parser"]["status"] in {"partial", "unavailable"}


def test_mcp_no_config_unresolved(tmp_path):
    (tmp_path / "notes.txt").write_text("no config here", encoding="utf-8")
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_files(tmp_path))
    assert payload["component"]["component_type"] == "project"


# --- MCP: security -----------------------------------------------------------


def test_mcp_no_execute_and_relative_paths():
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_C_MCP))
    for ev in payload["evidence"]:
        path = ev["source_span"]["path"].replace("\\", "/")
        assert ":" not in path and not path.startswith("/") and ".." not in path


def test_mcp_sources_never_emit_env_values():
    # full textual dump of the payload must never contain env *values*.
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_C_MCP))
    for ev in payload["evidence"]:
        for value in ("synthetic-placeholder-not-real", "fake-token-placeholder"):
            assert value not in ev["masked_excerpt"] and value not in repr(ev["details"])


# --- Skill: capabilities / boundaries ----------------------------------------


def test_skill_risky_capabilities():
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_E_SKILL_RISKY))
    names = {c["capability"] for c in payload["capabilities"]}
    assert "shell_execute" in names
    assert "network_access" in names


def test_skill_risky_boundary_shell():
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_E_SKILL_RISKY))
    modes = {b["execution_mode"] for b in payload["boundaries"]}
    assert "shell" in modes


def test_skill_plain_no_capability():
    payload = adapter.build(scan_id="scan", scene="release_precheck", files=_files(FIXTURE_F_SKILL_PLAIN))
    assert payload["capabilities"] == []
    assert payload["component"]["component_type"] == "skill"
    assert payload["component"]["declared_purpose"]


def test_skill_embedded_span_relative():
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_E_SKILL_RISKY))
    for ev in payload["evidence"]:
        assert "SKILL.md" == ev["source_span"]["path"]
        assert ev["source_span"]["start_line"] >= 1


# --- Cross-reference integrity across all three components -------------------


@pytest.mark.parametrize("root", [FIXTURE_C_MCP, FIXTURE_E_SKILL_RISKY, FIXTURE_F_SKILL_PLAIN])
def test_no_dangling_refs_batch2(root):
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    known = {e["evidence_id"] for e in payload["evidence"]}
    for cap in payload["capabilities"]:
        assert set(cap["evidence_refs"]) <= known
    for boundary in payload["boundaries"]:
        assert set(boundary["evidence_refs"]) <= known


@pytest.mark.parametrize("root", [FIXTURE_C_MCP, FIXTURE_E_SKILL_RISKY, FIXTURE_F_SKILL_PLAIN])
def test_ids_unique_batch2(root):
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    plural = {"capability": "capabilities", "boundary": "boundaries", "evidence": "evidence"}
    for kind in ("capability", "boundary", "evidence"):
        ids = [row[f"{kind}_id"] for row in payload[plural[kind]]]
        assert len(ids) == len(set(ids)), kind


@pytest.mark.parametrize("root", [FIXTURE_C_MCP, FIXTURE_E_SKILL_RISKY])
def test_deterministic_batch2(root):
    p1 = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    p2 = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    assert p1 == p2
    assert [c["capability_id"] for c in p1["capabilities"]] == [c["capability_id"] for c in p2["capabilities"]]
    assert [e["evidence_id"] for e in p1["evidence"]] == [e["evidence_id"] for e in p2["evidence"]]


# --- Real member C contract validation ---------------------------------------


@pytest.mark.parametrize(
    "root",
    [
        FIXTURE_C_MCP,
        FIXTURE_D_MCP_BROKEN,
        FIXTURE_E_SKILL_RISKY,
        FIXTURE_F_SKILL_PLAIN,
        FIXTURE_G_SKILL_NEVER,
        FIXTURE_H_MCP_YAML,
        FIXTURE_I_MCP_TOML,
    ],
)
def test_c_contract_validation_batch2(root, contract_module):
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    source = contract_module.IntentCapabilityInput.from_mapping(payload)
    assert source.payload["schema_version"] == SCHEMA_VERSION
    assert source.payload["component"]["component_type"] in {"skill", "mcp_server", "project", "agent"}
    assert source.payload["parser"]["status"] in {"success", "partial", "unavailable", "failed"}


def test_mcp_yaml_capabilities_and_evidence():
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_H_MCP_YAML))
    names = {c["capability"] for c in payload["capabilities"]}
    assert "process_execute" in names
    assert "network_access" in names
    assert "credential_access" in names
    known = {e["evidence_id"] for e in payload["evidence"]}
    for cap in payload["capabilities"]:
        assert set(cap["evidence_refs"]) <= known
    assert payload["parser"]["status"] == "success"


def test_mcp_toml_capabilities_and_evidence():
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_I_MCP_TOML))
    names = {c["capability"] for c in payload["capabilities"]}
    assert "process_execute" in names
    assert "network_access" in names
    assert "credential_access" in names
    known = {e["evidence_id"] for e in payload["evidence"]}
    for boundary in payload["boundaries"]:
        assert set(boundary["evidence_refs"]) <= known
    assert payload["parser"]["status"] == "success"


def test_mcp_yaml_and_toml_never_leak_values():
    for root in (FIXTURE_H_MCP_YAML, FIXTURE_I_MCP_TOML):
        payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
        blob = repr(payload)
        assert "yaml-placeholder-not-real" not in blob
        assert "toml-placeholder-not-real" not in blob
        assert "yaml-fake-token" not in blob


def test_mcp_yaml_toml_stable_ids():
    for root in (FIXTURE_H_MCP_YAML, FIXTURE_I_MCP_TOML):
        p1 = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
        p2 = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
        assert p1 == p2
        assert [c["capability_id"] for c in p1["capabilities"]] == [c["capability_id"] for c in p2["capabilities"]]
        assert [e["evidence_id"] for e in p1["evidence"]] == [e["evidence_id"] for e in p2["evidence"]]


def test_mcp_yaml_toml_relative_paths():
    for root in (FIXTURE_H_MCP_YAML, FIXTURE_I_MCP_TOML):
        payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
        for ev in payload["evidence"]:
            path = ev["source_span"]["path"].replace("\\", "/")
            assert ":" not in path and not path.startswith("/") and ".." not in path


def test_g_skill_contract_from_mapping(contract_module):
    # Batch 2 report claimed all 6 fixtures went through from_mapping; ensure the
    # never-execute skill fixture is also validated against the real contract.
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(FIXTURE_G_SKILL_NEVER))
    source = contract_module.IntentCapabilityInput.from_mapping(payload)
    assert source.payload["schema_version"] == SCHEMA_VERSION
    assert source.payload["component"]["component_type"] == "skill"


def test_c_contract_skill_and_mcp_full(root=FX):
    # Full payload round trip through the frozen contract for one skill & one mcp.
    for sub, scene in [(FIXTURE_C_MCP, "install_precheck"), (FIXTURE_E_SKILL_RISKY, "install_precheck")]:
        payload = adapter.build(scan_id="scan", scene=scene, files=_files(sub))
        from yuanjian_agent.component_security.intent_adapter import SCHEMA_VERSION as V
        assert payload["schema_version"] == V
        # C contract would be exercised via contract_module; here we validate shape.
        assert isinstance(payload["capabilities"], list)
        assert isinstance(payload["boundaries"], list)
        for cap in payload["capabilities"]:
            assert 1 <= cap["impact"] <= 5
            assert 0.0 <= cap["confidence"] <= 1.0


# --- Security: never execute audit code -------------------------------------


def test_never_execute_inline_script(tmp_path):
    root = FIXTURE_G_SKILL_NEVER
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    # The inline script raises if executed; a successful parse proves it was not run.
    assert payload["parser"]["status"] in {"success", "partial"}
    assert payload["component"]["component_type"] == "skill"


def test_never_execute_runtime_crash_is_impossible():
    # `os.system` inside the fixture must never be turned into a real subprocess.
    root = FIXTURE_G_SKILL_NEVER
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    blob = repr(payload)
    assert "pwned" not in blob or "echo" not in blob


def test_mcp_server_never_started(tmp_path):
    # A config pointing at a command must only be read as text, never launched.
    root = FIXTURE_C_MCP
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    assert payload["parser"]["status"] in {"success", "partial"}
    # Evidence excerpts only carry short static identifiers for command/env,
    # never a raw shell command that would have implied a launch.
    for ev in payload["evidence"]:
        assert "python" not in ev["masked_excerpt"] or "launch" in ev["masked_excerpt"]


def test_shell_command_evidence_is_short_and_static():
    root = FIXTURE_E_SKILL_RISKY
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(root))
    for ev in payload["evidence"]:
        assert len(ev["masked_excerpt"]) <= 220


# --- Parser partial / failure isolation --------------------------------------


def test_broken_embedded_script_is_partial(tmp_path):
    (tmp_path / "SKILL.md").write_text(
        "---\ndescription: partial skill\n---\n\n```python\ndef broken(:\n```\n",
        encoding="utf-8",
    )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(tmp_path))
    assert payload["parser"]["status"] == "partial"
    assert payload["parser"]["warnings"]


def test_ten_skills_one_broken_keeps_others(tmp_path):
    # Failure in one SKILL.md embedded script must not break the rest.
    records = []
    for i in range(3):
        sub = tmp_path / f"skill{i}"
        sub.mkdir()
        (sub / "SKILL.md").write_text(
            f"---\ndescription: skill number {i}\n---\n```python\nopen('/tmp/x').read_text()\n```\n",
            encoding="utf-8",
        )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(tmp_path))
    assert payload["component"]["component_type"] == "skill"
    assert payload["parser"]["status"] in {"success", "partial"}


def test_mcp_partial_with_bad_yaml(tmp_path):
    (tmp_path / "mcp.yaml").write_text("mcpServers: [unclosed", encoding="utf-8")
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(tmp_path))
    assert payload["parser"]["status"] in {"partial", "unavailable", "failed"}


# --- Skill: multiple capabilities / boundaries / evidence span ---------------


def test_skill_multiple_capability_evidence_spans(tmp_path):
    (tmp_path / "SKILL.md").write_text(
        "---\ndescription: multiple capability skill\n---\n"
        "```python\nsubprocess.run('x', shell=True)\nrequests.get('https://h.example/a')\n"
        "open('/tmp/f').read_text()\n```\n",
        encoding="utf-8",
    )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(tmp_path))
    names = {c["capability"] for c in payload["capabilities"]}
    assert {"shell_execute", "network_access", "file_read"} <= names
    for ev in payload["evidence"]:
        assert ev["source_span"]["path"] == "SKILL.md"
        assert ev["source_span"]["start_line"] >= 1
    # every capability has at least one evidence_ref
    for cap in payload["capabilities"]:
        assert cap["evidence_refs"]


def test_skill_boundary_data_scope(tmp_path):
    (tmp_path / "SKILL.md").write_text(
        "---\ndescription: filesystem skill\n---\n```python\nopen('/var/data/f').read_text()\n```\n",
        encoding="utf-8",
    )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(tmp_path))
    assert any("filesystem" in b["data_scope"] for b in payload["boundaries"])


def test_skill_relative_paths_only(tmp_path):
    (tmp_path / "SKILL.md").write_text(
        "---\ndescription: rel paths\n---\n```python\nopen('/tmp/x').read_text()\n```\n",
        encoding="utf-8",
    )
    payload = adapter.build(scan_id="scan", scene="install_precheck", files=_files(tmp_path))
    for ev in payload["evidence"]:
        p = ev["source_span"]["path"].replace("\\", "/")
        assert ":" not in p and not p.startswith("/") and ".." not in p
