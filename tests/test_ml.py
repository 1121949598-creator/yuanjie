from pathlib import Path

import joblib
import yaml

from yuanjian_agent.ml import evaluate, train_model


DATASET = Path(__file__).parents[1] / "experiments" / "dataset.example.jsonl"


def test_train_and_repository_grouped_evaluation(tmp_path: Path):
    model = tmp_path / "model.joblib"
    training = train_model(DATASET, model, seed=42)
    assert training["sample_count"] == 16
    assert joblib.load(model)["model_name"] == "tfidf-logistic-regression-v1"

    config = tmp_path / "experiment.yml"
    output = tmp_path / "metrics.json"
    config.write_text(
        yaml.safe_dump(
            {"dataset": str(DATASET), "seed": 42, "test_size": 0.25, "output": str(output)}
        ),
        encoding="utf-8",
    )
    report = evaluate(config)
    assert report["split"] == "repository-grouped"
    assert set(report["train_repositories"]).isdisjoint(report["test_repositories"])
    assert output.exists()
