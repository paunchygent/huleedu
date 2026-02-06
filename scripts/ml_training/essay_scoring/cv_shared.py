"""Shared helpers for CV-style essay scoring workflows.

Purpose:
    Centralize utilities that are shared across CV-style experiment runners (feature store
    preparation/reuse, fold training/evaluation, split validation, and leakage guards).

Relationships:
    - Used by `scripts.ml_training.essay_scoring.cross_validation`.
    - Produces fold-level results that are later persisted as metrics artifacts.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.config import (
    DatasetKind,
    ExperimentConfig,
    FeatureSet,
    TrainingConfig,
)
from scripts.ml_training.essay_scoring.cv_feature_store import (
    persist_cv_feature_store,
    resolve_cv_feature_store_dir,
)
from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.features.pipeline import FeaturePipeline
from scripts.ml_training.essay_scoring.logging_utils import ProgressWriter, stage_timer
from scripts.ml_training.essay_scoring.offload.extract_models import ExtractMeta
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
from scripts.ml_training.essay_scoring.training.grade_band_weighting import (
    GradeBandWeighting,
    compute_grade_band_sample_weights,
)
from scripts.ml_training.essay_scoring.training.trainer import train_model
from scripts.ml_training.essay_scoring.training.training_modes import (
    TrainingMode,
    decode_predictions,
)

logger = logging.getLogger(__name__)

SplitScheme = Literal["stratified_text", "prompt_holdout"]


class FoldSizes(TypedDict):
    """Train/validation record counts for a CV fold."""

    train: int
    val: int


class FoldEval(TypedDict):
    """Evaluation metrics for a single split (train/val)."""

    qwk: float
    adjacent_accuracy: float
    mean_absolute_error: float


class FoldResult(TypedDict):
    """Fold-level training and evaluation summary."""

    fold: int
    sizes: FoldSizes
    best_iteration: int
    train: FoldEval
    val: FoldEval


@dataclass(frozen=True)
class FoldPredictions:
    """Fold training outputs needed for residual diagnostics."""

    fold_result: FoldResult
    val_record_ids: list[str]
    val_indices: np.ndarray
    val_true: np.ndarray
    val_pred_raw: np.ndarray


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
    progress = ProgressWriter(run_dir)
    benchmarks: list[ExtractionBenchmark] = []
    logger.info("Extracting train features (n=%d)", len(train_records))
    with stage_timer(
        run_dir,
        logger,
        "cv_feature_store_train_extract",
        records=len(train_records),
        feature_set=feature_set.value,
    ):
        start = time.monotonic()
        train_features = pipeline.extract(train_records, feature_set, progress=progress)
        elapsed = time.monotonic() - start
    benchmarks.append(
        ExtractionBenchmark(
            mode="cv_feature_store_train_extract",
            records_processed=len(train_records),
            elapsed_s=elapsed,
        )
    )
    logger.info("Extracting test features (n=%d)", len(test_records))
    with stage_timer(
        run_dir,
        logger,
        "cv_feature_store_test_extract",
        records=len(test_records),
        feature_set=feature_set.value,
    ):
        start = time.monotonic()
        test_features = pipeline.extract(test_records, feature_set, progress=progress)
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
    _persist_offload_extract_meta(run_dir / "artifacts", pipeline.last_offload_meta)

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
    training_mode: TrainingMode = TrainingMode.REGRESSION,
    grade_band_weighting: GradeBandWeighting = GradeBandWeighting.NONE,
    grade_band_weight_cap: float = 3.0,
) -> FoldResult:
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

    sample_weight_train = compute_grade_band_sample_weights(
        y[train_idx],
        mode=grade_band_weighting,
        cap=grade_band_weight_cap,
    )

    model, best_iteration = _train_xgboost_model(
        train_matrix=train_matrix,
        val_matrix=val_matrix,
        feature_names=feature_names,
        y_train=y[train_idx],
        y_val=y[val_idx],
        training_config=config.training,
        training_mode=training_mode,
        sample_weight_train=sample_weight_train,
        min_band=min_band,
        max_band=max_band,
    )
    pred_train = decode_predictions(
        _predict_raw_with_xgboost(
            model=model,
            matrix=train_matrix,
            feature_names=feature_names,
        ),
        min_band=min_band,
        max_band=max_band,
        mode=training_mode,
    )
    pred_val = decode_predictions(
        _predict_raw_with_xgboost(
            model=model,
            matrix=val_matrix,
            feature_names=feature_names,
        ),
        min_band=min_band,
        max_band=max_band,
        mode=training_mode,
    )

    eval_train = evaluate_predictions(
        y[train_idx], pred_train, min_band=min_band, max_band=max_band
    )
    eval_val = evaluate_predictions(y[val_idx], pred_val, min_band=min_band, max_band=max_band)

    return {
        "fold": int(fold.fold),
        "sizes": {"train": int(train_idx.size), "val": int(val_idx.size)},
        "best_iteration": int(best_iteration),
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


def run_fold_with_predictions(
    *,
    fold: FoldDefinition,
    train_id_to_idx: dict[str, int],
    features: FeatureMatrix,
    y: np.ndarray,
    config: ExperimentConfig,
    member_seeds: list[int] | None = None,
    min_band: float,
    max_band: float,
    keep_feature_indices: list[int] | None,
    training_mode: TrainingMode = TrainingMode.REGRESSION,
    grade_band_weighting: GradeBandWeighting = GradeBandWeighting.NONE,
    grade_band_weight_cap: float = 3.0,
) -> FoldPredictions:
    """Train and evaluate a fold while returning raw val predictions.

    Args:
        fold: Fold definition with train/val record ids.
        train_id_to_idx: Mapping of record_id -> feature row index.
        features: Full train feature matrix.
        y: Train labels aligned with `features`.
        config: Experiment config (training params).
        member_seeds: Optional list of per-model random seeds to ensemble across within this fold.
            When provided, trains one XGBoost model per seed and averages their raw predictions
            before decoding/evaluation. When omitted, trains a single model using
            `config.training.random_seed`.
        min_band: Minimum valid score band.
        max_band: Maximum valid score band.
        keep_feature_indices: Optional list of feature indices to keep.

    Returns:
        FoldPredictions containing fold metrics and the raw validation predictions.
    """

    train_idx = indices_for_ids(fold.train_record_ids, id_to_idx=train_id_to_idx)
    val_idx = indices_for_ids(fold.val_record_ids, id_to_idx=train_id_to_idx)

    train_matrix = features.matrix[train_idx]
    val_matrix = features.matrix[val_idx]
    feature_names = list(features.feature_names)

    if keep_feature_indices is not None:
        feature_names = [feature_names[idx] for idx in keep_feature_indices]
        train_matrix = train_matrix[:, keep_feature_indices]
        val_matrix = val_matrix[:, keep_feature_indices]

    sample_weight_train = compute_grade_band_sample_weights(
        y[train_idx],
        mode=grade_band_weighting,
        cap=grade_band_weight_cap,
    )

    seeds = member_seeds or [int(config.training.random_seed)]
    if not seeds:
        raise ValueError("member_seeds must be non-empty when provided.")

    member_best_iterations: list[int] = []
    member_predt_train: list[np.ndarray] = []
    member_predt_val: list[np.ndarray] = []
    for seed in seeds:
        training_config = config.training.model_copy(update={"random_seed": int(seed)})
        model, best_iteration = _train_xgboost_model(
            train_matrix=train_matrix,
            val_matrix=val_matrix,
            feature_names=feature_names,
            y_train=y[train_idx],
            y_val=y[val_idx],
            training_config=training_config,
            training_mode=training_mode,
            sample_weight_train=sample_weight_train,
            min_band=min_band,
            max_band=max_band,
        )
        member_best_iterations.append(int(best_iteration))
        member_predt_train.append(
            _predict_raw_with_xgboost(
                model=model,
                matrix=train_matrix,
                feature_names=feature_names,
            )
        )
        member_predt_val.append(
            _predict_raw_with_xgboost(
                model=model,
                matrix=val_matrix,
                feature_names=feature_names,
            )
        )

    best_iteration = (
        int(round(float(np.mean(member_best_iterations)))) if member_best_iterations else 0
    )
    predt_train = np.mean(np.stack(member_predt_train, axis=0), axis=0)
    predt_val = np.mean(np.stack(member_predt_val, axis=0), axis=0)

    pred_train = decode_predictions(
        predt_train,
        min_band=min_band,
        max_band=max_band,
        mode=training_mode,
    )
    pred_val = decode_predictions(
        predt_val,
        min_band=min_band,
        max_band=max_band,
        mode=training_mode,
    )

    eval_train = evaluate_predictions(
        y[train_idx], pred_train, min_band=min_band, max_band=max_band
    )
    eval_val = evaluate_predictions(y[val_idx], pred_val, min_band=min_band, max_band=max_band)

    fold_result: FoldResult = {
        "fold": int(fold.fold),
        "sizes": {"train": int(train_idx.size), "val": int(val_idx.size)},
        "best_iteration": best_iteration,
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
    return FoldPredictions(
        fold_result=fold_result,
        val_record_ids=list(fold.val_record_ids),
        val_indices=val_idx,
        val_true=y[val_idx].astype(float),
        val_pred_raw=pred_val,
    )


def _train_xgboost_model(
    *,
    train_matrix: np.ndarray,
    val_matrix: np.ndarray,
    feature_names: list[str],
    y_train: np.ndarray,
    y_val: np.ndarray,
    training_config: TrainingConfig,
    training_mode: TrainingMode,
    sample_weight_train: np.ndarray | None,
    min_band: float,
    max_band: float,
) -> tuple[xgb.Booster, int]:
    """Train one XGBoost model and return `(model, best_iteration)`."""

    artifacts = train_model(
        FeatureMatrix(matrix=train_matrix, feature_names=feature_names),
        FeatureMatrix(matrix=val_matrix, feature_names=feature_names),
        y_train,
        y_val,
        training_config,
        min_band=min_band,
        max_band=max_band,
        training_mode=training_mode,
        sample_weight_train=sample_weight_train,
    )
    return artifacts.model, int(artifacts.best_iteration)


def _predict_raw_with_xgboost(
    *,
    model: xgb.Booster,
    matrix: np.ndarray,
    feature_names: list[str],
) -> np.ndarray:
    """Predict raw score values from an XGBoost model."""

    dmatrix = xgb.DMatrix(matrix, feature_names=feature_names)
    return np.asarray(model.predict(dmatrix))


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


def _persist_offload_extract_meta(artifacts_dir: Path, meta: ExtractMeta | None) -> None:
    if meta is None:
        return
    try:
        json_text = meta.model_dump_json(indent=2)
    except Exception:
        return
    (artifacts_dir / "offload_extract_meta.json").write_text(json_text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
