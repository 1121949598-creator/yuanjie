"""Small-sample, repository-grouped engineering evaluation for V1 baselines."""

from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit

from .scoring import ComponentContext, assess
from .semantic import SentenceEncoder, assess_semantic

LABELS = ("justified", "needs_review", "inconsistent", "insufficient_evidence")


def evaluate_dataset(dataset: Path, *, seed: int = 42, test_size: float = 0.25,
                     encoder: SentenceEncoder | None = None,
                     model_name: str = "", model_version: str = "") -> dict:
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) < 12 or len({row["repository_id"] for row in rows}) < 3:
        raise ValueError("need >=12 labeled rows from >=3 repositories")
    if any(row["gold_relation"] not in LABELS for row in rows):
        raise ValueError("unknown gold_relation")
    groups = [row["repository_id"] for row in rows]
    split = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_indices, test_indices = next(split.split(rows, groups=groups))
    train_repos = sorted({groups[i] for i in train_indices})
    test_repos = sorted({groups[i] for i in test_indices})
    result = {
        "synthetic": all(row.get("synthetic") is True for row in rows),
        "purpose": "small-sample engineering check, not ecosystem accuracy",
        "seed": seed, "split": "repository-grouped", "train_samples": len(train_indices),
        "test_samples": len(test_indices), "train_repositories": train_repos,
        "test_repositories": test_repos, "labels": list(LABELS), "methods": {},
    }
    truth = [rows[i]["gold_relation"] for i in test_indices]
    for method in (("rule", "lexical", "semantic") if encoder is not None else ("rule", "lexical")):
        start = perf_counter()
        predicted = [
            (assess_semantic(ComponentContext.from_mapping(rows[i]["context"]),
                             encoder=encoder, model_name=model_name, model_version=model_version)
             if method == "semantic" else
             assess(ComponentContext.from_mapping(rows[i]["context"]), method=method)).relation
            for i in test_indices
        ]
        elapsed = (perf_counter() - start) / len(test_indices)
        precision, recall, f1, support = precision_recall_fscore_support(
            truth, predicted, labels=LABELS, zero_division=0)
        matrix = confusion_matrix(truth, predicted, labels=LABELS).tolist()
        f1_macro = float(sum(f1) / len(LABELS))
        inconsistent_index = LABELS.index("inconsistent")
        fp = sum(matrix[row][inconsistent_index] for row in range(len(LABELS)) if row != inconsistent_index)
        tn = sum(matrix[row][col] for row in range(len(LABELS)) for col in range(len(LABELS))
                 if row != inconsistent_index and col != inconsistent_index)
        result["methods"][method] = {
            "macro_f1": round(f1_macro, 4),
            "inconsistent_fpr": round(fp / (fp + tn), 4) if fp + tn else None,
            "class_metrics": {label: {"precision": round(float(precision[j]), 4),
                                      "recall": round(float(recall[j]), 4),
                                      "f1": round(float(f1[j]), 4), "support": int(support[j])}
                              for j, label in enumerate(LABELS)},
            "confusion_matrix": matrix, "mean_seconds_per_component": round(elapsed, 6),
            "failures": [{"repository_id": groups[i], "gold": gold, "predicted": guess}
                         for i, gold, guess in zip(test_indices, truth, predicted) if gold != guess],
        }
    return result
