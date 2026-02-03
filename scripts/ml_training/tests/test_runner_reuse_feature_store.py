from __future__ import annotations

import json

import numpy as np
import pandas as pd

from scripts.ml_training.essay_scoring.config import (
    DatasetKind,
    ExperimentConfig,
    FeatureSet,
    OutputConfig,
    TrainingConfig,
)
from scripts.ml_training.essay_scoring.dataset import load_ellipse_train_test_dataset
from scripts.ml_training.essay_scoring.feature_store import persist_feature_store
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.runner import run_ablation, run_experiment
from scripts.ml_training.essay_scoring.splitters import DatasetSplit


def _make_text(word_count: int, *, seed: str) -> str:
    return " ".join(f"{seed}_w{i}" for i in range(word_count))


def _write_ellipse_train_test(tmp_path) -> tuple[pd.DataFrame, pd.DataFrame, object]:  # noqa: ANN001
    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    train_rows = []
    for i in range(40):
        label = 1.0 if i % 2 == 0 else 2.0
        word_count = 220 + (i % 4) * 30
        train_rows.append(
            {
                "full_text": _make_text(word_count, seed=f"train{i}"),
                "prompt": f"P{i % 3}",
                "Overall": str(label),
            }
        )
    test_rows = []
    for i in range(10):
        label = 1.0 if i % 2 == 0 else 2.0
        word_count = 230 + (i % 5) * 20
        test_rows.append(
            {
                "full_text": _make_text(word_count, seed=f"test{i}"),
                "prompt": f"P{i % 3}",
                "Overall": str(label),
            }
        )

    train_frame = pd.DataFrame(train_rows)
    test_frame = pd.DataFrame(test_rows)
    train_frame.to_csv(train_path, index=False)
    test_frame.to_csv(test_path, index=False)
    return train_frame, test_frame, (train_path, test_path)


def test_run_experiment_with_reused_feature_store_writes_artifacts(tmp_path) -> None:
    _, _, (train_path, test_path) = _write_ellipse_train_test(tmp_path)
    pre_split = load_ellipse_train_test_dataset(train_path, test_path, excluded_prompts=set())
    dataset = pre_split.dataset

    split = DatasetSplit(
        train=list(pre_split.train_records[:20]),
        val=list(pre_split.train_records[20:30]),
        test=list(pre_split.test_records[:10]),
    )

    rng = np.random.default_rng(0)
    feature_names = [f"f{i}" for i in range(4)]
    train_features = FeatureMatrix(
        matrix=rng.normal(size=(len(split.train), 4)).astype(np.float32),
        feature_names=feature_names,
    )
    val_features = FeatureMatrix(
        matrix=rng.normal(size=(len(split.val), 4)).astype(np.float32),
        feature_names=feature_names,
    )
    test_features = FeatureMatrix(
        matrix=rng.normal(size=(len(split.test), 4)).astype(np.float32),
        feature_names=feature_names,
    )

    training = TrainingConfig(
        train_ratio=0.7,
        val_ratio=0.3,
        test_ratio=0.0,
        random_seed=42,
        num_boost_round=30,
        early_stopping_rounds=5,
        params={
            "objective": "reg:squarederror",
            "max_depth": 3,
            "learning_rate": 0.2,
            "min_child_weight": 1,
            "reg_lambda": 1.0,
            "colsample_bytree": 1.0,
            "subsample": 1.0,
        },
    )
    config = ExperimentConfig(
        dataset_kind=DatasetKind.ELLIPSE,
        ellipse_train_path=train_path,
        ellipse_test_path=test_path,
        training=training,
        feature_set=FeatureSet.HANDCRAFTED,
        output=OutputConfig(base_dir=tmp_path / "runs", run_name="runner"),
    )

    store_run_dir = tmp_path / "feature_store_run"
    persist_feature_store(
        run_dir=store_run_dir,
        config=config,
        dataset=dataset,
        split=split,
        feature_set=FeatureSet.HANDCRAFTED,
        spacy_model="en_core_web_sm",
        train_features=train_features,
        val_features=val_features,
        test_features=test_features,
    )

    summary = run_experiment(
        config,
        feature_set=FeatureSet.HANDCRAFTED,
        reuse_feature_store_dir=store_run_dir,
        skip_shap=True,
        skip_grade_scale_report=False,
    )

    assert summary.run_paths.metrics_path.exists()
    assert summary.run_paths.metadata_path.exists()
    assert summary.run_paths.model_path.exists()
    assert summary.run_paths.feature_schema_path.exists()
    assert summary.run_paths.grade_scale_report_path.exists()

    metrics = json.loads(summary.run_paths.metrics_path.read_text(encoding="utf-8"))
    assert set(metrics) == {"train", "val", "test"}
    assert "qwk" in metrics["test"]

    metadata = json.loads(summary.run_paths.metadata_path.read_text(encoding="utf-8"))
    assert metadata["dataset_kind"] == "ellipse"
    assert metadata["feature_set"] == "handcrafted"
    assert metadata["record_counts"]["train"] == len(split.train)


def test_run_ablation_updates_run_names(tmp_path, monkeypatch) -> None:
    config = ExperimentConfig(output=OutputConfig(base_dir=tmp_path / "runs", run_name="base"))

    calls: list[str] = []

    from scripts.ml_training.essay_scoring.paths import build_run_paths
    from scripts.ml_training.essay_scoring.runner import RunSummary

    def _fake_run_experiment(
        updated_config: ExperimentConfig, *, feature_set: FeatureSet, **_kwargs
    ):
        calls.append(str(updated_config.output.run_name))
        return RunSummary(
            run_paths=build_run_paths(updated_config.output), feature_set=feature_set, metrics={}
        )

    monkeypatch.setattr(
        "scripts.ml_training.essay_scoring.runner.run_experiment",  # type: ignore[arg-type]
        lambda updated_config, feature_set=None, **_kwargs: _fake_run_experiment(
            updated_config,
            feature_set=feature_set,  # type: ignore[arg-type]
        ),
    )

    summaries = run_ablation(config)
    assert len(summaries) == 3

    assert calls == ["handcrafted", "embeddings", "combined"]
