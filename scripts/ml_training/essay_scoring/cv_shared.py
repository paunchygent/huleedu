"""Shared helpers for CV-style essay scoring workflows."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Literal

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.cv_feature_store import (
    persist_cv_feature_store,
    resolve_cv_feature_store_dir,
)
from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.features.pipeline import FeaturePipeline
from scripts.ml_training.essay_scoring.offload.metrics import (
    ExtractionBenchmark,
    persist_offload_metrics,
)
from scripts.ml_training.essay_scoring.split_definitions import FoldDefinition, SplitDefinitions
from scripts.ml_training.essay_scoring.text_processing import (
    count_words,
    normalize_text_for_hashing,
    sha256_text,
)
from scripts.ml_training.essay_scoring.training.evaluation import evaluate_predictions
from scripts.ml_training.essay_scoring.training.trainer import train_model

logger = logging.getLogger(__name__)

SplitScheme = Literal["stratified_text", "prompt_holdout"]


def prepare_cv_feature_store(
    *,
    config: ExperimentConfig,
    run_dir: Path,
    feature_set: FeatureSet,
    word_window: dict[str, int],
    train_records: list[EssayRecord],
    test_records: list[EssayRecord],
    reuse_store_dir: Path | None,
) -> Path:
    """Create or reuse a CV feature store (full train + locked test)."""

    if reuse_store_dir is not None:
        resolved = resolve_cv_feature_store_dir(reuse_store_dir)
        logger.info("Reusing CV feature store from %s", resolved)
        persist_offload_metrics(
            output_path=run_dir / "artifacts" / "offload_metrics.json",
            metrics=None,
            benchmarks=None,
        )
        return resolved

    pipeline = FeaturePipeline(config.embedding, offload=config.offload)
    logger.info("Extracting train features (n=%d)", len(train_records))
    benchmarks: list[ExtractionBenchmark] = []
    start = time.monotonic()
    train_features = pipeline.extract(train_records, feature_set)
    elapsed = time.monotonic() - start
    benchmarks.append(
        ExtractionBenchmark(
            mode="cv_feature_store_train_extract",
            records_processed=len(train_records),
            elapsed_s=elapsed,
        )
    )
    logger.info("Extracting test features (n=%d)", len(test_records))
    start = time.monotonic()
    test_features = pipeline.extract(test_records, feature_set)
    elapsed = time.monotonic() - start
    benchmarks.append(
        ExtractionBenchmark(
            mode="cv_feature_store_test_extract",
            records_processed=len(test_records),
            elapsed_s=elapsed,
        )
    )

    total_records = len(train_records) + len(test_records)
    total_elapsed = sum(benchmark.elapsed_s for benchmark in benchmarks)
    benchmarks.append(
        ExtractionBenchmark(
            mode="cv_feature_store_total_extract",
            records_processed=total_records,
            elapsed_s=total_elapsed,
        )
    )

    persist_offload_metrics(
        output_path=run_dir / "artifacts" / "offload_metrics.json",
        metrics=pipeline.offload_metrics,
        benchmarks=benchmarks,
    )

    y_train = np.array([record.overall for record in train_records], dtype=np.float32)
    y_test = np.array([record.overall for record in test_records], dtype=np.float32)

    store_dir = persist_cv_feature_store(
        run_dir=run_dir,
        config=config,
        feature_set=feature_set,
        spacy_model=pipeline.spacy_model,
        word_count_window=word_window,
        train_record_ids=[record.record_id for record in train_records],
        test_record_ids=[record.record_id for record in test_records],
        train_features=train_features,
        test_features=test_features,
        y_train=y_train,
        y_test=y_test,
    )
    logger.info("CV feature store created: %s", store_dir)
    return store_dir


def run_fold(
    *,
    fold: FoldDefinition,
    train_id_to_idx: dict[str, int],
    features: FeatureMatrix,
    y: np.ndarray,
    config: ExperimentConfig,
    min_band: float,
    max_band: float,
    keep_feature_indices: list[int] | None,
) -> dict[str, Any]:
    """Train and evaluate a single CV fold (optionally dropping feature columns)."""

    train_idx = indices_for_ids(fold.train_record_ids, id_to_idx=train_id_to_idx)
    val_idx = indices_for_ids(fold.val_record_ids, id_to_idx=train_id_to_idx)

    train_matrix = features.matrix[train_idx]
    val_matrix = features.matrix[val_idx]
    feature_names = list(features.feature_names)

    if keep_feature_indices is not None:
        feature_names = [feature_names[idx] for idx in keep_feature_indices]
        train_matrix = train_matrix[:, keep_feature_indices]
        val_matrix = val_matrix[:, keep_feature_indices]

    artifacts = train_model(
        FeatureMatrix(matrix=train_matrix, feature_names=feature_names),
        FeatureMatrix(matrix=val_matrix, feature_names=feature_names),
        y[train_idx],
        y[val_idx],
        config.training,
        min_band=min_band,
        max_band=max_band,
    )

    dtrain = xgb.DMatrix(train_matrix, feature_names=feature_names)
    dval = xgb.DMatrix(val_matrix, feature_names=feature_names)
    pred_train = artifacts.model.predict(dtrain)
    pred_val = artifacts.model.predict(dval)

    eval_train = evaluate_predictions(
        y[train_idx], pred_train, min_band=min_band, max_band=max_band
    )
    eval_val = evaluate_predictions(y[val_idx], pred_val, min_band=min_band, max_band=max_band)

    return {
        "fold": int(fold.fold),
        "sizes": {"train": int(train_idx.size), "val": int(val_idx.size)},
        "best_iteration": int(artifacts.best_iteration),
        "train": {
            "qwk": float(eval_train.qwk),
            "adjacent_accuracy": float(eval_train.adjacent_accuracy),
            "mean_absolute_error": float(eval_train.mean_absolute_error),
        },
        "val": {
            "qwk": float(eval_val.qwk),
            "adjacent_accuracy": float(eval_val.adjacent_accuracy),
            "mean_absolute_error": float(eval_val.mean_absolute_error),
        },
    }


def indices_for_ids(record_ids: list[str], *, id_to_idx: dict[str, int]) -> np.ndarray:
    return np.array([id_to_idx[record_id] for record_id in record_ids], dtype=int)


def select_folds(splits: SplitDefinitions, *, scheme: SplitScheme) -> list[FoldDefinition]:
    if scheme == "stratified_text":
        return list(splits.stratified_text_folds)
    if scheme == "prompt_holdout":
        return list(splits.prompt_holdout_folds)
    raise ValueError(f"Unknown split scheme: {scheme}")


def filter_by_word_count(
    records: list[EssayRecord], *, min_words: int, max_words: int
) -> list[EssayRecord]:
    filtered = []
    for record in records:
        wc = count_words(record.essay)
        if min_words <= wc <= max_words:
            filtered.append(record)
    return filtered


def raise_on_overlap(*, train_records: list[EssayRecord], test_records: list[EssayRecord]) -> None:
    train_hashes = {
        sha256_text(normalize_text_for_hashing(record.essay)) for record in train_records
    }
    overlap = [
        record.record_id
        for record in test_records
        if sha256_text(normalize_text_for_hashing(record.essay)) in train_hashes
    ]
    if overlap:
        raise ValueError(
            "Train/test leakage detected after filtering: "
            f"{len(overlap)} test records share identical essay text with train."
        )


def validate_splits_compatibility(
    *,
    config: ExperimentConfig,
    splits: SplitDefinitions,
    min_words: int | None,
    max_words: int | None,
) -> None:
    if splits.schema_version != 1:
        raise ValueError(f"Unsupported splits schema_version={splits.schema_version}")

    if splits.dataset_kind != config.dataset_kind:
        raise ValueError(
            "Split dataset_kind mismatch "
            f"splits={splits.dataset_kind.value} config={config.dataset_kind.value}"
        )

    if config.dataset_kind != DatasetKind.ELLIPSE:
        raise ValueError("Splits compatibility validator currently supports only ellipse")

    expected_sha = {
        "ellipse_train": sha256_file(config.ellipse_train_path),
        "ellipse_test": sha256_file(config.ellipse_test_path),
    }
    if splits.dataset_sha256 != expected_sha:
        raise ValueError(
            "Split definitions dataset fingerprint mismatch "
            f"expected={expected_sha} splits={splits.dataset_sha256}"
        )

    expected_excluded = sorted(config.ellipse_excluded_prompts)
    if splits.dataset_excluded_prompts != expected_excluded:
        raise ValueError(
            "Split definitions excluded prompt mismatch "
            f"expected={expected_excluded} splits={splits.dataset_excluded_prompts}"
        )

    if min_words is not None and int(min_words) != int(splits.word_count_window["min"]):
        raise ValueError(
            "Split definitions min_words mismatch "
            f"expected={splits.word_count_window['min']} got={min_words}"
        )
    if max_words is not None and int(max_words) != int(splits.word_count_window["max"]):
        raise ValueError(
            "Split definitions max_words mismatch "
            f"expected={splits.word_count_window['max']} got={max_words}"
        )


def validate_record_ids_against_splits(
    *,
    splits: SplitDefinitions,
    train_records: list[EssayRecord],
    test_records: list[EssayRecord],
) -> None:
    expected_test = set(splits.test_record_ids)
    actual_test = {record.record_id for record in test_records}
    if expected_test != actual_test:
        raise ValueError(
            "Split definitions test_record_ids mismatch after filtering "
            f"expected={len(expected_test)} got={len(actual_test)}"
        )

    fold_val_ids: set[str] = set()
    fold_train_ids: set[str] = set()
    for fold in splits.stratified_text_folds + splits.prompt_holdout_folds:
        fold_val_ids.update(fold.val_record_ids)
        fold_train_ids.update(fold.train_record_ids)

    actual_train = {record.record_id for record in train_records}
    if not fold_val_ids.issubset(actual_train):
        raise ValueError(
            "Split definitions contain val_record_ids not present in the filtered train set."
        )
    if not fold_train_ids.issubset(actual_train):
        raise ValueError(
            "Split definitions contain train_record_ids not present in the filtered train set."
        )


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
