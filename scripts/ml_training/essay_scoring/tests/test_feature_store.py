"""Tests for the warm-cache feature store."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from scripts.ml_training.essay_scoring.config import ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.dataset import EssayDataset, EssayRecord
from scripts.ml_training.essay_scoring.feature_store import (
    load_feature_store,
    persist_feature_store,
    resolve_feature_store_dir,
)
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.splitters import DatasetSplit


def _write_min_dataset(path: Path) -> None:
    rows = [
        {
            "Task_Type": "1",
            "Question": "Q1",
            "Essay": "A B.",
            "Examiner_Commen": "",
            "Task_Response": "6",
            "Coherence_Cohesion": "6",
            "Lexical_Resource": "6",
            "Range_Accuracy": "6",
            "Overall": "6.0",
        },
        {
            "Task_Type": "1",
            "Question": "Q2",
            "Essay": "A C.",
            "Examiner_Commen": "",
            "Task_Response": "6",
            "Coherence_Cohesion": "6",
            "Lexical_Resource": "6",
            "Range_Accuracy": "6",
            "Overall": "6.5",
        },
        {
            "Task_Type": "2",
            "Question": "Q3",
            "Essay": "D E.",
            "Examiner_Commen": "",
            "Task_Response": "7",
            "Coherence_Cohesion": "7",
            "Lexical_Resource": "7",
            "Range_Accuracy": "7",
            "Overall": "7.0",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_feature_store_roundtrip(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.csv"
    _write_min_dataset(dataset_path)

    records = [
        EssayRecord(
            record_id="r1",
            task_type="1",
            question="Q1",
            essay="A B.",
            overall=6.0,
            component_scores={},
        ),
        EssayRecord(
            record_id="r2",
            task_type="1",
            question="Q2",
            essay="A C.",
            overall=6.5,
            component_scores={},
        ),
        EssayRecord(
            record_id="r3",
            task_type="2",
            question="Q3",
            essay="D E.",
            overall=7.0,
            component_scores={},
        ),
    ]
    dataset = EssayDataset(records=records)
    split = DatasetSplit(train=[records[0]], val=[records[1]], test=[records[2]])

    feature_names = ["f1", "f2", "f3"]
    train_features = FeatureMatrix(
        matrix=np.array([[1.0, 2.0, 3.0]], dtype=np.float32), feature_names=feature_names
    )
    val_features = FeatureMatrix(
        matrix=np.array([[4.0, 5.0, 6.0]], dtype=np.float32), feature_names=feature_names
    )
    test_features = FeatureMatrix(
        matrix=np.array([[7.0, 8.0, 9.0]], dtype=np.float32), feature_names=feature_names
    )

    config = ExperimentConfig(dataset_path=dataset_path, feature_set=FeatureSet.COMBINED)

    store_dir = persist_feature_store(
        run_dir=tmp_path / "run",
        config=config,
        dataset=dataset,
        split=split,
        feature_set=FeatureSet.COMBINED,
        spacy_model="en_core_web_sm",
        train_features=train_features,
        val_features=val_features,
        test_features=test_features,
    )

    resolved = resolve_feature_store_dir(store_dir.parent)
    assert resolved == store_dir

    loaded = load_feature_store(dataset=dataset, store_dir=store_dir, expected_config=config)

    assert loaded.split == split
    assert loaded.train_features.feature_names == feature_names
    assert loaded.val_features.feature_names == feature_names
    assert loaded.test_features.feature_names == feature_names

    np.testing.assert_allclose(loaded.train_features.matrix, train_features.matrix)
    np.testing.assert_allclose(loaded.val_features.matrix, val_features.matrix)
    np.testing.assert_allclose(loaded.test_features.matrix, test_features.matrix)
    np.testing.assert_allclose(loaded.y_train, np.array([6.0], dtype=np.float32))
    np.testing.assert_allclose(loaded.y_val, np.array([6.5], dtype=np.float32))
    np.testing.assert_allclose(loaded.y_test, np.array([7.0], dtype=np.float32))
