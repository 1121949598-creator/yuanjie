"""Host-defined, per-request scan plans; never loaded from uploaded projects."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .files import TextFile
from .parsers import parse_project

PROFILE_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class ScanProfile:
    id: str
    scene: str
    modules: tuple[str, ...]
    component_scope: str | None


PROFILES = {
    "project": ScanProfile("project", "release_precheck", ("secret", "license"), None),
    "download": ScanProfile("download", "install_precheck",
                            ("secret", "license", "tool_capability"), "tool"),
    "agent": ScanProfile("agent", "release_precheck",
                         ("secret", "license", "agent_security", "component_security"), "agent"),
}


def resolve_profile(profile: str | None, scene: str | None) -> tuple[ScanProfile | None, str]:
    # Old CLI/API clients keep their previous comprehensive behavior. Never
    # pretend that an old record was produced by one of the new profiles.
    if profile is None:
        scene = scene or "release_precheck"
        if scene not in {"install_precheck", "release_precheck"}:
            raise ValueError("unsupported component-security scene")
        return None, scene
    if profile not in PROFILES:
        raise ValueError("unsupported scan profile")
    plan = PROFILES[profile]
    if scene is not None and scene != plan.scene:
        raise ValueError("scene does not match scan profile")
    return plan, plan.scene


def detect_inputs(files: list[TextFile]) -> dict:
    """Conservative applicability hints, not a safety or Agent-risk assessment.

    Uses the existing pure static parsers, and discards all target-derived
    strings. Unsupported languages and syntax errors cannot imply safety.
    """
    python = [f for f in files if f.relative_path.lower().endswith(".py")]
    names = {Path(f.relative_path).name.lower() for f in files}
    syntax_errors = 0
    agent_hint = False
    for file in python:
        try:
            tree = ast.parse(file.text)
        except (SyntaxError, ValueError, RecursionError):
            syntax_errors += 1
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            if any(m.split(".")[0] in {"langchain", "langchain_core", "langgraph", "crewai", "autogen"}
                   for m in modules):
                agent_hint = True
    try:
        parsed = parse_project(files)
        declared_agent = bool(parsed.agents)
        parser_warning = bool(parsed.warnings)
    except Exception:
        declared_agent, parser_warning = False, True
    mcp = bool(names & {"mcp.json", "mcp.yaml", "mcp.yml", "mcp.toml", "claude_desktop_config.json"})
    unsupported = sum(Path(f.relative_path).suffix.lower() in {
        ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c", ".cpp", ".sh", ".ps1",
    } for f in files)
    return {
        "python_files": len(python), "python_syntax_errors": syntax_errors,
        "unsupported_code_files": unsupported, "agent_detected": declared_agent,
        "agent_hint": agent_hint, "skill_detected": "skill.md" in names,
        "mcp_detected": mcp, "structure_detection_incomplete": parser_warning,
    }


def empty_component_result(scene: str, status: str, reason: str) -> dict:
    return {"schema_version": "1.0", "scene": scene, "status": status,
            "components": [], "summary": {"components": 0, "assessments": 0,
                                            "inconsistent": 0, "needs_review": 0},
            "warnings": [reason]}
