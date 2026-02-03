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
from scripts.ml_training.essay_scoring.cross_validation import run_cross_validation
from scripts.ml_training.essay_scoring.cv_feature_store import persist_cv_feature_store
from scripts.ml_training.essay_scoring.dataset import load_ellipse_train_test_dataset
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.split_definitions import generate_splits


def _make_text(word_count: int, *, seed: str) -> str:
    return " ".join(f"{seed}_w{i}" for i in range(word_count))


def test_cross_validation_runs_with_reused_store(tmp_path) -> None:
    train_path = tmp_path / "train.csv"
    test_path = tmp_path / "test.csv"

    train_rows = []
    for i in range(30):
        label = 1.0 if i % 2 == 0 else 2.0
        train_rows.append(
            {
                "full_text": _make_text(250, seed=f"train{i}"),
                "prompt": f"P{i % 3}",
                "Overall": str(label),
            }
        )
    test_rows = []
    for i in range(10):
        label = 1.0 if i % 2 == 0 else 2.0
        test_rows.append(
            {
                "full_text": _make_text(250, seed=f"test{i}"),
                "prompt": f"P{i % 3}",
                "Overall": str(label),
            }
        )

    pd.DataFrame(train_rows).to_csv(train_path, index=False)
    pd.DataFrame(test_rows).to_csv(test_path, index=False)

    training = TrainingConfig(
        train_ratio=0.7,
        val_ratio=0.15,
        test_ratio=0.15,
        random_seed=42,
        num_boost_round=50,
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

    base_config = ExperimentConfig(
        dataset_kind=DatasetKind.ELLIPSE,
        ellipse_train_path=train_path,
        ellipse_test_path=test_path,
        training=training,
        output=OutputConfig(base_dir=tmp_path, run_name="splits"),
    )

    splits_summary = generate_splits(base_config, min_words=200, max_words=1000, n_splits=3)

    dataset = load_ellipse_train_test_dataset(train_path, test_path, excluded_prompts=set())
    train_records = dataset.train_records
    test_records = dataset.test_records

    rng = np.random.default_rng(0)
    feature_names = [f"f{i}" for i in range(4)]
    train_matrix = rng.normal(size=(len(train_records), 4)).astype(np.float32)
    test_matrix = rng.normal(size=(len(test_records), 4)).astype(np.float32)

    store_run_dir = tmp_path / "precomputed_store_run"
    store_run_dir.mkdir(parents=True, exist_ok=True)
    persist_cv_feature_store(
        run_dir=store_run_dir,
        config=base_config,
        feature_set=FeatureSet.HANDCRAFTED,
        spacy_model="en_core_web_sm",
        word_count_window={"min": 200, "max": 1000},
        train_record_ids=[record.record_id for record in train_records],
        test_record_ids=[record.record_id for record in test_records],
        train_features=FeatureMatrix(matrix=train_matrix, feature_names=feature_names),
        test_features=FeatureMatrix(matrix=test_matrix, feature_names=feature_names),
        y_train=np.array([record.overall for record in train_records], dtype=np.float32),
        y_test=np.array([record.overall for record in test_records], dtype=np.float32),
    )

    cv_config = base_config.model_copy(
        update={"output": OutputConfig(base_dir=tmp_path, run_name="cv")}
    )
    cv_summary = run_cross_validation(
        cv_config,
        feature_set=FeatureSet.HANDCRAFTED,
        splits_path=splits_summary.splits_path,
        scheme="stratified_text",
        reuse_cv_feature_store_dir=store_run_dir,
        min_words=200,
        max_words=1000,
    )

    assert cv_summary.metrics_path.exists()
    payload = json.loads(cv_summary.metrics_path.read_text(encoding="utf-8"))
    assert payload["feature_set"] == "handcrafted"
    assert "summary" in payload
    assert "folds" in payload
