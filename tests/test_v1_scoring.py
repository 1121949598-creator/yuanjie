from __future__ import annotations

import json
from pathlib import Path

import pytest
import numpy as np

from yuanjian_agent.component_security.scoring import ComponentContext, assess
from yuanjian_agent.component_security.evaluation import evaluate_dataset
from yuanjian_agent.component_security.semantic import assess_semantic


def sample_context(**changes):
    payload = {
        "scene": "install_precheck",
        "component": {
            "component_type": "skill",
            "name": "文档整理助手",
            "declared_purpose": "整理本地 Markdown 文档并生成目录",
            "extraction_status": "resolved",
        },
        "capabilities": [{
            "capability": "file_read",
            "action": "read",
            "resource": "docs/*.md",
            "impact": 2,
            "evidence": [{"path": "scripts/index.py", "start_line": 12, "end_line": 12}],
            "confidence": 0.9,
            "rule_id": "skill.file_read",
        }],
        "boundary": {
            "data_scope": "docs/*.md", "network_target": None,
            "credential_use": False, "execution_mode": "static-declared",
        },
        "controls": ["path_allowlist"],
    }
    payload.update(changes)
    return payload


@pytest.mark.parametrize("method", ["rule", "lexical"])
def test_missing_declaration_or_evidence_never_justified(method):
    no_purpose = sample_context()
    no_purpose["component"]["declared_purpose"] = ""
    result = assess(ComponentContext.from_mapping(no_purpose), method=method)
    assert result.relation == "insufficient_evidence"
    assert result.score == 0
    assert result.uncertainty

    no_evidence = sample_context()
    no_evidence["capabilities"][0]["evidence"] = []
    result = assess(ComponentContext.from_mapping(no_evidence), method=method)
    assert result.relation == "insufficient_evidence"
    assert result.evidence_refs == ()


def test_lexical_result_uses_static_evidence_and_never_calls_it_safe():
    result = assess(ComponentContext.from_mapping(sample_context()), method="lexical")
    assert result.relation in {"justified", "needs_review", "inconsistent"}
    assert 0 <= result.score <= 1
    assert result.model == "existing-lexical-context-baseline"
    assert result.evidence_refs[0].path == "scripts/index.py"
    assert result.evidence_refs[0].start_line == 12
    assert all("safe" not in reason.lower() for reason in result.reasons)


def test_rule_baseline_flags_broad_credential_access_for_review():
    payload = sample_context()
    payload["capabilities"][0].update({"capability": "credential_read", "impact": 5, "resource": "environment"})
    payload["boundary"].update({"credential_use": True, "data_scope": "environment"})
    payload["controls"] = []
    result = assess(ComponentContext.from_mapping(payload), method="rule")
    assert result.relation == "needs_review"
    assert result.model == "rule-baseline-v1"


def test_invalid_scene_or_unsafe_evidence_path_rejected():
    with pytest.raises(ValueError, match="scene"):
        ComponentContext.from_mapping(sample_context(scene="other"))
    payload = sample_context()
    payload["capabilities"][0]["evidence"][0]["path"] = "../../secret"
    with pytest.raises(ValueError, match="path"):
        ComponentContext.from_mapping(payload)


def test_dataset_evaluation_keeps_repositories_apart(tmp_path: Path):
    rows = []
    for repository_id in ("a", "b", "c", "d"):
        for relation in ("justified", "needs_review", "inconsistent", "insufficient_evidence"):
            rows.append({"repository_id": repository_id, "gold_relation": relation, "synthetic": True,
                         "context": sample_context()})
    dataset = tmp_path / "relations.jsonl"
    dataset.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    report = evaluate_dataset(dataset, seed=42, test_size=0.25)
    assert report["synthetic"] is True
    assert set(report["train_repositories"]).isdisjoint(report["test_repositories"])
    assert report["test_samples"] == 4
    assert set(report["methods"]) == {"rule", "lexical"}
    assert len(report["methods"]["rule"]["confusion_matrix"]) == 4


def test_evaluation_does_not_mislabel_real_rows_as_synthetic(tmp_path: Path):
    rows = [{"repository_id": repo, "gold_relation": relation, "synthetic": False,
             "context": sample_context()}
            for repo in ("a", "b", "c")
            for relation in ("justified", "needs_review", "inconsistent", "insufficient_evidence")]
    dataset = tmp_path / "real.jsonl"
    dataset.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    report = evaluate_dataset(dataset)
    assert report["synthetic"] is False


class _Encoder:
    def encode(self, texts):
        return [[1.0, 0.0] if "Markdown" in text or "file_read" in text
                else [0.0, 1.0] for text in texts]


def test_semantic_uses_supplied_evidence_and_encoder():
    result = assess_semantic(ComponentContext.from_mapping(sample_context()),
                             encoder=_Encoder(), model_name="test-encoder", model_version="fixture")
    assert result.relation == "justified"
    assert result.model == "test-encoder"
    assert result.evidence_refs[0].path == "scripts/index.py"


def test_semantic_fails_closed_without_evidence_or_with_bad_vectors():
    payload = sample_context()
    payload["capabilities"][0]["evidence"] = []
    result = assess_semantic(ComponentContext.from_mapping(payload), encoder=_Encoder(),
                             model_name="test-encoder", model_version="fixture")
    assert result.relation == "insufficient_evidence"

    class BadEncoder:
        def encode(self, texts):
            return [[0, 0] for _ in texts]

    result = assess_semantic(ComponentContext.from_mapping(sample_context()), encoder=BadEncoder(),
                             model_name="test-encoder", model_version="fixture")
    assert result.relation == "insufficient_evidence"

    class CrashingEncoder:
        def encode(self, texts):
            raise RuntimeError("local model unavailable")

    result = assess_semantic(ComponentContext.from_mapping(sample_context()), encoder=CrashingEncoder(),
                             model_name="test-encoder", model_version="fixture")
    assert result.relation == "insufficient_evidence"


def test_semantic_accepts_numpy_vectors_from_real_encoder():
    class NumpyEncoder:
        def encode(self, texts):
            return np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)

    result = assess_semantic(ComponentContext.from_mapping(sample_context()),
                             encoder=NumpyEncoder(), model_name="numpy-fixture", model_version="1")
    assert result.relation == "justified"
