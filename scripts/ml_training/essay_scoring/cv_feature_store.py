"""Feature store for cross-validation workflows.

Unlike the per-run split feature store (`feature_store.py`), this store persists
features for the full (filtered) train split and the locked test split. CV folds
then slice by `record_id` without re-extracting features.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.environment import gather_git_sha, repo_root_from_package
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix

_CV_STORE_SCHEMA_VERSION = 2


class CVFeatureStoreManifest(BaseModel):
    """Metadata describing a persisted CV feature store."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=_CV_STORE_SCHEMA_VERSION, ge=1)
    created_at: str
    git_sha: str

    dataset_kind: DatasetKind
    dataset_sources: dict[str, str]
    dataset_sha256: dict[str, str]
    dataset_excluded_prompts: list[str] = Field(default_factory=list)
    word_count_window: dict[str, int]

    feature_set: FeatureSet
    spacy_model: str
    embedding_model_name: str
    embedding_max_length: int

    feature_names: list[str]
    train_record_ids: list[str]
    test_record_ids: list[str]

    files: dict[str, str]


@dataclass(frozen=True)
class CVFeatureStoreData:
    manifest: CVFeatureStoreManifest
    train_features: FeatureMatrix
    test_features: FeatureMatrix
    y_train: np.ndarray
    y_test: np.ndarray


def cv_feature_store_dir(run_dir: Path) -> Path:
    return run_dir / "cv_feature_store"


def persist_cv_feature_store(
    *,
    run_dir: Path,
    config: ExperimentConfig,
    feature_set: FeatureSet,
    spacy_model: str,
    word_count_window: dict[str, int],
    train_record_ids: list[str],
    test_record_ids: list[str],
    train_features: FeatureMatrix,
    test_features: FeatureMatrix,
    y_train: np.ndarray,
    y_test: np.ndarray,
) -> Path:
    store_dir = cv_feature_store_dir(run_dir)
    store_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "manifest": store_dir / "manifest.json",
        "train_features": store_dir / "train_features.npy",
        "train_labels": store_dir / "train_labels.npy",
        "test_features": store_dir / "test_features.npy",
        "test_labels": store_dir / "test_labels.npy",
    }

    np.save(paths["train_features"], _as_float32(train_features.matrix), allow_pickle=False)
    np.save(paths["train_labels"], np.array(y_train, dtype=np.float32), allow_pickle=False)
    np.save(paths["test_features"], _as_float32(test_features.matrix), allow_pickle=False)
    np.save(paths["test_labels"], np.array(y_test, dtype=np.float32), allow_pickle=False)

    repo_root = repo_root_from_package()
    dataset_sources: dict[str, str]
    dataset_sha256: dict[str, str]
    dataset_excluded_prompts: list[str] = []

    if config.dataset_kind == DatasetKind.IELTS:
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

    manifest = CVFeatureStoreManifest(
        created_at=datetime.now(tz=timezone.utc).isoformat(),
        git_sha=gather_git_sha(repo_root),
        dataset_kind=config.dataset_kind,
        dataset_sources=dataset_sources,
        dataset_sha256=dataset_sha256,
        dataset_excluded_prompts=dataset_excluded_prompts,
        word_count_window={str(k): int(v) for k, v in word_count_window.items()},
        feature_set=feature_set,
        spacy_model=spacy_model,
        embedding_model_name=config.embedding.model_name,
        embedding_max_length=config.embedding.max_length,
        feature_names=list(train_features.feature_names),
        train_record_ids=list(train_record_ids),
        test_record_ids=list(test_record_ids),
        files={key: str(path.relative_to(store_dir)) for key, path in paths.items()},
    )
    paths["manifest"].write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return store_dir


def load_cv_feature_store(
    *,
    store_dir: Path,
    expected_config: ExperimentConfig,
    expected_feature_set: FeatureSet,
    expected_word_count_window: dict[str, int],
) -> CVFeatureStoreData:
    manifest_path = store_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"CV feature store manifest not found at {manifest_path}")

    manifest = CVFeatureStoreManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    if manifest.schema_version != _CV_STORE_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported CV feature store schema version "
            f"store={manifest.schema_version} expected={_CV_STORE_SCHEMA_VERSION}."
        )

    if manifest.dataset_kind != expected_config.dataset_kind:
        raise ValueError(
            "CV feature store dataset_kind mismatch "
            f"expected={expected_config.dataset_kind.value} store={manifest.dataset_kind.value}"
        )

    if manifest.feature_set != expected_feature_set:
        raise ValueError(
            "CV feature store feature_set mismatch "
            f"expected={expected_feature_set.value} store={manifest.feature_set.value}"
        )

    if manifest.embedding_model_name != expected_config.embedding.model_name:
        raise ValueError(
            "CV feature store embedding model mismatch "
            f"expected={expected_config.embedding.model_name} store={manifest.embedding_model_name}"
        )

    if manifest.embedding_max_length != expected_config.embedding.max_length:
        raise ValueError(
            "CV feature store embedding max_length mismatch "
            f"expected={expected_config.embedding.max_length} store={manifest.embedding_max_length}"
        )

    expected_window = {str(k): int(v) for k, v in expected_word_count_window.items()}
    if manifest.word_count_window != expected_window:
        raise ValueError(
            "CV feature store word_count_window mismatch "
            f"expected={expected_window} store={manifest.word_count_window}"
        )

    _validate_dataset_fingerprint(manifest, expected_config)

    train_features = FeatureMatrix(
        matrix=np.load(store_dir / manifest.files["train_features"]),
        feature_names=list(manifest.feature_names),
    )
    test_features = FeatureMatrix(
        matrix=np.load(store_dir / manifest.files["test_features"]),
        feature_names=list(manifest.feature_names),
    )
    y_train = np.load(store_dir / manifest.files["train_labels"])
    y_test = np.load(store_dir / manifest.files["test_labels"])

    return CVFeatureStoreData(
        manifest=manifest,
        train_features=train_features,
        test_features=test_features,
        y_train=y_train,
        y_test=y_test,
    )


def resolve_cv_feature_store_dir(path: Path) -> Path:
    """Resolve either a run directory or a direct CV store directory."""

    if (path / "manifest.json").exists():
        return path
    candidate = path / "cv_feature_store"
    if (candidate / "manifest.json").exists():
        return candidate
    raise FileNotFoundError(
        "Could not find CV feature store manifest. Expected either "
        f"{path / 'manifest.json'} or {candidate / 'manifest.json'}"
    )


def _validate_dataset_fingerprint(
    manifest: CVFeatureStoreManifest, config: ExperimentConfig
) -> None:
    if config.dataset_kind == DatasetKind.IELTS:
        expected = {"ielts": _sha256_file(config.dataset_path)}
        if manifest.dataset_sha256 != expected:
            raise ValueError(
                "CV feature store dataset fingerprint mismatch for ielts "
                f"expected={expected} store={manifest.dataset_sha256}"
            )
        return

    expected = {
        "ellipse_train": _sha256_file(config.ellipse_train_path),
        "ellipse_test": _sha256_file(config.ellipse_test_path),
    }
    if manifest.dataset_sha256 != expected:
        raise ValueError(
            "CV feature store dataset fingerprint mismatch for ellipse "
            f"expected={expected} store={manifest.dataset_sha256}"
        )

    excluded = sorted(config.ellipse_excluded_prompts)
    if manifest.dataset_excluded_prompts != excluded:
        raise ValueError(
            "CV feature store excluded prompt filter mismatch for ellipse "
            f"expected={excluded} store={manifest.dataset_excluded_prompts}"
        )


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
