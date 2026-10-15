from __future__ import annotations

import importlib.resources
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import CapabilityEvidence, SourceSpan, ToolSpec


TOKEN_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]+|[\u4e00-\u9fff]{1,4}")


def tokenize(text: str) -> set[str]:
    normalized = text.lower().replace("_", " ").replace("-", " ")
    return {token.lower() for token in TOKEN_PATTERN.findall(normalized) if len(token) > 1}


def load_tool_rules(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    resource = importlib.resources.files("yuanjian_agent.default_rules").joinpath("tool_capabilities.yml")
    return yaml.safe_load(resource.read_text(encoding="utf-8"))


class CapabilityAnalyzer:
    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        self.rules = rules or load_tool_rules()

    def analyze(self, tool: ToolSpec) -> ToolSpec:
        haystack = " ".join(
            [tool.name, tool.description, " ".join(tool.body_calls), str(tool.metadata.get("body_source", ""))]
        ).lower()
        semantic_text = f"{tool.name} {tool.description}".lower()
        span = tool.source_spans[0] if tool.source_spans else SourceSpan("unknown", 1, 1)
        capabilities: list[CapabilityEvidence] = []
        normalized_calls = [call.lower().split(":", 1)[0] for call in tool.body_calls]
        rules_version = str(self.rules.get("version", "unknown"))
        for rule in self.rules.get("capabilities", []):
            matches: list[str] = []
            for pattern in rule.get("call_patterns", []):
                pattern_lower = pattern.lower()
                suffix = pattern_lower.rsplit(".", 1)[-1]
                if any(
                    call == pattern_lower
                    or call.endswith(f".{pattern_lower}")
                    or ("." not in call and call == suffix)
                    for call in normalized_calls
                ):
                    matches.append(pattern)
            for keyword in rule.get("name_keywords", []):
                normalized_keyword = str(keyword).lower()
                if re.search(rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])", semantic_text):
                    matches.append(keyword)
            if rule["id"] == "file_write" and re.search(r"\bopen\s*\([^\n]*(?:['\"]w|mode\s*=\s*['\"]w)", haystack):
                matches.append("open(write mode)")
            if matches:
                capabilities.append(
                    CapabilityEvidence(
                        capability=rule["id"],
                        impact=int(rule["impact"]),
                        source_span=span,
                        symbol=matches[0],
                        rationale=f"Matched capability evidence: {', '.join(sorted(set(matches))[:4])}",
                        rule_id=f"agent.capability.{rule['id']}",
                        rule_version=rules_version,
                    )
                )
        controls: list[str] = []
        for control, patterns in self.rules.get("controls", {}).items():
            if any(str(pattern).lower() in haystack for pattern in patterns):
                controls.append(control)
        tool.capabilities = capabilities
        tool.controls = sorted(set(controls))
        tool.metadata["capability_rules_version"] = rules_version
        return tool


@dataclass(slots=True)
class ExposureScore:
    probability: float
    impact: int
    score: float
    similarity: float
    reasons: list[str]
    model: str
    uncertainty_reasons: list[str]


class ContextRiskScorer:
    """CPU-safe task/tool scorer with optional scikit-learn model support."""

    def __init__(self, model_bundle: dict[str, Any] | None = None, rules: dict[str, Any] | None = None) -> None:
        self.model_bundle = model_bundle
        self.rules = rules or load_tool_rules()
        self.capability_rules = {item["id"]: item for item in self.rules.get("capabilities", [])}

    def score(self, task_text: str, tool: ToolSpec) -> ExposureScore:
        impact = max((item.impact for item in tool.capabilities), default=1)
        similarity = self._semantic_overlap(task_text, tool)
        numeric = {
            "impact": impact / 5.0,
            "similarity": similarity,
            "control_count": min(len(tool.controls), 4) / 4.0,
            "description_missing": float(not tool.description.strip()),
            "task_missing": float(not task_text.strip()),
            "extraction_unresolved": float(tool.extraction_status != "resolved"),
        }
        if self.model_bundle:
            text = training_text(task_text, tool)
            vectorizer = self.model_bundle["vectorizer"]
            classifier = self.model_bundle["classifier"]
            import numpy as np
            from scipy.sparse import csr_matrix, hstack

            text_features = vectorizer.transform([text])
            numeric_features = csr_matrix(
                np.array([[numeric[key] for key in self.model_bundle["numeric_keys"]]], dtype=float)
            )
            probability = float(classifier.predict_proba(hstack([text_features, numeric_features]))[0, 1])
            model_name = str(self.model_bundle.get("model_name", "logistic-regression"))
        else:
            controls = min(len(tool.controls), 3)
            missing_description = 0.45 if not tool.description.strip() else 0.0
            missing_task = 0.55 if not task_text.strip() else 0.0
            unresolved = 0.35 if tool.extraction_status != "resolved" else 0.0
            logit = (
                -0.7 + 2.3 * (impact / 5.0) - 4.2 * similarity - 0.45 * controls
                + missing_description + missing_task + unresolved
            )
            probability = 1.0 / (1.0 + math.exp(-logit))
            model_name = "deterministic-context-baseline"
        reasons = [f"Maximum capability impact is {impact}/5", f"Task-tool necessity signal is {similarity:.2f}"]
        if tool.controls:
            reasons.append(f"Detected controls: {', '.join(tool.controls)}")
        else:
            reasons.append("No explicit static safety control was detected")
        if not tool.description.strip():
            reasons.append("Tool description is missing, which increases uncertainty")
        if tool.extraction_status != "resolved":
            reasons.append(f"Extraction status is {tool.extraction_status}")
        uncertainty_reasons: list[str] = []
        if not task_text.strip():
            uncertainty_reasons.append("Declared Agent task is missing")
        if not tool.description.strip():
            uncertainty_reasons.append("Tool description is missing")
        if tool.extraction_status != "resolved":
            uncertainty_reasons.extend(tool.extraction_reasons or [f"Tool extraction is {tool.extraction_status}"])
        return ExposureScore(
            probability=round(probability, 4),
            impact=impact,
            score=round(probability * impact, 4),
            similarity=round(similarity, 4),
            reasons=reasons,
            model=model_name,
            uncertainty_reasons=uncertainty_reasons,
        )

    def _semantic_overlap(self, task_text: str, tool: ToolSpec) -> float:
        task_tokens = tokenize(task_text)
        tool_tokens = tokenize(f"{tool.name} {tool.description}")
        if not task_tokens or not tool_tokens:
            lexical = 0.0
        else:
            lexical = len(task_tokens & tool_tokens) / math.sqrt(len(task_tokens) * len(tool_tokens))
        domain_matches = 0
        capability_count = max(len(tool.capabilities), 1)
        task_lower = task_text.lower()
        for capability in tool.capabilities:
            keywords = self.capability_rules.get(capability.capability, {}).get("task_keywords", [])
            if any(str(keyword).lower() in task_lower for keyword in keywords):
                domain_matches += 1
        domain = domain_matches / capability_count
        return min(1.0, 0.55 * lexical + 0.45 * domain)


def training_text(task_text: str, tool: ToolSpec) -> str:
    return (
        f"TASK {task_text}\nTOOL {tool.name} {tool.description}\n"
        f"CAPABILITIES {' '.join(item.capability for item in tool.capabilities)}\n"
        f"CONTROLS {' '.join(tool.controls)}"
    )
