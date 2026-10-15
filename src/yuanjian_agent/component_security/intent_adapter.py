"""Intent/Capability contract 1.0 adapter (member B side).

Builds a contract payload (``IntentCapabilityInput``) from static component
facts. The payload is consumed by member C's ``IntentCapabilityInput``
through ``from_mapping``; this module never executes target code and never
emits absolute paths or raw secrets.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..analysis import load_tool_rules
from ..files import TextFile
from ..core.identifiers import stable_id
from .facts import (
    PARSER_VERSION,
    CapabilityFact,
    ComponentFacts,
    EvidenceFact,
    detect_component,
    extract_component_facts,
)

SCHEMA_VERSION = "1.0"
SCENES = {"install_precheck", "release_precheck"}


def _execution_mode(capabilities: Sequence[CapabilityFact]) -> str:
    names = {cap.capability for cap in capabilities}
    if "shell_execute" in names:
        return "shell"
    if "process_execute" in names or any("subprocess" in ev.symbol for cap in capabilities for ev in cap.evidence):
        return "local_process"
    return "none"


def _aggregate_boundaries(
    capabilities: Sequence[CapabilityFact],
    component_id: str,
    cap_evidence_ids: Sequence[tuple[int, int, str]],
) -> list[dict[str, Any]]:
    if not capabilities:
        return []
    data_scope = sorted({cap.resource for cap in capabilities if cap.resource != "unknown"})
    credential_use = any(cap.capability == "credential_access" for cap in capabilities)
    execution_mode = _execution_mode(capabilities)
    ids = [eid for _c, _j, eid in cap_evidence_ids]
    return [
        {
            "boundary_id": stable_id("bnd", component_id, execution_mode),
            "data_scope": data_scope,
            "network_target": [],
            "credential_use": credential_use,
            "execution_mode": execution_mode,
            "evidence_refs": list(dict.fromkeys(ids)),
        }
    ]


def _parser_status(facts: ComponentFacts, has_python: bool) -> str:
    if not has_python and not facts.purpose_spans:
        return "unavailable"
    if facts.warnings:
        return "partial"
    if facts.extraction_status in {"partial", "unresolved"}:
        return "partial"
    return "success"


def _stable_warnings(facts: ComponentFacts) -> list[str]:
    out: list[str] = []
    for warning in facts.warnings[:20]:
        code = warning.split(":", 1)[0]
        out.append(code)
    if facts.extraction_status != "resolved":
        out.append(f"extraction:{facts.extraction_status}")
    return sorted(set(out))


def _span_dict(span: Any) -> dict[str, Any]:
    return {
        "path": span.path,
        "start_line": span.start_line,
        "end_line": span.end_line,
        "start_column": span.start_column,
        "end_column": span.end_column,
    }


class IntentCapabilityAdapter:
    """Builds a ``IntentCapabilityInput`` payload from static component facts."""

    def __init__(self, rules: Mapping[str, Any] | None = None) -> None:
        self.rules = dict(rules) if rules else load_tool_rules()

    def build(
        self,
        *,
        scan_id: str,
        scene: str,
        files: Sequence[TextFile],
        parsed_agents: Sequence[Any] | None = None,
        agents_by_name: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if scene not in SCENES:
            raise ValueError(f"unsupported scene: {scene!r}")
        file_list = list(files)
        try:
            base_facts, base_warnings = extract_component_facts(
                file_list,
                parsed_agents=list(parsed_agents or []),
                agents_by_name=dict(agents_by_name or {}),
                rules=self.rules,
            )
            if base_facts.component_type == "skill":
                from .parsers import SkillParser

                facts = SkillParser().parse(file_list, rules=self.rules)
                warnings = facts.warnings
            elif base_facts.component_type == "mcp_server":
                from .parsers import McpParser

                facts = McpParser().parse(file_list, rules=self.rules)
                warnings = facts.warnings
            else:
                facts = base_facts
                warnings = base_warnings
        except Exception:
            # Unrecoverable parse failure: fail closed with a fixed, sanitized
            # parser status (never leak the raw exception or input content).
            return {
                "schema_version": SCHEMA_VERSION,
                "scan_id": scan_id,
                "scene": scene,
                "component": {
                    "component_id": f"component_{stable_id('component', 'unknown', scan_id)}",
                    "component_type": "project",
                    "name": "unknown",
                    "declared_purpose": "",
                    "source_spans": [],
                    "extraction_status": "unresolved",
                    "extraction_reasons": ["Unrecoverable parse failure"],
                },
                "capabilities": [],
                "boundaries": [],
                "evidence": [],
                "parser": {
                    "status": "failed",
                    "version": PARSER_VERSION,
                    "warnings": ["parser:failed"],
                },
            }

        has_python = any(f.relative_path.lower().endswith(".py") for f in files)
        return self._render(facts, scan_id, scene, has_python)

    def build_agents(
        self,
        *,
        scan_id: str,
        scene: str,
        files: Sequence[TextFile],
    ) -> list[dict[str, Any]]:
        """Build one Contract 1.0 payload per statically declared Agent.

        Agents are resolved without executing any audited code. Each Agent only
        receives the capabilities of the Tools it statically binds, so multiple
        Agents inside one file stay isolated. Dynamic bindings degrade to
        ``partial`` and are never guessed.
        """
        if scene not in SCENES:
            raise ValueError(f"unsupported scene: {scene!r}")
        from .agent_resolver import AgentResolver, effective_agent_facts

        resolver = AgentResolver(self.rules)
        declarations = resolver.resolve(list(files))
        has_python = any(f.relative_path.lower().endswith(".py") for f in files)
        payloads: list[dict[str, Any]] = []
        for facts in effective_agent_facts(declarations, list(files), self.rules):
            payloads.append(self._render(facts, scan_id, scene, has_python))
        return payloads

    def _render(
        self,
        facts: ComponentFacts,
        scan_id: str,
        scene: str,
        has_python: bool,
    ) -> dict[str, Any]:
        component_id = stable_id("component", facts.component_type, facts.name)

        # Deterministic evidence ids (ev_001 ...) in a fixed order covering both
        # capability evidence and parser-provided boundary evidence.
        evidence_by_index: dict[tuple[str, int, int], str] = {}
        counter = 0
        for cap_index, cap in enumerate(facts.capabilities):
            for ev_index in range(len(cap.evidence)):
                counter += 1
                evidence_by_index[("cap", cap_index, ev_index)] = f"ev_{counter:03d}"
        for bnd_index, boundary in enumerate(facts.boundaries):
            for ev_index in range(len(boundary.evidence)):
                counter += 1
                evidence_by_index[("bnd", bnd_index, ev_index)] = f"ev_{counter:03d}"

        capability_rows: list[dict[str, Any]] = []
        for cap_index, cap in enumerate(facts.capabilities):
            refs = [evidence_by_index[("cap", cap_index, j)] for j in range(len(cap.evidence))]
            capability_rows.append(
                {
                    "capability_id": stable_id("cap", component_id, cap.capability),
                    "capability": cap.capability,
                    "action": cap.action,
                    "resource": cap.resource,
                    "impact": int(cap.impact),
                    "confidence": float(cap.confidence),
                    "rule_id": cap.rule_id,
                    "controls": list(cap.controls),
                    "evidence_refs": refs,
                }
            )

        cap_evidence_ids: list[tuple[int, int, str]] = [
            (cap_index, j, evidence_by_index[("cap", cap_index, j)])
            for cap_index, cap in enumerate(facts.capabilities)
            for j in range(len(cap.evidence))
        ]

        evidence_rows: list[dict[str, Any]] = []
        for cap_index, cap in enumerate(facts.capabilities):
            for ev_index, ev in enumerate(cap.evidence):
                evidence_rows.append(
                    {
                        "evidence_id": evidence_by_index[("cap", cap_index, ev_index)],
                        "source_span": _span_dict(ev.span),
                        "masked_excerpt": ev.excerpt,
                        "details": dict(ev.details),
                    }
                )
        for bnd_index, boundary in enumerate(facts.boundaries):
            for ev_index, ev in enumerate(boundary.evidence):
                evidence_rows.append(
                    {
                        "evidence_id": evidence_by_index[("bnd", bnd_index, ev_index)],
                        "source_span": _span_dict(ev.span),
                        "masked_excerpt": ev.excerpt,
                        "details": dict(ev.details),
                    }
                )
        evidence_ids_resolved = {ev["evidence_id"] for ev in evidence_rows}

        if facts.boundaries:
            boundaries: list[dict[str, Any]] = []
            for bnd_index, boundary in enumerate(facts.boundaries):
                if boundary.evidence:
                    refs = [evidence_by_index[("bnd", bnd_index, j)] for j in range(len(boundary.evidence))]
                else:
                    # Share the component's capability evidence when the parser
                    # could not attach a dedicated file-scope fact, so the
                    # boundary still links to resolvable evidence.
                    refs = list(dict.fromkeys(eid for _c, _j, eid in cap_evidence_ids))
                boundaries.append(
                    {
                        "boundary_id": stable_id(
                            "bnd", component_id, boundary.execution_mode, str(bnd_index)
                        ),
                        "data_scope": [s for s in boundary.data_scope],
                        "network_target": [t for t in boundary.network_target],
                        "credential_use": bool(boundary.credential_use),
                        "execution_mode": boundary.execution_mode,
                        "evidence_refs": refs,
                    }
                )
        else:
            boundaries = _aggregate_boundaries(facts.capabilities, component_id, cap_evidence_ids)

        for boundary in boundaries:
            boundary["evidence_refs"] = [
                ref for ref in boundary["evidence_refs"] if ref in evidence_ids_resolved
            ]

        purpose_spans = [
            _span_dict(span)
            for span in facts.purpose_spans
        ]

        return {
            "schema_version": SCHEMA_VERSION,
            "scan_id": scan_id,
            "scene": scene,
            "component": {
                "component_id": component_id,
                "component_type": facts.component_type,
                "name": facts.name,
                "declared_purpose": facts.declared_purpose,
                "source_spans": purpose_spans,
                "extraction_status": facts.extraction_status,
                "extraction_reasons": list(facts.extraction_reasons),
            },
            "capabilities": capability_rows,
            "boundaries": boundaries,
            "evidence": evidence_rows,
            "parser": {
                "status": _parser_status(facts, has_python),
                "version": PARSER_VERSION,
                "warnings": _stable_warnings(facts),
            },
        }
