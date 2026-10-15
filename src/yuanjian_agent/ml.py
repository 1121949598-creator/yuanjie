from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import yaml
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit

from .analysis import ContextRiskScorer, training_text
from .models import CapabilityEvidence, Framework, SourceSpan, ToolSpec


NUMERIC_KEYS = ["impact", "similarity", "control_count", "description_missing"]


@dataclass(slots=True)
class LabeledPair:
    repository_id: str
    task_text: str
    tool: ToolSpec
    label: int


def load_pairs(path: Path) -> list[LabeledPair]:
    pairs: list[LabeledPair] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSONL at line {index}: {error}") from error
        label_value = row.get("label")
        if label_value in {"uncertain", None}:
            continue
        label = int(label_value in {1, True, "1", "over_exposed", "yes"})
        span = SourceSpan(str(row.get("source_path", "dataset.jsonl")), index, index)
        capabilities = [
            CapabilityEvidence(
                capability=str(value.get("name")) if isinstance(value, dict) else str(value),
                impact=int(value.get("impact", 3)) if isinstance(value, dict) else 3,
                source_span=span,
                symbol="dataset",
                rationale="Annotated capability",
            )
            for value in row.get("capabilities", [])
        ]
        try:
            framework = Framework(row.get("framework", "generic"))
        except ValueError:
            framework = Framework.GENERIC
        tool = ToolSpec(
            id=f"dataset_tool_{index}", framework=framework,
            name=str(row.get("tool_name", "unnamed_tool")),
            description=str(row.get("tool_description", "")),
            parameters=[str(value) for value in row.get("parameters", [])],
            capabilities=capabilities,
            controls=[str(value) for value in row.get("controls", [])],
        )
        pairs.append(LabeledPair(str(row.get("repository_id", f"row-{index}")), str(row.get("task_text", "")), tool, label))
    if len(pairs) < 4 or len({pair.label for pair in pairs}) < 2:
        raise ValueError("Dataset must contain at least four certain samples and both labels")
    return pairs


def _numeric(pair: LabeledPair, scorer: ContextRiskScorer) -> list[float]:
    similarity = scorer._semantic_overlap(pair.task_text, pair.tool)
    impact = max((cap.impact for cap in pair.tool.capabilities), default=1)
    return [impact / 5.0, similarity, min(len(pair.tool.controls), 4) / 4.0, float(not pair.tool.description.strip())]


def train_model(dataset: Path, output: Path, seed: int = 42) -> dict[str, Any]:
    pairs = load_pairs(dataset)
    scorer = ContextRiskScorer()
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=20_000)
    text_features = vectorizer.fit_transform([training_text(pair.task_text, pair.tool) for pair in pairs])
    numeric = csr_matrix(np.asarray([_numeric(pair, scorer) for pair in pairs], dtype=float))
    classifier = LogisticRegression(class_weight="balanced", random_state=seed, max_iter=2_000)
    classifier.fit(hstack([text_features, numeric]), np.asarray([pair.label for pair in pairs]))
    bundle = {"vectorizer": vectorizer, "classifier": classifier, "numeric_keys": NUMERIC_KEYS,
              "model_name": "tfidf-logistic-regression-v1", "seed": seed, "sample_count": len(pairs)}
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output)
    return {"output": str(output), "sample_count": len(pairs), "repositories": len({p.repository_id for p in pairs})}


def evaluate(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    dataset_value = Path(config["dataset"])
    dataset = dataset_value if dataset_value.is_absolute() else (config_path.parent / dataset_value).resolve()
    seed, test_size = int(config.get("seed", 42)), float(config.get("test_size", 0.3))
    pairs = load_pairs(dataset)
    groups, labels = np.asarray([p.repository_id for p in pairs]), np.asarray([p.label for p in pairs])
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, test_idx = next(splitter.split(np.arange(len(pairs)), labels, groups))
    train_pairs, test_pairs = [pairs[i] for i in train_idx], [pairs[i] for i in test_idx]
    if len({p.label for p in train_pairs}) < 2 or len({p.label for p in test_pairs}) < 2:
        raise ValueError("Repository split must contain both labels in train and test")
    scorer = ContextRiskScorer()
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=20_000)
    train_text = vectorizer.fit_transform([training_text(p.task_text, p.tool) for p in train_pairs])
    test_text = vectorizer.transform([training_text(p.task_text, p.tool) for p in test_pairs])
    x_train = hstack([train_text, csr_matrix(np.asarray([_numeric(p, scorer) for p in train_pairs]))])
    x_test = hstack([test_text, csr_matrix(np.asarray([_numeric(p, scorer) for p in test_pairs]))])
    classifier = LogisticRegression(class_weight="balanced", random_state=seed, max_iter=2_000).fit(x_train, [p.label for p in train_pairs])
    probabilities = classifier.predict_proba(x_test)[:, 1]
    truth = np.asarray([p.label for p in test_pairs])
    predictions = (probabilities >= float(config.get("threshold", 0.5))).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(truth, predictions, average="binary", zero_division=0)
    report = {"seed": seed, "dataset": str(dataset), "split": "repository-grouped",
              "train_samples": len(train_pairs), "test_samples": len(test_pairs),
              "train_repositories": sorted({p.repository_id for p in train_pairs}),
              "test_repositories": sorted({p.repository_id for p in test_pairs}),
              "metrics": {"precision": round(float(precision), 4), "recall": round(float(recall), 4),
                          "f1": round(float(f1), 4), "pr_auc": round(float(average_precision_score(truth, probabilities)), 4),
                          "confusion_matrix": confusion_matrix(truth, predictions, labels=[0, 1]).tolist()}}
    if config.get("output"):
        output_value = Path(config["output"])
        output = output_value if output_value.is_absolute() else (config_path.parent / output_value).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
