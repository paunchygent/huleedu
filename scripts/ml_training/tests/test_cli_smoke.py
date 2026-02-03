from __future__ import annotations

import numpy as np
import pandas as pd
from typer.testing import CliRunner

from scripts.ml_training.essay_scoring.cli import app
from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.dataset import load_ellipse_train_test_dataset
from scripts.ml_training.essay_scoring.feature_store import persist_feature_store
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.splitters import DatasetSplit


def _make_text(word_count: int, *, seed: str) -> str:
    return " ".join(f"{seed}_w{i}" for i in range(word_count))


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Whitebox essay scoring research pipeline" in result.stdout


def test_cli_run_with_reused_feature_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PYTHONWARNINGS", "ignore")

    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    train_rows = []
    for i in range(40):
        label = "1.0" if i % 2 == 0 else "2.0"
        train_rows.append(
            {
                "full_text": _make_text(250, seed=f"train{i}"),
                "prompt": f"P{i % 2}",
                "Overall": label,
            }
        )

    test_rows = []
    for i in range(8):
        label = "1.0" if i % 2 == 0 else "2.0"
        test_rows.append(
            {
                "full_text": _make_text(250, seed=f"test{i}"),
                "prompt": f"P{i % 2}",
                "Overall": label,
            }
        )

    pd.DataFrame(train_rows).to_csv(train_path, index=False)
    pd.DataFrame(test_rows).to_csv(test_path, index=False)

    config = ExperimentConfig(
        dataset_kind=DatasetKind.ELLIPSE,
        ellipse_train_path=train_path,
        ellipse_test_path=test_path,
        feature_set=FeatureSet.HANDCRAFTED,
        output={"base_dir": tmp_path / "runs", "run_name": "cli"},  # type: ignore[arg-type]
        training={
            "num_boost_round": 10,
            "early_stopping_rounds": 3,
            "params": {
                "objective": "reg:squarederror",
                "max_depth": 3,
                "learning_rate": 0.3,
                "min_child_weight": 1,
                "reg_lambda": 1.0,
                "colsample_bytree": 1.0,
                "subsample": 1.0,
            },
        },
    )

    pre_split = load_ellipse_train_test_dataset(train_path, test_path, excluded_prompts=set())
    split = DatasetSplit(
        train=list(pre_split.train_records[:20]),
        val=list(pre_split.train_records[20:30]),
        test=list(pre_split.test_records[:8]),
    )

    rng = np.random.default_rng(0)
    feature_names = ["f0", "f1", "f2"]
    train_features = FeatureMatrix(
        matrix=rng.normal(size=(len(split.train), 3)).astype(np.float32),
        feature_names=feature_names,
    )
    val_features = FeatureMatrix(
        matrix=rng.normal(size=(len(split.val), 3)).astype(np.float32),
        feature_names=feature_names,
    )
    test_features = FeatureMatrix(
        matrix=rng.normal(size=(len(split.test), 3)).astype(np.float32),
        feature_names=feature_names,
    )

    store_run_dir = tmp_path / "store_run"
    persist_feature_store(
        run_dir=store_run_dir,
        config=config,
        dataset=pre_split.dataset,
        split=split,
        feature_set=FeatureSet.HANDCRAFTED,
        spacy_model="en_core_web_sm",
        train_features=train_features,
        val_features=val_features,
        test_features=test_features,
    )

    config_path = tmp_path / "config.json"
    config_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "run",
            "--config-path",
            str(config_path),
            "--reuse-feature-store-dir",
            str(store_run_dir),
            "--run-name",
            "cli_run",
            "--skip-shap",
            "--skip-grade-scale-report",
        ],
    )
    assert result.exit_code == 0
    assert "Run complete:" in result.stdout
