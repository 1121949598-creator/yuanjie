"""Public EvidenceConstrainedScorer implementing A's frozen contract 1.0."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .contract import IntentCapabilityInput, IntentCapabilityResult, RELATIONS
from .semantic import LocalSentenceTransformerEncoder, SentenceEncoder, _cosine

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
MODEL_SHA256 = "eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b"
INCONSISTENT_BELOW = 0.30
JUSTIFIED_AT_LEAST = 0.55
MIN_FACT_CONFIDENCE = 0.60
_SENSITIVE = {"credential_access", "credential_read", "shell_execute", "shell_execution",
              "persistence", "privilege_escalation", "elevation"}
_BROAD = {"any", "all", "*", "environment", "unrestricted", "local_operating_system",
          "process_environment_credentials", "system", "system_directory"}


def _reason(code, message, refs):
    return {"code": code, "message": message, "evidence_refs": list(refs)}


def _metadata(used, name, version):
    return {
        "name": name if used else "deterministic-context-baseline",
        "version": version if used else "1.0", "used": used,
        "provider": "local" if used else "builtin",
        "rules_version": "1.0", "feature_version": "1.0",
        "thresholds": {"inconsistent_below": INCONSISTENT_BELOW,
                       "justified_at_least": JUSTIFIED_AT_LEAST,
                       "min_fact_confidence": MIN_FACT_CONFIDENCE},
    }


class EvidenceConstrainedScorer:
    """Pure algorithm entry point. No source reads, Web, DB, or subprocess calls.

    Supply a local encoder or use from_local_model(). With no encoder, return
    an explicit rules fallback (partial, model.used=false).
    """

    def __init__(self, *, encoder: SentenceEncoder | None = None,
                 model_name=MODEL_NAME, model_version=MODEL_REVISION):
        self.encoder = encoder
        self.model_name = model_name
        self.model_version = model_version

    @classmethod
    def from_local_model(cls, model_dir: Path) -> "EvidenceConstrainedScorer":
        return cls(encoder=LocalSentenceTransformerEncoder(Path(model_dir), expected_sha256=MODEL_SHA256))

    def score(self, input: IntentCapabilityInput | Mapping) -> IntentCapabilityResult:
        validated = IntentCapabilityInput.from_mapping(
            input.payload if isinstance(input, IntentCapabilityInput) else input)
        data = validated.payload
        component, parser = data["component"], data["parser"]
        warnings = []
        known = {e["evidence_id"] for e in data["evidence"]}
        boundaries = []
        for boundary in data["boundaries"]:
            if not boundary["evidence_refs"] or not set(boundary["evidence_refs"]) <= known:
                warnings.append("boundary_evidence_unavailable")
            else:
                boundaries.append(boundary)
        if parser["status"] != "success" or component["extraction_status"] != "resolved":
            warnings.append("parser_coverage_incomplete")
        if parser["warnings"]:
            # Never relay the parser's raw warnings across this boundary.
            warnings.append("parser_reported_coverage_warning")
        if not data["capabilities"]:
            warnings.append("no_capabilities_does_not_mean_passed")
        if not known:
            warnings.append("evidence_unavailable")
        assessments = []
        for capability in data["capabilities"]:
            refs = list(dict.fromkeys(capability["evidence_refs"]))
            if not refs or not set(refs) <= known:
                warnings.append("capability_evidence_unavailable")
                continue
            related = [b for b in boundaries if set(refs).intersection(b["evidence_refs"])]
            # Preserve capability-level control ownership; don't pool controls.
            try:
                assessment, item_warnings = self._assess(data, capability, refs, related)
            except Exception:
                # A failed capability cannot discard the other capabilities.
                assessment = self._insufficient(capability, refs, "assessment_unavailable")
                item_warnings = ["assessment_unavailable"]
            assessments.append(assessment)
            warnings.extend(item_warnings)
        status = "partial" if warnings else "success"
        if parser["status"] in {"unavailable", "failed"}:
            status = parser["status"]
        counts = {relation: sum(a["relation"] == relation for a in assessments) for relation in RELATIONS}
        result = IntentCapabilityResult({
            "schema_version": "1.0", "component_id": component["component_id"],
            "scene": data["scene"], "status": status, "assessments": assessments,
            "summary": {"total": len(assessments), "by_relation": counts,
                        "max_score": max((a["score"] for a in assessments), default=0.0)},
            "warnings": list(dict.fromkeys(warnings)),
        })
        result.validate(validated)
        return result

    def _base(self, cap, refs, relation, score, reasons, uncertainty, used):
        return {
            "assessment_id": "asm_" + cap["capability_id"],
            "capability_id": cap["capability_id"], "relation": relation,
            "score": round(score, 4), "reasons": reasons, "uncertainty": uncertainty,
            "evidence_refs": refs,
            "model": _metadata(used, self.model_name, self.model_version),
        }

    def _insufficient(self, cap, refs, code):
        return self._base(cap, refs, "insufficient_evidence", .5,
                          [_reason(code, "现有声明或解析证据不足以判断该能力与用途的关系。", refs)],
                          {"level": "high", "reasons": [code]}, False)

    def _assess(self, data, cap, refs, boundaries):
        component, parser = data["component"], data["parser"]
        if not component["declared_purpose"].strip():
            return self._insufficient(cap, refs, "declared_purpose_unavailable"), ["declared_purpose_unavailable"]
        if component["extraction_status"] == "unresolved" or parser["status"] in {"unavailable", "failed"}:
            return self._insufficient(cap, refs, "parser_coverage_insufficient"), ["parser_coverage_insufficient"]
        if not cap["capability"].strip() or not cap["action"].strip():
            return self._insufficient(cap, refs, "capability_description_unavailable"), ["capability_description_unavailable"]

        incomplete = (component["extraction_status"] != "resolved" or parser["status"] != "success"
                      or bool(parser["warnings"]))
        broad = cap["resource"].lower() in _BROAD or any(
            b["credential_use"] or b["execution_mode"].lower() == "shell"
            or any(scope.lower() in _BROAD for scope in b["data_scope"] + b["network_target"])
            for b in boundaries)
        sensitive = cap["impact"] >= 4 or cap["capability"].lower() in _SENSITIVE
        unknown_scope = (not boundaries or cap["resource"].strip().lower() in {"", "unknown"}
                         or any(not b["data_scope"] or "unknown" in b["data_scope"] + b["network_target"]
                                or b["execution_mode"].lower() == "unknown" for b in boundaries))
        low_confidence = cap["confidence"] < MIN_FACT_CONFIDENCE
        try:
            if self.encoder is None:
                raise RuntimeError()
            # Encode only B's declared purpose and this capability's normalized
            # facts; never masked excerpts, details, raw code or exception text.
            capability_text = "; ".join(
                f"{label}: {cap[key].replace('_', ' ')}"
                for label, key in (("Capability", "capability"), ("Action", "action"), ("Resource", "resource")))
            vectors = self.encoder.encode([component["declared_purpose"], capability_text])
            if len(vectors) != 2:
                raise ValueError()
            similarity = _cosine(vectors[0], vectors[1])
            if similarity is None:
                raise ValueError()
        except Exception:
            return self._base(cap, refs, "needs_review", .7 if sensitive or broad else .5,
                              [_reason("semantic_model_unavailable", "本地语义模型不可用，使用规则基线并保留人工复核。", refs)],
                              {"level": "high", "reasons": ["semantic_model_unavailable"]}, False), ["semantic_model_unavailable"]

        # Read rule 7.2 as low similarity AND (high impact OR sensitive type).
        # A shell/credential capability alone is not proof of inconsistency.
        if similarity < INCONSISTENT_BELOW and (sensitive or broad):
            relation = "inconsistent"
            risk = .75 + .25 * (INCONSISTENT_BELOW - max(0., similarity)) / INCONSISTENT_BELOW
            code, message = "high_impact_capability_not_supported_by_purpose", "该能力与声明用途的语义关联较低，且涉及高影响或敏感边界。"
        elif (similarity >= JUSTIFIED_AT_LEAST and not broad and not unknown_scope
              and not low_confidence and not incomplete and cap["controls"]):
            relation = "justified"
            risk = .29 * (1 - min(1., similarity)) / (1 - JUSTIFIED_AT_LEAST)
            code, message = "purpose_capability_aligned", "该能力与声明用途关联较强，且存在静态范围及控制依据。"
        else:
            relation = "needs_review"
            risk = min(.74, max(.3, .3 + .3 * (1 - max(0., similarity)) + .1 * broad + .04 * sensitive))
            code, message = "purpose_capability_requires_review", "该能力的用途关联、资源范围或控制信息仍需人工确认。"
        reasons = [_reason(code, message, refs),
                   _reason("semantic_similarity", f"本地模型计算的声明—能力余弦相似度为 {similarity:.4f}。", refs)]
        all_refs = list(refs)
        for boundary in boundaries:
            all_refs.extend(boundary["evidence_refs"])
        all_refs = list(dict.fromkeys(all_refs))
        reasons.append(_reason("sensitive_boundary" if broad else "scope_evidence",
                               "边界包含敏感访问或宽泛范围。" if broad else "资源边界按输入中的静态证据解释。", all_refs))
        if cap["controls"]:
            reasons.append(_reason("scope_control_detected", "输入中记录了该能力的静态控制措施。", refs))
        else:
            reasons.append(_reason("static_control_unavailable", "输入未提供该能力的静态控制依据。", refs))
        reasons.append(_reason("install_review" if data["scene"] == "install_precheck" else "release_review",
                               "安装前请确认授权范围及本机资源访问。" if data["scene"] == "install_precheck"
                               else "发布前请由维护者复核工具权限及不必要的能力暴露。", refs))
        uncertainty = []
        if incomplete:
            uncertainty.append("parser_coverage_incomplete")
        if low_confidence:
            uncertainty.append("low_static_fact_confidence")
        if unknown_scope:
            uncertainty.append("resource_boundary_unknown")
        level = "high" if incomplete or low_confidence or unknown_scope else "medium"
        # Similarity is heuristic; do not claim calibrated low uncertainty.
        uncertainty.append("semantic_relation_is_not_a_safety_verdict")
        return self._base(cap, all_refs, relation, risk, reasons,
                          {"level": level, "reasons": uncertainty}, True), []
