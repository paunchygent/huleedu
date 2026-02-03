from __future__ import annotations

import json

import numpy as np
import pytest

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.dataset import EssayDataset, EssayRecord
from scripts.ml_training.essay_scoring.feature_store import (
    load_feature_store,
    persist_feature_store,
    resolve_feature_store_dir,
)
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.splitters import DatasetSplit


def _record(idx: int, label: float) -> EssayRecord:
    return EssayRecord(
        record_id=f"record-{idx}",
        task_type="1",
        question="Prompt?",
        essay=f"Essay {idx}",
        overall=label,
        component_scores={},
    )


def test_feature_store_roundtrip_and_dir_resolution(tmp_path) -> None:
    dataset_path = tmp_path / "ielts.csv"
    dataset_path.write_text("Task_Type,Question,Essay,Overall\n1,Q,E,5.0\n", encoding="utf-8")

    config = ExperimentConfig(
        dataset_kind=DatasetKind.IELTS,
        dataset_path=dataset_path,
    )

    records = [_record(1, 5.0), _record(2, 6.0), _record(3, 7.0), _record(4, 6.5)]
    dataset = EssayDataset(records=list(records))
    split = DatasetSplit(train=[records[0], records[1]], val=[records[2]], test=[records[3]])

    feature_names = ["f0", "f1"]
    train_features = FeatureMatrix(
        matrix=np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32),
        feature_names=feature_names,
    )
    val_features = FeatureMatrix(
        matrix=np.array([[5.0, 6.0]], dtype=np.float32),
        feature_names=feature_names,
    )
    test_features = FeatureMatrix(
        matrix=np.array([[7.0, 8.0]], dtype=np.float32),
        feature_names=feature_names,
    )

    store_run_dir = tmp_path / "store_run"
    store_dir = persist_feature_store(
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

    assert resolve_feature_store_dir(store_run_dir) == store_dir
    assert resolve_feature_store_dir(store_dir) == store_dir

    loaded = load_feature_store(
        dataset=dataset,
        store_dir=store_dir,
        expected_config=config.model_copy(update={"feature_set": FeatureSet.HANDCRAFTED}),
    )
    assert loaded.manifest.dataset_kind == DatasetKind.IELTS
    assert loaded.split.train[0].record_id == split.train[0].record_id
    assert np.allclose(loaded.train_features.matrix, train_features.matrix)
    assert np.allclose(loaded.val_features.matrix, val_features.matrix)
    assert np.allclose(loaded.test_features.matrix, test_features.matrix)


def test_feature_store_rejects_schema_mismatch(tmp_path) -> None:
    dataset_path = tmp_path / "ielts.csv"
    dataset_path.write_text("Task_Type,Question,Essay,Overall\n1,Q,E,5.0\n", encoding="utf-8")

    config = ExperimentConfig(
        dataset_kind=DatasetKind.IELTS,
        dataset_path=dataset_path,
    )

    records = [_record(1, 5.0), _record(2, 6.0), _record(3, 7.0)]
    dataset = EssayDataset(records=list(records))
    split = DatasetSplit(train=[records[0]], val=[records[1]], test=[records[2]])

    feature_names = ["f0"]
    matrix = np.array([[1.0]], dtype=np.float32)
    store_dir = persist_feature_store(
        run_dir=tmp_path / "store_run",
        config=config,
        dataset=dataset,
        split=split,
        feature_set=FeatureSet.HANDCRAFTED,
        spacy_model="en_core_web_sm",
        train_features=FeatureMatrix(matrix=matrix, feature_names=feature_names),
        val_features=FeatureMatrix(matrix=matrix, feature_names=feature_names),
        test_features=FeatureMatrix(matrix=matrix, feature_names=feature_names),
    )

    manifest_path = store_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 999
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported feature store schema version"):
        load_feature_store(dataset=dataset, store_dir=store_dir)


def test_feature_store_rejects_dataset_hash_mismatch(tmp_path) -> None:
    dataset_path = tmp_path / "ielts.csv"
    dataset_path.write_text("Task_Type,Question,Essay,Overall\n1,Q,E,5.0\n", encoding="utf-8")

    config = ExperimentConfig(
        dataset_kind=DatasetKind.IELTS,
        dataset_path=dataset_path,
    )

    records = [_record(1, 5.0), _record(2, 6.0), _record(3, 7.0)]
    dataset = EssayDataset(records=list(records))
    split = DatasetSplit(train=[records[0]], val=[records[1]], test=[records[2]])

    store_dir = persist_feature_store(
        run_dir=tmp_path / "store_run",
        config=config,
        dataset=dataset,
        split=split,
        feature_set=FeatureSet.HANDCRAFTED,
        spacy_model="en_core_web_sm",
        train_features=FeatureMatrix(
            matrix=np.array([[1.0]], dtype=np.float32), feature_names=["f0"]
        ),
        val_features=FeatureMatrix(
            matrix=np.array([[2.0]], dtype=np.float32), feature_names=["f0"]
        ),
        test_features=FeatureMatrix(
            matrix=np.array([[3.0]], dtype=np.float32), feature_names=["f0"]
        ),
    )

    dataset_path.write_text("Task_Type,Question,Essay,Overall\n1,Q,E,6.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="dataset hash mismatch"):
        load_feature_store(
            dataset=dataset,
            store_dir=store_dir,
            expected_config=config.model_copy(update={"feature_set": FeatureSet.HANDCRAFTED}),
        )


def test_feature_store_rejects_shape_mismatch(tmp_path) -> None:
    dataset_path = tmp_path / "ielts.csv"
    dataset_path.write_text("Task_Type,Question,Essay,Overall\n1,Q,E,5.0\n", encoding="utf-8")

    config = ExperimentConfig(
        dataset_kind=DatasetKind.IELTS,
        dataset_path=dataset_path,
    )

    records = [_record(1, 5.0), _record(2, 6.0), _record(3, 7.0)]
    dataset = EssayDataset(records=list(records))
    split = DatasetSplit(train=[records[0]], val=[records[1]], test=[records[2]])

    store_dir = persist_feature_store(
        run_dir=tmp_path / "store_run",
        config=config,
        dataset=dataset,
        split=split,
        feature_set=FeatureSet.HANDCRAFTED,
        spacy_model="en_core_web_sm",
        train_features=FeatureMatrix(
            matrix=np.array([[1.0]], dtype=np.float32), feature_names=["f0"]
        ),
        val_features=FeatureMatrix(
            matrix=np.array([[2.0]], dtype=np.float32), feature_names=["f0"]
        ),
        test_features=FeatureMatrix(
            matrix=np.array([[3.0]], dtype=np.float32), feature_names=["f0"]
        ),
    )

    np.save(store_dir / "val_features.npy", np.zeros((2, 1), dtype=np.float32), allow_pickle=False)

    with pytest.raises(ValueError, match="feature rows mismatch"):
        load_feature_store(dataset=dataset, store_dir=store_dir)
