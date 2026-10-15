"""Static fact extraction for the V1 intent/capability contract.

This module turns already-parsed project files into component-level static
facts (component, capabilities, boundaries, evidence) without executing or
installing the target project. It reuses the existing capability rules
(``tool_capabilities.yml``) and source-span / stable-id helpers from the main
codebase.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..analysis import load_tool_rules
from ..files import TextFile
from ..models import SourceSpan
from ..secret.masking import mask_secret

PARSER_VERSION = "component-parser-1.0"

# Deterministic names used to recognise a component without framework knowledge.
_SKILL_MARKERS = ("SKILL.md", "skill.md")
_MCP_MARKERS = ("mcp.json", "mcp.yaml", "mcp.yml", "mcp.toml", "claude_desktop_config.json")


@dataclass(slots=True)
class EvidenceFact:
    symbol: str
    span: SourceSpan
    excerpt: str
    parser: str
    details: dict[str, Any]


@dataclass(slots=True)
class CapabilityFact:
    capability: str
    action: str
    resource: str
    impact: int
    confidence: float
    rule_id: str
    controls: list[str]
    evidence: list[EvidenceFact] = field(default_factory=list)


@dataclass(slots=True)
class BoundaryFact:
    data_scope: list[str]
    network_target: list[str]
    credential_use: bool
    execution_mode: str
    evidence: list[EvidenceFact] = field(default_factory=list)


@dataclass(slots=True)
class ComponentFacts:
    component_type: str
    name: str
    declared_purpose: str
    purpose_spans: list[SourceSpan]
    extraction_status: str
    extraction_reasons: list[str]
    capabilities: list[CapabilityFact] = field(default_factory=list)
    boundaries: list[BoundaryFact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|passwd|auth|authorization|credential)", re.I)
_STRING_LITERAL_RE = re.compile(r"(['\"])(?P<body>(?:(?!\1).)*)\1")


def mask_excerpt(text: str) -> str:
    """Mask secret-looking string literals while keeping the explanatory call.

    A literal is masked when its nearest preceding key names look secret-ish
    (api_key/token/secret/password/auth/...) or when the literal itself has
    high character diversity (looks like an opaque credential). Reuses the
    project's ``mask_secret`` so a captured value is never emitted intact.
    """
    def _is_secret_literal(body: str, prefix: str) -> bool:
        if _SECRET_KEY_RE.search(prefix.splitlines()[-1]):
            return True
        if len(body) < 6:
            return False
        diversity = len(set(body))
        return diversity >= 5 and not body.isspace()

    def _replace(match: "re.Match[str]") -> str:
        quote = match.group(1)
        body = match.group("body")
        prefix = text[max(0, match.start() - 24): match.start()]
        if _STRING_LITERAL_RE.pattern and _is_secret_literal(body, prefix):
            return f"{quote}****{quote}"
        return match.group(0)

    return _STRING_LITERAL_RE.sub(_replace, text)


def _masked_line(text: str, node: ast.AST, fallback: str = "") -> str:
    segment = ast.get_source_segment(text, node)
    if not segment:
        return fallback
    return mask_excerpt(segment.strip()[:200])


def _capability_from_symbol(symbol: str, rules: dict[str, Any]) -> str | None:
    norm = symbol.lower()
    for rule in rules.get("capabilities", []):
        for pattern in rule.get("call_patterns", []):
            pattern_lower = pattern.lower()
            if norm == pattern_lower or norm.endswith(f".{pattern_lower}"):
                return rule["id"]
            if "." not in pattern_lower and norm.rsplit(".", 1)[-1] == pattern_lower:
                return rule["id"]
    return None


def _rule_for(capability: str, rules: dict[str, Any]) -> dict[str, Any] | None:
    for rule in rules.get("capabilities", []):
        if rule.get("id") == capability:
            return rule
    return None


def _action_for(capability: str, symbol: str) -> str:
    name = symbol.rsplit(".", 1)[-1].lower()
    action_map = {
        "file_read": "read_" + (name if name not in ("open",) else "file"),
        "file_write": "write_" + (name if name not in ("open",) else "file"),
        "file_delete": "delete_" + (name or "file"),
        "shell_execute": "execute_shell",
        "network_access": "network_request",
        "credential_access": "read_credential",
        "process_execute": "execute_process",
    }
    return action_map.get(capability, f"call_{name or capability}")


def _resource_for(symbol: str) -> str:
    full = symbol.lower()
    name = full.rsplit(".", 1)[-1]
    if name in {"getenv", "environ"} or full.endswith("environ.get") or full.endswith("environ"):
        return "process_environment_credentials"
    if name.startswith("subprocess") or name in {"system", "popen", "call", "run", "check_output", "check_call"}:
        return "local_operating_system"
    if name in {"open", "read_text", "read_bytes", "glob", "iterdir", "listdir", "scandir", "walk", "write_text", "unlink", "rmtree"}:
        return "filesystem"
    return "unknown"


_EXTENSION_CONTROLS = ("*.md", "*.py", "*.txt", "*.json", "*.yaml", "*.yml", "*.toml")


def _controls_for(text: str, symbol: str) -> list[str]:
    controls: list[str] = []
    lower = text
    if re.search(r"(user_selected|selected|choose|input_dir|in_dir)", lower, re.I) and symbol in (
        "Path.glob", "Path.iterdir", "open", "Path.read_text", "Path.read_bytes", "os.listdir", "os.scandir"
    ):
        controls.append("user_selected_path")
    if any(ext in lower for ext in _EXTENSION_CONTROLS):
        controls.append("extension_allowlist")
    return controls


def _detect_component(files: list[TextFile], parsed_agents: list[Any]) -> tuple[str, str]:
    names = {Path(f.relative_path).name for f in files}
    for marker in _SKILL_MARKERS:
        if marker in names:
            return "skill", marker
    for marker in _MCP_MARKERS:
        if marker in names:
            return "mcp_server", marker
    readme = any(Path(f.relative_path).name.lower().startswith("readme") for f in files)
    entry_scripts = {
        Path(f.relative_path).name.lower()
        for f in files
        if Path(f.relative_path).suffix.lower() == ".py"
        and Path(f.relative_path).name.lower() in {"agent.py", "main.py", "app.py", "server.py", "cli.py"}
    }
    if readme and entry_scripts:
        return "agent", "agent"
    if parsed_agents:
        return "agent", "agent"
    return "project", "project"


def _purpose_from_skill(file: TextFile, relative: str) -> tuple[str, str, list[SourceSpan], str, list[str]]:
    text = file.text
    spans: list[SourceSpan] = []
    front = text.split("---", 2)
    purpose = ""
    name = Path(relative).parent.name or "skill"
    if len(front) >= 3:
        for line in front[1].splitlines():
            match = re.match(r"^\s*(description|name|summary)\s*:\s*(.*)$", line, re.I)
            if not match:
                continue
            key, value = match.group(1).lower(), match.group(2).strip().strip("'\"")
            if not value:
                continue
            lineno = text.splitlines().index(line) + 1
            if key == "name":
                name = value
            # declared_purpose must come from an actual scope declaration,
            # preferring description/summary over the component's name.
            if key in {"description", "summary"} and not purpose:
                purpose = value
                spans.append(SourceSpan(relative, lineno, lineno, 0, 0))
        if purpose:
            return purpose, name, spans, "resolved", []
    # Fall back to the first substantial body line only when no description
    # was declared; do not treat the component name as its purpose.
    if not purpose:
        for idx, line in enumerate(text.splitlines()):
            stripped = line.strip()
            if stripped and len(stripped) > 6 and not stripped.startswith(("#", "[", "]", "-", "*", "---")):
                purpose = stripped[:200]
                spans.append(SourceSpan(relative, idx + 1, idx + 1, 0, 0))
                break
    if not purpose:
        return "", name, [], "unresolved", ["No declared purpose was found in SKILL.md"]
    return purpose, name, spans, "resolved", []


def _purpose_from_agent(
    files: list[TextFile],
    parsed_agents: list[Any],
    agents_by_name: dict[str, tuple[TextFile, ast.AST]],
) -> tuple[str, list[SourceSpan], str, list[str]]:
    readme = next((f for f in files if Path(f.relative_path).name.lower().startswith("readme")), None)
    if readme:
        for line in readme.text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", "[", "]", "-", "*")):
                lineno = readme.text.splitlines().index(line) + 1
                return stripped[:200], [SourceSpan(readme.relative_path, lineno, lineno, 0, 0)], "resolved", []
    for agent in parsed_agents:
        if agent.task_text and agent.task_text != "MCP client configuration":
            span = agent.source_spans[0] if agent.source_spans else SourceSpan("agent.py", 1, 1)
            return agent.task_text[:200], [span], "resolved", []
    if agents_by_name:
        for f, node in agents_by_name.values():
            segment = ast.get_source_segment(f.text, node) or ""
            m = re.search(r"(?:prompt|description|goal|backstory|system_prompt)\s*=\s*['\"]([^'\"]{6,})['\"]", segment)
            if m:
                span = SourceSpan(
                    f.relative_path, getattr(node, "lineno", 1), getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                    getattr(node, "col_offset", 0), getattr(node, "end_col_offset", 0),
                )
                return m.group(1)[:200], [span], "resolved", []
    return "", [], "unresolved", ["No declared purpose was found in agent source or README"]


def _extract_python_facts(file: TextFile, rules: dict[str, Any]) -> tuple[list[CapabilityFact], list[str]]:
    try:
        tree = ast.parse(file.text, filename=file.relative_path)
    except SyntaxError as error:
        line = getattr(error, "lineno", None) or 1
        return [], [f"python-syntax-error:{file.relative_path}:{line}"]

    capabilities: dict[str, CapabilityFact] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        symbol = ""
        fn = node.func
        if isinstance(fn, ast.Name):
            symbol = fn.id
        elif isinstance(fn, ast.Attribute):
            parts = []
            cur = fn
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
                symbol = ".".join(reversed(parts))
            else:
                symbol = fn.attr
        if not symbol:
            continue
        capability_id = _capability_from_symbol(symbol, rules)
        if not capability_id:
            # write-mode open() is a file_write fact only when mode is present.
            if symbol == "open" and any(
                (isinstance(k.value, ast.Constant) and "w" in str(k.value.value))
                for k in (node.keywords or []) if k.arg == "mode"
            ):
                capability_id = "file_write"
            else:
                continue
        span = SourceSpan(
            file.relative_path,
            getattr(node, "lineno", 1),
            getattr(node, "end_lineno", getattr(node, "lineno", 1)),
            getattr(node, "col_offset", 0),
            getattr(node, "end_col_offset", 0),
        )
        excerpt = _masked_line(file.text, node, fallback=symbol)
        evidence = EvidenceFact(
            symbol=symbol,
            span=span,
            excerpt=excerpt,
            parser="python-ast-static",
            details={
                "symbol": symbol,
                "parser": "python-ast-static",
                "rule_version": str(rules.get("version", "1.0")),
            },
        )
        cap = capabilities.get(capability_id)
        if cap is None:
            rule = _rule_for(capability_id, rules) or {}
            impact = int(rule.get("impact", 1))
            cap = CapabilityFact(
                capability=capability_id,
                action=_action_for(capability_id, symbol),
                resource=_resource_for(symbol),
                impact=impact,
                confidence=0.0,
                rule_id=f"component.capability.{capability_id}",
                controls=_controls_for(file.text, symbol),
            )
            capabilities[capability_id] = cap
        cap.evidence.append(evidence)

    # Confidence reflects static-evidence certainty, not malice probability.
    for cap in capabilities.values():
        distinct = {ev.symbol for ev in cap.evidence}
        cap.confidence = min(0.99, 0.55 + 0.10 * len(distinct)) if distinct else 0.40
        cap.confidence = round(cap.confidence, 2)
    return list(capabilities.values()), []


def _agent_name(files: list[TextFile]) -> str:
    readme = next((f for f in files if Path(f.relative_path).name.lower().startswith("readme")), None)
    if readme:
        for line in readme.text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped.lstrip("#").strip()
                if heading:
                    return heading[:100]
    entry = next(
        (f for f in files
         if Path(f.relative_path).suffix.lower() == ".py"
         and Path(f.relative_path).stem in {"agent", "main", "app", "server", "cli"}),
        None,
    )
    if entry:
        return Path(entry.relative_path).stem
    return "agent"


def detect_component(
    files: list[TextFile], parsed_agents: list[Any] | None = None
) -> tuple[str, str]:
    """Public wrapper over the internal component-type detection."""
    return _detect_component(files, list(parsed_agents or []))


def extract_component_facts(
    files: list[TextFile],
    *,
    parsed_agents: list[Any] | None = None,
    agents_by_name: dict[str, tuple[TextFile, ast.AST]] | None = None,
    rules: dict[str, Any] | None = None,
) -> tuple[ComponentFacts, list[str]]:
    rules = rules or load_tool_rules()
    parsed_agents = parsed_agents or []
    agents_by_name = agents_by_name or {}
    warnings: list[str] = []

    component_type, _marker = _detect_component(files, parsed_agents)

    if component_type == "skill":
        skill_file = next((f for f in files if Path(f.relative_path).name in _SKILL_MARKERS), None)
        if skill_file:
            purpose, name, spans, status, reasons = _purpose_from_skill(skill_file, skill_file.relative_path)
        else:
            purpose, name, spans, status, reasons = "", "skill", [], "unresolved", ["SKILL.md was not readable"]
        return (
            ComponentFacts(
                component_type="skill",
                name=name,
                declared_purpose=purpose,
                purpose_spans=spans,
                extraction_status=status,
                extraction_reasons=reasons,
                capabilities=_python_capabilities(files, rules, warnings),
                boundaries=[],
                warnings=warnings,
            ),
            warnings,
        )

    if component_type == "mcp_server":
        return (
            ComponentFacts(
                component_type="mcp_server",
                name="mcp_server",
                declared_purpose="",
                purpose_spans=[],
                extraction_status="partial",
                extraction_reasons=["MCP server declarative parsing is provided by McpParser"],
                capabilities=[],
                boundaries=[],
                warnings=warnings,
            ),
            warnings,
        )

    if component_type == "agent":
        purpose, spans, status, reasons = _purpose_from_agent(files, parsed_agents, agents_by_name)
        name = _agent_name(files)
    else:
        purpose, spans, status, reasons = "", [], "unresolved", ["Project component has no declared purpose"]
        name = "project"

    capabilities = _python_capabilities(files, rules, warnings)

    return (
        ComponentFacts(
            component_type=component_type,
            name=name,
            declared_purpose=purpose,
            purpose_spans=spans,
            extraction_status=status,
            extraction_reasons=reasons,
            capabilities=capabilities,
            warnings=warnings,
        ),
        warnings,
    )


def _python_capabilities(
    files: list[TextFile],
    rules: dict[str, Any],
    warnings: list[str],
) -> list[CapabilityFact]:
    capabilities: list[CapabilityFact] = []
    for file in files:
        if file.path.suffix.lower() != ".py":
            continue
        cap_facts, file_warnings = _extract_python_facts(file, rules)
        warnings.extend(file_warnings)
        capabilities.extend(cap_facts)
    merged: dict[str, CapabilityFact] = {}
    for cap in capabilities:
        if cap.capability in merged:
            existing = merged[cap.capability]
            existing.evidence.extend(cap.evidence)
            existing.controls = sorted(set(existing.controls) | set(cap.controls))
            existing.confidence = max(existing.confidence, cap.confidence)
        else:
            merged[cap.capability] = cap
    return list(merged.values())
