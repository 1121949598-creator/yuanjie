"""Static parsers for the V1 three-component pipeline (member B side).

``SkillParser`` and ``McpParser`` turn already-safe-imported ``TextFile`` objects
into the unified internal static-fact model (``ComponentFacts``) without
executing, importing, or starting the target component. They reuse the shared
capability rules, source-span and stable-id helpers, and redaction from the
facts module. The unified ``IntentCapabilityAdapter`` then projects these facts
to contract 1.0, so no per-component contract builder is needed here.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from ..analysis import load_tool_rules
from ..files import TextFile
from ..models import SourceSpan
from .facts import (
    BoundaryFact,
    CapabilityFact,
    ComponentFacts,
    EvidenceFact,
    _action_for,
    _capability_from_symbol,
    _controls_for,
    _extract_python_facts,
    _resource_for,
    _rule_for,
    mask_excerpt,
)

SKILL_MARKERS = ("SKILL.md", "skill.md")
MCP_CONFIG_NAMES = ("mcp.json", "mcp.yaml", "mcp.yml", "mcp.toml", "claude_desktop_config.json")

_CODE_FENCE_RE = re.compile(r"```(?P<lang>\w*)[ \t]*\r?\n(?P<body>.*?)```", re.DOTALL)

_SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|passwd|auth|authorization|credential)", re.I)
_URL_RE = re.compile(r"(https?://[^\s'\"]+)", re.I)
_FILESYSTEM_WORDS = re.compile(r"(directory|folder|path|file|workspace|data[_-]?dir|input[_-]?dir|\./|/)", re.I)
_CREDENTIAL_WORDS = re.compile(r"(credential|secret|token|api[_-]?key|password|database[_-]?url)", re.I)


def _host_of(url: str) -> str:
    """Return only the host of a URL as a safe network-target identifier.

    Never returns query strings, credentials, or full paths. Returns an empty
    string when the URL cannot be parsed statically.
    """
    m = re.match(r"https?://([^/?#:\s]+)", url, re.I)
    if not m:
        return ""
    return m.group(1)


def _call_symbol(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        parts: list[str] = []
        cur = fn
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        return fn.attr
    return ""


def _env_secret_keys(env: dict[str, Any]) -> list[str]:
    return sorted(str(k) for k in env if isinstance(k, str) and _SECRET_KEY_RE.search(k))


class SkillParser:
    """Static parser for a Skill declared by ``SKILL.md`` and its local scripts."""

    def parse(self, files: list[TextFile], *, rules: dict[str, Any] | None = None) -> ComponentFacts:
        rules = rules or load_tool_rules()
        skill_file = next((f for f in files if Path(f.relative_path).name in SKILL_MARKERS), None)
        warnings: list[str] = []

        if skill_file is None:
            return ComponentFacts(
                component_type="skill",
                name="skill",
                declared_purpose="",
                purpose_spans=[],
                extraction_status="unresolved",
                extraction_reasons=["SKILL.md was not present"],
                capabilities=[],
                boundaries=[],
                warnings=["skill:no_manifest"],
            )

        purpose, name, purpose_spans, status, reasons = self._declaration(skill_file)
        capabilities: list[CapabilityFact] = []
        for file in files:
            if file.path.suffix.lower() != ".py":
                continue
            cap_facts, file_warnings = _extract_python_facts(file, rules)
            warnings.extend(file_warnings)
            capabilities.extend(cap_facts)

        embedded, embed_warnings = self._extract_embedded_python(skill_file, rules)
        warnings.extend(embed_warnings)
        capabilities.extend(embedded)

        capabilities = _merge_capabilities(capabilities)
        boundaries = self._build_boundaries(skill_file, capabilities, rules)

        return ComponentFacts(
            component_type="skill",
            name=name,
            declared_purpose=purpose,
            purpose_spans=purpose_spans,
            extraction_status=status,
            extraction_reasons=reasons,
            capabilities=capabilities,
            boundaries=boundaries,
            warnings=warnings,
        )

    @staticmethod
    def _declaration(skill_file: TextFile) -> tuple[str, str, list[SourceSpan], str, list[str]]:
        text = skill_file.text
        spans: list[SourceSpan] = []
        name = Path(skill_file.relative_path).parent.name or "skill"
        purpose = ""
        all_lines = text.splitlines()
        body_start = 0
        front = text.split("---", 2)
        if len(front) >= 3:
            body_start = len(front[0].splitlines()) + len(front[1].splitlines()) + 2
            for line in front[1].splitlines():
                match = re.match(r"^\s*(description|name|summary)\s*:\s*(.*)$", line, re.I)
                if not match:
                    continue
                key, value = match.group(1).lower(), match.group(2).strip().strip("'\"")
                if not value:
                    continue
                lineno = all_lines.index(line) + 1
                if key == "name":
                    name = value
                if key in {"description", "summary"} and not purpose:
                    purpose = value
                    spans.append(SourceSpan(skill_file.relative_path, lineno, lineno, 0, 0))
            if purpose:
                return purpose, name, spans, "resolved", []
        if not purpose:
            for idx in range(body_start, len(all_lines)):
                stripped = all_lines[idx].strip()
                if stripped and len(stripped) > 6 and not stripped.startswith(("#", "[", "]", "-", "*", "---")):
                    purpose = stripped[:200]
                    spans.append(SourceSpan(skill_file.relative_path, idx + 1, idx + 1, 0, 0))
                    break
        if not purpose:
            return "", name, [], "unresolved", ["No declared purpose was found in SKILL.md"]
        return purpose, name, spans, "resolved", []

    @staticmethod
    def _extract_embedded_python(
        skill_file: TextFile,
        rules: dict[str, Any],
    ) -> tuple[list[CapabilityFact], list[str]]:
        text = skill_file.text
        lines = text.splitlines()
        capabilities: dict[str, CapabilityFact] = {}
        warnings: list[str] = []
        for match in _CODE_FENCE_RE.finditer(text):
            lang = (match.group("lang") or "").lower()
            if lang not in {"python", "py"}:
                continue
            body = match.group("body")
            fence_start_line = text[: match.start()].count("\n") + 1
            try:
                tree = ast.parse(body, filename=skill_file.relative_path)
            except SyntaxError as error:
                lineno = getattr(error, "lineno", None)
                warnings.append(f"skill-embedded-syntax:{skill_file.relative_path}:{fence_start_line + (lineno or 1) - 1}")
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                symbol = _call_symbol(node)
                if not symbol:
                    continue
                capability_id = _capability_from_symbol(symbol, rules)
                if not capability_id:
                    if symbol == "open" and any(
                        (isinstance(k.value, ast.Constant) and "w" in str(k.value.value))
                        for k in (node.keywords or []) if k.arg == "mode"
                    ):
                        capability_id = "file_write"
                    else:
                        continue
                span = SourceSpan(
                    skill_file.relative_path,
                    fence_start_line + getattr(node, "lineno", 1) - 1,
                    fence_start_line + getattr(node, "end_lineno", getattr(node, "lineno", 1)) - 1,
                    getattr(node, "col_offset", 0),
                    getattr(node, "end_col_offset", 0),
                )
                segment = ast.get_source_segment(body, node) or symbol
                evidence = EvidenceFact(
                    symbol=symbol,
                    span=span,
                    excerpt=mask_excerpt(segment.strip()[:200]),
                    parser="skill-embedded-static",
                    details={
                        "symbol": symbol,
                        "parser": "skill-embedded-static",
                        "embedding": "SKILL.md",
                        "rule_version": str(rules.get("version", "1.0")),
                    },
                )
                cap = capabilities.get(capability_id)
                if cap is None:
                    rule = _rule_for(capability_id, rules) or {}
                    cap = CapabilityFact(
                        capability=capability_id,
                        action=_action_for(capability_id, symbol),
                        resource=_resource_for(symbol),
                        impact=int(rule.get("impact", 1)),
                        confidence=0.0,
                        rule_id=f"component.capability.{capability_id}",
                        controls=_controls_for(text, symbol),
                    )
                    capabilities[capability_id] = cap
                cap.evidence.append(evidence)
        for cap in capabilities.values():
            distinct = {ev.symbol for ev in cap.evidence}
            cap.confidence = round(min(0.99, 0.55 + 0.10 * len(distinct)) if distinct else 0.40, 2)
        return list(capabilities.values()), warnings

    @staticmethod
    def _build_boundaries(
        skill_file: TextFile,
        capabilities: list[CapabilityFact],
        rules: dict[str, Any],
    ) -> list[BoundaryFact]:
        data_scope: set[str] = {cap.resource for cap in capabilities if cap.resource != "unknown"}
        execution_options = {cap.capability for cap in capabilities}
        if "shell_execute" in execution_options:
            execution_mode = "shell"
        elif any("subprocess" in ev.symbol for cap in capabilities for ev in cap.evidence):
            execution_mode = "local_process"
        else:
            execution_mode = "none"
        credential_use = any(cap.capability == "credential_access" for cap in capabilities)

        body = skill_file.text
        evidence: list[EvidenceFact] = []
        if _FILESYSTEM_WORDS.search(body):
            span = SourceSpan(skill_file.relative_path, 1, max(skill_file.text.count("\n") + 1, 1), 0, 0)
            evidence.append(
                EvidenceFact(
                    symbol="SKILL.md",
                    span=span,
                    excerpt="declared data scope (directory / workspace)",
                    parser="skill-frontmatter",
                    details={"parser": "skill-frontmatter", "rule_version": str(rules.get("version", "1.0"))},
                )
            )
        return [
            BoundaryFact(
                data_scope=sorted(data_scope) if data_scope else (["filesystem"] if evidence else []),
                network_target=[],
                credential_use=credential_use,
                execution_mode=execution_mode,
                evidence=evidence,
            )
        ]


def _merge_capabilities(capabilities: list[CapabilityFact]) -> list[CapabilityFact]:
    merged: dict[str, CapabilityFact] = {}
    for cap in capabilities:
        if cap.capability in merged:
            existing = merged[cap.capability]
            existing.evidence.extend(cap.evidence)
            existing.controls = sorted(set(existing.controls) | set(cap.controls))
            existing.confidence = max(existing.confidence, cap.confidence)
        else:
            merged[cap.capability] = cap
    return [merged[key] for key in sorted(merged)]


class McpParser:
    """Static parser for MCP server declaration files (mcp.json and friends)."""

    def parse(self, files: list[TextFile], *, rules: dict[str, Any] | None = None) -> ComponentFacts:
        rules = rules or load_tool_rules()
        config_file = next(
            (f for f in files if Path(f.relative_path).name.lower() in MCP_CONFIG_NAMES),
            None,
        )
        warnings: list[str] = []

        if config_file is None:
            return ComponentFacts(
                component_type="mcp_server",
                name="mcp_server",
                declared_purpose="",
                purpose_spans=[],
                extraction_status="unresolved",
                extraction_reasons=["No supported MCP configuration file was present"],
                capabilities=[],
                boundaries=[],
                warnings=["mcp:no_config"],
            )

        try:
            data = self._load(config_file)
        except (ValueError, json.JSONDecodeError) as error:
            warnings.append(f"mcp-parse-error:{config_file.relative_path}")
            return ComponentFacts(
                component_type="mcp_server",
                name="mcp_server",
                declared_purpose="",
                purpose_spans=[],
                extraction_status="unresolved",
                extraction_reasons=["MCP configuration could not be parsed"],
                capabilities=[],
                boundaries=[],
                warnings=warnings,
            )

        servers = self._find_servers(data)
        if not servers:
            return ComponentFacts(
                component_type="mcp_server",
                name="mcp_server",
                declared_purpose="",
                purpose_spans=[],
                extraction_status="partial",
                extraction_reasons=["No mcpServers object was found in the configuration"],
                capabilities=[],
                boundaries=[],
                warnings=["mcp:no_servers"],
            )

        server_names = sorted(str(name) for name in servers)
        capabilities: list[CapabilityFact] = []
        boundaries: list[BoundaryFact] = []
        for name in server_names:
            server = servers.get(name)
            if not isinstance(server, dict):
                warnings.append(f"mcp:server_non_object:{name}")
                continue
            self._ingest_server(config_file, name, server, rules, capabilities, boundaries, warnings)

        capabilities = _merge_capabilities(capabilities)
        status = "partial" if warnings else "resolved"
        file_span = SourceSpan(config_file.relative_path, 1, max(config_file.text.count("\n") + 1, 1), 0, 0)

        return ComponentFacts(
            component_type="mcp_server",
            name=Path(config_file.relative_path).stem,
            declared_purpose="MCP server configuration declares remote or local tool endpoints",
            purpose_spans=[file_span],
            extraction_status=status,
            extraction_reasons=([] if status == "resolved" else warnings[:10]),
            capabilities=capabilities,
            boundaries=boundaries if boundaries else [],
            warnings=warnings,
        )

    def _ingest_server(
        self,
        config_file: TextFile,
        name: str,
        server: dict[str, Any],
        rules: dict[str, Any],
        capabilities: list[CapabilityFact],
        boundaries: list[BoundaryFact],
        warnings: list[str],
    ) -> None:
        span = SourceSpan(config_file.relative_path, 1, max(config_file.text.count("\n") + 1, 1), 0, 0)
        url = str(server.get("url", "") or "")
        if url.lower().startswith(("http://", "https://")):
            host = _host_of(url)
            if host:
                cap = self._upsert(capabilities, "network_access", "network_request", "remote_endpoint", rules)
                cap.evidence.append(
                    EvidenceFact(
                        symbol="mcp.url",
                        span=span,
                        excerpt=f"remote endpoint {host}",
                        parser="mcp-config-static",
                        details={
                            "server": name,
                            "symbol": "mcp.url",
                            "parser": "mcp-config-static",
                            "rule_version": str(rules.get("version", "1.0")),
                        },
                    )
                )
                boundaries.append(
                    BoundaryFact(
                        data_scope=[],
                        network_target=[host],
                        credential_use=False,
                        execution_mode="network",
                        evidence=[cap.evidence[-1]],
                    )
                )

        env = server.get("env")
        if isinstance(env, dict) and env:
            secret_keys = _env_secret_keys(env)
            if secret_keys:
                cap = self._upsert(capabilities, "credential_access", "read_credential", "process_environment_credentials", rules)
                cap.evidence.append(
                    EvidenceFact(
                        symbol="mcp.env",
                        span=span,
                        excerpt=f"credential env refs {','.join(secret_keys)}",
                        parser="mcp-config-static",
                        details={
                            "server": name,
                            "symbol": "mcp.env",
                            "parser": "mcp-config-static",
                            "rule_version": str(rules.get("version", "1.0")),
                        },
                    )
                )
                boundaries.append(
                    BoundaryFact(
                        data_scope=[],
                        network_target=[],
                        credential_use=True,
                        execution_mode="local_process",
                        evidence=[cap.evidence[-1]],
                    )
                )

        command = str(server.get("command", "") or "")
        args = server.get("args", [])
        if command:
            command_name = Path(command).name
            if command_name.lower() in {"bash", "sh", "zsh", "cmd", "powershell", "pwsh"}:
                cap = self._upsert(capabilities, "shell_execute", "execute_shell", "local_operating_system", rules)
                cap.evidence.append(
                    EvidenceFact(
                        symbol="mcp.command",
                        span=span,
                        excerpt=f"shell command {command_name}",
                        parser="mcp-config-static",
                        details={
                            "server": name,
                            "symbol": "mcp.command",
                            "parser": "mcp-config-static",
                            "rule_version": str(rules.get("version", "1.0")),
                        },
                    )
                )
            elif command_name.lower() in {"python", "python3", "node", "npx", "uvx", "docker", "docker-compose"}:
                cap = self._upsert(capabilities, "process_execute", "execute_process", "local_operating_system", rules)
                cap.evidence.append(
                    EvidenceFact(
                        symbol="mcp.command",
                        span=span,
                        excerpt=f"launch command {command_name}",
                        parser="mcp-config-static",
                        details={
                            "server": name,
                            "symbol": "mcp.command",
                            "parser": "mcp-config-static",
                            "rule_version": str(rules.get("version", "1.0")),
                        },
                    )
                )
                if isinstance(args, list) and any(isinstance(a, str) and _FILESYSTEM_WORDS.search(a) for a in args):
                    boundaries.append(
                        BoundaryFact(
                            data_scope=["filesystem"],
                            network_target=[],
                            credential_use=bool(_env_secret_keys(env)) if isinstance(env, dict) else False,
                            execution_mode="local_process",
                            evidence=[cap.evidence[-1]],
                        )
                    )

    @staticmethod
    def _upsert(
        capabilities: list[CapabilityFact],
        capability: str,
        action: str,
        resource: str,
        rules: dict[str, Any],
    ) -> CapabilityFact:
        for cap in capabilities:
            if cap.capability == capability:
                return cap
        rule = _rule_for(capability, rules) or {}
        cap = CapabilityFact(
            capability=capability,
            action=action,
            resource=resource,
            impact=int(rule.get("impact", 1)),
            confidence=0.0,
            rule_id=f"component.capability.{capability}",
            controls=[],
        )
        capabilities.append(cap)
        return cap

    @staticmethod
    def _load(file: TextFile) -> Any:
        suffix = Path(file.relative_path).suffix.lower()
        if suffix == ".json":
            return json.loads(file.text)
        if suffix == ".toml":
            import tomllib

            return tomllib.loads(file.text)
        import yaml

        return yaml.safe_load(file.text)

    @staticmethod
    def _find_servers(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            for key in ("mcpServers", "mcp_servers", "servers"):
                candidate = value.get(key)
                if isinstance(candidate, dict):
                    return candidate
        return {}
