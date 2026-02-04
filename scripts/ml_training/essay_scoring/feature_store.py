"""Warm-cache feature store for essay scoring research runs.

This module persists extracted features (train/val/test) so experiments can iterate on
training parameters without re-running expensive feature extraction.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.dataset import EssayDataset, EssayRecord
from scripts.ml_training.essay_scoring.environment import gather_git_sha, repo_root_from_package
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.splitters import DatasetSplit

_FEATURE_STORE_SCHEMA_VERSION = 5


class FeatureStoreManifest(BaseModel):
    """Metadata describing a persisted feature store."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=_FEATURE_STORE_SCHEMA_VERSION, ge=1)
    created_at: str
    git_sha: str

    dataset_kind: DatasetKind
    dataset_sources: dict[str, str]
    dataset_sha256: dict[str, str]
    dataset_excluded_prompts: list[str] = Field(default_factory=list)
    record_counts: dict[str, int]

    feature_set: FeatureSet
    spacy_model: str
    embedding_model_name: str
    embedding_max_length: int

    feature_names: list[str]
    split_record_ids: dict[str, list[str]]

    files: dict[str, str]


@dataclass(frozen=True)
class FeatureStoreData:
    """In-memory feature store contents."""

    manifest: FeatureStoreManifest
    split: DatasetSplit
    train_features: FeatureMatrix
    val_features: FeatureMatrix
    test_features: FeatureMatrix
    y_train: np.ndarray
    y_val: np.ndarray
    y_test: np.ndarray


def feature_store_dir(run_dir: Path) -> Path:
    return run_dir / "feature_store"


def persist_feature_store(
    *,
    run_dir: Path,
    config: ExperimentConfig,
    dataset: EssayDataset,
    split: DatasetSplit,
    feature_set: FeatureSet,
    spacy_model: str,
    train_features: FeatureMatrix,
    val_features: FeatureMatrix,
    test_features: FeatureMatrix,
) -> Path:
    """Persist extracted features and a split manifest under the given run directory."""

    store_dir = feature_store_dir(run_dir)
    store_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "manifest": store_dir / "manifest.json",
        "train_features": store_dir / "train_features.npy",
        "val_features": store_dir / "val_features.npy",
        "test_features": store_dir / "test_features.npy",
        "train_labels": store_dir / "train_labels.npy",
        "val_labels": store_dir / "val_labels.npy",
        "test_labels": store_dir / "test_labels.npy",
    }

    y_train = np.array([record.overall for record in split.train], dtype=np.float32)
    y_val = np.array([record.overall for record in split.val], dtype=np.float32)
    y_test = np.array([record.overall for record in split.test], dtype=np.float32)

    np.save(paths["train_features"], _as_float32(train_features.matrix), allow_pickle=False)
    np.save(paths["val_features"], _as_float32(val_features.matrix), allow_pickle=False)
    np.save(paths["test_features"], _as_float32(test_features.matrix), allow_pickle=False)
    np.save(paths["train_labels"], y_train, allow_pickle=False)
    np.save(paths["val_labels"], y_val, allow_pickle=False)
    np.save(paths["test_labels"], y_test, allow_pickle=False)

    split_record_ids = {
        "train": [_record_id(record) for record in split.train],
        "val": [_record_id(record) for record in split.val],
        "test": [_record_id(record) for record in split.test],
    }

    repo_root = repo_root_from_package()
    dataset_kind = config.dataset_kind
    dataset_sources: dict[str, str]
    dataset_sha256: dict[str, str]
    dataset_excluded_prompts: list[str] = []

    if dataset_kind == DatasetKind.IELTS:
        dataset_sources = {"ielts": str(config.dataset_path)}
        dataset_sha256 = {"ielts": _sha256_file(config.dataset_path)}
    else:
        dataset_sources = {
            "ellipse_train": str(config.ellipse_train_path),
            "ellipse_test": str(config.ellipse_test_path),
        }
        dataset_sha256 = {
            "ellipse_train": _sha256_file(config.ellipse_train_path),
            "ellipse_test": _sha256_file(config.ellipse_test_path),
        }
        dataset_excluded_prompts = sorted(config.ellipse_excluded_prompts)

    manifest = FeatureStoreManifest(
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        git_sha=gather_git_sha(repo_root),
        dataset_kind=dataset_kind,
        dataset_sources=dataset_sources,
        dataset_sha256=dataset_sha256,
        dataset_excluded_prompts=dataset_excluded_prompts,
        record_counts={
            "total": len(dataset.records),
            "train": len(split.train),
            "val": len(split.val),
            "test": len(split.test),
        },
        feature_set=feature_set,
        spacy_model=spacy_model,
        embedding_model_name=config.embedding.model_name,
        embedding_max_length=config.embedding.max_length,
        feature_names=list(train_features.feature_names),
        split_record_ids=split_record_ids,
        files={key: str(path.relative_to(store_dir)) for key, path in paths.items()},
    )
    paths["manifest"].write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return store_dir


def load_feature_store(
    *,
    dataset: EssayDataset,
    store_dir: Path,
    expected_config: ExperimentConfig | None = None,
) -> FeatureStoreData:
    """Load a previously persisted feature store and materialize the split."""

    manifest_path = store_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Feature store manifest not found at {manifest_path}")

    manifest = FeatureStoreManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    if manifest.schema_version != _FEATURE_STORE_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported feature store schema version "
            f"store={manifest.schema_version} expected={_FEATURE_STORE_SCHEMA_VERSION}. "
            "Re-run 'featurize' to regenerate the feature store."
        )

    if expected_config is not None:
        if manifest.dataset_kind != expected_config.dataset_kind:
            raise ValueError(
                "Feature store dataset_kind mismatch "
                f"expected={expected_config.dataset_kind.value} store={manifest.dataset_kind.value}"
            )
        _validate_dataset_fingerprint(manifest, expected_config)
        if manifest.feature_set != expected_config.feature_set:
            raise ValueError(
                "Feature store feature_set mismatch "
                f"expected={expected_config.feature_set.value} store={manifest.feature_set.value}"
            )
        if manifest.embedding_model_name != expected_config.embedding.model_name:
            raise ValueError(
                "Feature store embedding model mismatch "
                f"expected={expected_config.embedding.model_name} "
                f"store={manifest.embedding_model_name}"
            )
        if manifest.embedding_max_length != expected_config.embedding.max_length:
            raise ValueError(
                "Feature store embedding max_length mismatch "
                f"expected={expected_config.embedding.max_length} "
                f"store={manifest.embedding_max_length}"
            )

    split = _materialize_split(dataset, manifest.split_record_ids)

    train_features = FeatureMatrix(
        matrix=np.load(store_dir / manifest.files["train_features"]),
        feature_names=list(manifest.feature_names),
    )
    val_features = FeatureMatrix(
        matrix=np.load(store_dir / manifest.files["val_features"]),
        feature_names=list(manifest.feature_names),
    )
    test_features = FeatureMatrix(
        matrix=np.load(store_dir / manifest.files["test_features"]),
        feature_names=list(manifest.feature_names),
    )

    y_train = np.load(store_dir / manifest.files["train_labels"])
    y_val = np.load(store_dir / manifest.files["val_labels"])
    y_test = np.load(store_dir / manifest.files["test_labels"])

    _validate_shapes(
        split=split,
        train_features=train_features,
        val_features=val_features,
        test_features=test_features,
        y_train=y_train,
        y_val=y_val,
        y_test=y_test,
    )

    return FeatureStoreData(
        manifest=manifest,
        split=split,
        train_features=train_features,
        val_features=val_features,
        test_features=test_features,
        y_train=y_train,
        y_val=y_val,
        y_test=y_test,
    )


def resolve_feature_store_dir(path: Path) -> Path:
    """Resolve either a run directory or a direct feature-store directory."""

    if (path / "manifest.json").exists():
        return path
    candidate = path / "feature_store"
    if (candidate / "manifest.json").exists():
        return candidate
    raise FileNotFoundError(
        "Could not find feature store manifest. Expected either "
        f"{path / 'manifest.json'} or {candidate / 'manifest.json'}"
    )


def _validate_dataset_fingerprint(
    manifest: FeatureStoreManifest, expected: ExperimentConfig
) -> None:
    if manifest.dataset_kind == DatasetKind.IELTS:
        expected_sha = _sha256_file(expected.dataset_path)
        stored_sha = manifest.dataset_sha256.get("ielts")
        if stored_sha != expected_sha:
            raise ValueError(
                f"Feature store dataset hash mismatch expected={expected_sha} store={stored_sha}"
            )
        return

    expected_train_sha = _sha256_file(expected.ellipse_train_path)
    expected_test_sha = _sha256_file(expected.ellipse_test_path)
    stored_train_sha = manifest.dataset_sha256.get("ellipse_train")
    stored_test_sha = manifest.dataset_sha256.get("ellipse_test")
    if stored_train_sha != expected_train_sha or stored_test_sha != expected_test_sha:
        raise ValueError(
            "Feature store dataset hash mismatch for ellipse "
            f"expected_train={expected_train_sha} store_train={stored_train_sha} "
            f"expected_test={expected_test_sha} store_test={stored_test_sha}"
        )
    if sorted(expected.ellipse_excluded_prompts) != sorted(manifest.dataset_excluded_prompts):
        raise ValueError(
            "Feature store excluded prompt filter mismatch for ellipse "
            f"expected={sorted(expected.ellipse_excluded_prompts)} "
            f"store={sorted(manifest.dataset_excluded_prompts)}"
        )


def _materialize_split(
    dataset: EssayDataset, split_record_ids: dict[str, list[str]]
) -> DatasetSplit:
    by_id: dict[str, EssayRecord] = {}
    for record in dataset.records:
        record_id = _record_id(record)
        if record_id in by_id:
            raise ValueError(
                "Dataset contains duplicate record IDs; cannot materialize split deterministically."
            )
        by_id[record_id] = record

    def _records(split_name: str) -> list[EssayRecord]:
        missing = [rid for rid in split_record_ids[split_name] if rid not in by_id]
        if missing:
            raise ValueError(
                f"Feature store split '{split_name}' contains record IDs missing from dataset "
                f"count={len(missing)}"
            )
        return [by_id[rid] for rid in split_record_ids[split_name]]

    return DatasetSplit(
        train=_records("train"),
        val=_records("val"),
        test=_records("test"),
    )


def _record_id(record: EssayRecord) -> str:
    return record.record_id


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _as_float32(matrix: np.ndarray) -> np.ndarray:
    if matrix.dtype == np.float32:
        return matrix
    return matrix.astype(np.float32, copy=False)


def _validate_shapes(
    *,
    split: DatasetSplit,
    train_features: FeatureMatrix,
    val_features: FeatureMatrix,
    test_features: FeatureMatrix,
    y_train: np.ndarray,
    y_val: np.ndarray,
    y_test: np.ndarray,
) -> None:
    expected_dim = int(train_features.matrix.shape[1])
    for name, feats, y, records in [
        ("train", train_features, y_train, split.train),
        ("val", val_features, y_val, split.val),
        ("test", test_features, y_test, split.test),
    ]:
        if feats.matrix.shape[0] != len(records):
            raise ValueError(
                f"Feature store {name} feature rows mismatch rows={feats.matrix.shape[0]} "
                f"records={len(records)}"
            )
        if int(feats.matrix.shape[1]) != expected_dim:
            raise ValueError(
                f"Feature store {name} feature dim mismatch dim={feats.matrix.shape[1]} "
                f"expected={expected_dim}"
            )
        if y.shape[0] != len(records):
            raise ValueError(
                f"Feature store {name} labels mismatch labels={y.shape[0]} records={len(records)}"
            )
