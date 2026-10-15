"""Evidence-constrained V1 baselines. The output is a relation, not a safety verdict.

This is a provisional adapter for Member B's future normalized JSON. Member A
must freeze the public contract before wiring it into ScanEngine or the API.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping

from ..analysis import ContextRiskScorer
from ..models import CapabilityEvidence, Framework, SourceSpan, ToolSpec

Scene = Literal["install_precheck", "release_precheck"]
Relation = Literal["justified", "needs_review", "inconsistent", "insufficient_evidence"]
Method = Literal["rule", "lexical"]
SCENES = {"install_precheck", "release_precheck"}


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    path: str
    start_line: int
    end_line: int

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any]) -> "EvidenceRef":
        path = str(item.get("path", "")).replace("\\", "/")
        parts = PurePosixPath(path).parts
        if not path or path.startswith("/") or ":" in path or ".." in parts:
            raise ValueError("evidence path must be project-relative")
        start, end = int(item.get("start_line", 0)), int(item.get("end_line", 0))
        if start < 1 or end < start:
            raise ValueError("evidence line range is invalid")
        return cls(path, start, end)


@dataclass(frozen=True, slots=True)
class CapabilityFact:
    capability: str
    action: str
    resource: str
    impact: int
    evidence: tuple[EvidenceRef, ...]
    confidence: float
    rule_id: str

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any]) -> "CapabilityFact":
        impact, confidence = int(item.get("impact", 0)), float(item.get("confidence", 0))
        if not 1 <= impact <= 5 or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("capability impact/confidence is out of range")
        return cls(
            str(item.get("capability", "")), str(item.get("action", "")),
            str(item.get("resource", "")), impact,
            tuple(EvidenceRef.from_mapping(row) for row in item.get("evidence", [])),
            confidence, str(item.get("rule_id", "")),
        )


@dataclass(frozen=True, slots=True)
class ComponentContext:
    scene: Scene
    component_type: str
    name: str
    declared_purpose: str
    extraction_status: str
    capabilities: tuple[CapabilityFact, ...]
    boundary: Mapping[str, Any]
    controls: tuple[str, ...]

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any]) -> "ComponentContext":
        scene = str(item.get("scene", ""))
        if scene not in SCENES:
            raise ValueError("scene must be install_precheck or release_precheck")
        manifest = item.get("component") or {}
        if not isinstance(manifest, Mapping):
            raise ValueError("component must be an object")
        capabilities = item.get("capabilities") or []
        if not isinstance(capabilities, list):
            raise ValueError("capabilities must be an array")
        boundary = item.get("boundary") or {}
        if not isinstance(boundary, Mapping):
            raise ValueError("boundary must be an object")
        return cls(
            scene, str(manifest.get("component_type", "")),
            str(manifest.get("name", "")), str(manifest.get("declared_purpose", "")),
            str(manifest.get("extraction_status", "unresolved")),
            tuple(CapabilityFact.from_mapping(row) for row in capabilities),
            boundary, tuple(str(control) for control in item.get("controls", [])),
        )


@dataclass(frozen=True, slots=True)
class Assessment:
    relation: Relation
    score: float
    reasons: tuple[str, ...]
    uncertainty: tuple[str, ...]
    evidence_refs: tuple[EvidenceRef, ...]
    model: str
    model_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _lexical_similarity(context: ComponentContext) -> float:
    capabilities = [
        CapabilityEvidence(
            fact.capability, fact.impact,
            SourceSpan(fact.evidence[0].path, fact.evidence[0].start_line, fact.evidence[0].end_line),
            fact.action or fact.capability, "Extracted static capability", fact.rule_id,
        )
        for fact in context.capabilities if fact.evidence
    ]
    tool = ToolSpec(
        id="v1-component", framework=Framework.GENERIC, name=context.name,
        description=" ".join(f"{fact.capability} {fact.action} {fact.resource}" for fact in context.capabilities),
        parameters=[], capabilities=capabilities, controls=list(context.controls),
        extraction_status=context.extraction_status,
    )
    return ContextRiskScorer()._semantic_overlap(context.declared_purpose, tool)


def assess(context: ComponentContext, *, method: Method = "rule") -> Assessment:
    """Assess supplied static facts only; never infer capabilities or claim safety."""
    if method not in {"rule", "lexical"}:
        raise ValueError("method must be rule or lexical")
    name, version = (("rule-baseline-v1", "1") if method == "rule"
                     else ("existing-lexical-context-baseline", "1"))
    refs = tuple(dict.fromkeys(ref for fact in context.capabilities for ref in fact.evidence))
    uncertainty = []
    if not context.declared_purpose.strip():
        uncertainty.append("Declared purpose is missing")
    if not context.capabilities:
        uncertainty.append("No capability facts were extracted")
    if not refs or any(not fact.evidence for fact in context.capabilities):
        uncertainty.append("One or more capability facts lack source evidence")
    if context.extraction_status != "resolved":
        uncertainty.append(f"Extraction status is {context.extraction_status}")
    if uncertainty:
        return Assessment("insufficient_evidence", 0.0,
                          ("Available static evidence cannot support a relation judgement",),
                          tuple(uncertainty), refs, name, version)

    impact = max(fact.impact for fact in context.capabilities)
    broad = bool(context.boundary.get("credential_use")) or any(
        str(context.boundary.get(key, "")).lower() in {"any", "all", "*", "environment", "unrestricted"}
        for key in ("data_scope", "network_target")
    )
    reasons = [f"Highest extracted capability impact is {impact}/5"]
    if method == "rule":
        # A rule-only baseline cannot prove task necessity from a declaration.
        relation: Relation = "needs_review" if impact >= 4 or broad or not context.controls else "justified"
        reasons.append("Broad or high-impact capability needs human review" if relation == "needs_review"
                       else "Low-impact capability has an explicit static control")
        return Assessment(relation, 0.65 if relation == "needs_review" else 0.55,
                          tuple(reasons), ("Rule-only baseline does not assess task meaning",), refs,
                          name, version)

    similarity = _lexical_similarity(context)
    reasons.append(f"Existing lexical task/capability overlap is {similarity:.2f}")
    if impact >= 4 and similarity < 0.16:
        relation = "inconsistent"
    elif similarity >= 0.35 and not (impact >= 4 and broad):
        relation = "justified"
    else:
        relation = "needs_review"
    if broad:
        reasons.append("Capability reaches a broad or credential-related boundary")
    support = similarity if relation == "justified" else 1 - similarity if relation == "inconsistent" else 0.5
    return Assessment(relation, round(min(1.0, max(0.0, support)), 4), tuple(reasons),
                      ("Lexical overlap does not establish semantic necessity",), refs, name, version)
