"""Cross-validation runner for the essay scoring research pipeline."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.cv_feature_store import (
    load_cv_feature_store,
)
from scripts.ml_training.essay_scoring.cv_shared import (
    SplitScheme,
    filter_by_word_count,
    indices_for_ids,
    prepare_cv_feature_store,
    raise_on_overlap,
    run_fold,
    select_folds,
    validate_record_ids_against_splits,
    validate_splits_compatibility,
)
from scripts.ml_training.essay_scoring.dataset import (
    EssayDataset,
    EssayRecord,
    load_ellipse_train_test_dataset,
)
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.logging_utils import run_file_logger
from scripts.ml_training.essay_scoring.paths import RunPaths, build_run_paths
from scripts.ml_training.essay_scoring.split_definitions import (
    load_splits,
)
from scripts.ml_training.essay_scoring.splitters import DatasetSplit, stratified_split
from scripts.ml_training.essay_scoring.training.evaluation import evaluate_predictions
from scripts.ml_training.essay_scoring.training.trainer import train_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrossValidationSummary:
    run_paths: RunPaths
    cv_feature_store_dir: Path
    metrics_path: Path
    report_path: Path


def run_cross_validation(
    config: ExperimentConfig,
    *,
    feature_set: FeatureSet,
    splits_path: Path,
    scheme: SplitScheme,
    reuse_cv_feature_store_dir: Path | None = None,
    min_words: int | None = None,
    max_words: int | None = None,
) -> CrossValidationSummary:
    """Run cross-validation for ELLIPSE using reusable split definitions."""

    if config.dataset_kind != DatasetKind.ELLIPSE:
        raise ValueError("cv currently supports only --dataset-kind=ellipse")

    splits = load_splits(splits_path)
    validate_splits_compatibility(
        config=config, splits=splits, min_words=min_words, max_words=max_words
    )

    min_words = int(splits.word_count_window["min"])
    max_words = int(splits.word_count_window["max"])
    word_window = {"min": min_words, "max": max_words}

    run_paths = build_run_paths(config.output)
    metrics_path = run_paths.artifacts_dir / "cv_metrics.json"
    report_path = run_paths.reports_dir / "cv_report.md"

    with run_file_logger(run_paths.log_path):
        dataset = load_ellipse_train_test_dataset(
            config.ellipse_train_path,
            config.ellipse_test_path,
            excluded_prompts=set(config.ellipse_excluded_prompts),
        )

        train_records = filter_by_word_count(
            dataset.train_records, min_words=min_words, max_words=max_words
        )
        test_records = filter_by_word_count(
            dataset.test_records, min_words=min_words, max_words=max_words
        )
        raise_on_overlap(train_records=train_records, test_records=test_records)

        validate_record_ids_against_splits(
            splits=splits,
            train_records=train_records,
            test_records=test_records,
        )

        cv_store_dir = prepare_cv_feature_store(
            config=config,
            run_dir=run_paths.run_dir,
            feature_set=feature_set,
            word_window=word_window,
            train_records=train_records,
            test_records=test_records,
            reuse_store_dir=reuse_cv_feature_store_dir,
        )
        store = load_cv_feature_store(
            store_dir=cv_store_dir,
            expected_config=config,
            expected_feature_set=feature_set,
            expected_word_count_window=word_window,
        )

        folds = select_folds(splits, scheme=scheme)
        train_id_to_idx = {rid: idx for idx, rid in enumerate(store.manifest.train_record_ids)}

        min_band = float(np.min(store.y_train))
        max_band = float(np.max(store.y_train))

        fold_results: list[dict[str, Any]] = []
        fold_val_qwk: list[float] = []
        fold_val_mae: list[float] = []
        fold_val_adj: list[float] = []

        start = time.monotonic()
        for fold in folds:
            fold_result = run_fold(
                fold=fold,
                train_id_to_idx=train_id_to_idx,
                features=store.train_features,
                y=store.y_train,
                config=config,
                min_band=min_band,
                max_band=max_band,
                keep_feature_indices=None,
            )
            fold_results.append(fold_result)
            fold_val_qwk.append(float(fold_result["val"]["qwk"]))
            fold_val_mae.append(float(fold_result["val"]["mean_absolute_error"]))
            fold_val_adj.append(float(fold_result["val"]["adjacent_accuracy"]))

        elapsed = time.monotonic() - start
        summary = {
            "val_qwk_mean": float(np.mean(fold_val_qwk)) if fold_val_qwk else 0.0,
            "val_qwk_std": float(np.std(fold_val_qwk)) if fold_val_qwk else 0.0,
            "val_mae_mean": float(np.mean(fold_val_mae)) if fold_val_mae else 0.0,
            "val_mae_std": float(np.std(fold_val_mae)) if fold_val_mae else 0.0,
            "val_adjacent_accuracy_mean": float(np.mean(fold_val_adj)) if fold_val_adj else 0.0,
            "val_adjacent_accuracy_std": float(np.std(fold_val_adj)) if fold_val_adj else 0.0,
            "elapsed_s": float(elapsed),
        }

        final_eval = _run_final_train_and_test_eval(
            train_records=train_records,
            test_records=test_records,
            train_id_to_idx=train_id_to_idx,
            train_features=store.train_features,
            y_train=store.y_train,
            test_features=store.test_features,
            y_test=store.y_test,
            config=config,
            min_band=min_band,
            max_band=max_band,
        )

        payload: dict[str, Any] = {
            "schema_version": 1,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "dataset_kind": config.dataset_kind.value,
            "feature_set": feature_set.value,
            "scheme": scheme,
            "n_splits": splits.n_splits,
            "word_count_window": word_window,
            "record_counts": {"train": len(train_records), "test": len(test_records)},
            "cv_feature_store_dir": str(cv_store_dir),
            "folds": fold_results,
            "summary": summary,
            "final_train_val_test": final_eval,
        }
        metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        report_md = _build_cv_report(payload)
        report_path.write_text(report_md, encoding="utf-8")

        logger.info("CV complete: %s", run_paths.run_dir)

    return CrossValidationSummary(
        run_paths=run_paths,
        cv_feature_store_dir=cv_store_dir,
        metrics_path=metrics_path,
        report_path=report_path,
    )


def _run_final_train_and_test_eval(
    *,
    train_records: list[EssayRecord],
    test_records: list[EssayRecord],
    train_id_to_idx: dict[str, int],
    train_features: FeatureMatrix,
    y_train: np.ndarray,
    test_features: FeatureMatrix,
    y_test: np.ndarray,
    config: ExperimentConfig,
    min_band: float,
    max_band: float,
) -> dict[str, Any]:
    split = _train_val_split(train_records, config=config)
    train_ids = [record.record_id for record in split.train]
    val_ids = [record.record_id for record in split.val]

    train_idx = indices_for_ids(train_ids, id_to_idx=train_id_to_idx)
    val_idx = indices_for_ids(val_ids, id_to_idx=train_id_to_idx)

    feature_names = list(train_features.feature_names)
    train_mat = train_features.matrix[train_idx]
    val_mat = train_features.matrix[val_idx]

    artifacts = train_model(
        FeatureMatrix(matrix=train_mat, feature_names=feature_names),
        FeatureMatrix(matrix=val_mat, feature_names=feature_names),
        y_train[train_idx],
        y_train[val_idx],
        config.training,
        min_band=min_band,
        max_band=max_band,
    )

    dval = xgb.DMatrix(val_mat, feature_names=feature_names)
    dtest = xgb.DMatrix(test_features.matrix, feature_names=feature_names)
    pred_val = artifacts.model.predict(dval)
    pred_test = artifacts.model.predict(dtest)

    eval_val = evaluate_predictions(
        y_train[val_idx],
        pred_val,
        min_band=min_band,
        max_band=max_band,
    )
    eval_test = evaluate_predictions(
        y_test,
        pred_test,
        min_band=min_band,
        max_band=max_band,
    )

    return {
        "train_val_split": {"train": len(split.train), "val": len(split.val), "test": 0},
        "val": {
            "qwk": float(eval_val.qwk),
            "adjacent_accuracy": float(eval_val.adjacent_accuracy),
            "mean_absolute_error": float(eval_val.mean_absolute_error),
        },
        "test": {
            "qwk": float(eval_test.qwk),
            "adjacent_accuracy": float(eval_test.adjacent_accuracy),
            "mean_absolute_error": float(eval_test.mean_absolute_error),
        },
        "test_record_count": len(test_records),
        "best_iteration": int(artifacts.best_iteration),
    }


def _train_val_split(records: list[EssayRecord], *, config: ExperimentConfig) -> DatasetSplit:
    train_plus_val = config.training.train_ratio + config.training.val_ratio
    if train_plus_val <= 0:
        raise ValueError("Training config must have a non-zero train+val ratio for CV final fit.")

    split_config = config.training.model_copy(
        update={
            "train_ratio": config.training.train_ratio / train_plus_val,
            "val_ratio": config.training.val_ratio / train_plus_val,
            "test_ratio": 0.0,
        }
    )
    return stratified_split(EssayDataset(records=list(records)), split_config)


def _build_cv_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    folds = payload.get("folds", [])
    final_eval = payload.get("final_train_val_test", {})

    qwk_mean = float(summary.get("val_qwk_mean", 0.0))
    qwk_std = float(summary.get("val_qwk_std", 0.0))
    mae_mean = float(summary.get("val_mae_mean", 0.0))
    mae_std = float(summary.get("val_mae_std", 0.0))
    adj_mean = float(summary.get("val_adjacent_accuracy_mean", 0.0))
    adj_std = float(summary.get("val_adjacent_accuracy_std", 0.0))
    elapsed_s = float(summary.get("elapsed_s", 0.0))

    lines = [
        "# Cross-Validation Report",
        "",
        "## Summary",
        "",
        f"- dataset_kind: `{payload.get('dataset_kind')}`",
        f"- feature_set: `{payload.get('feature_set')}`",
        f"- scheme: `{payload.get('scheme')}`",
        f"- n_splits: `{payload.get('n_splits')}`",
        f"- word_count_window: `{payload.get('word_count_window')}`",
        f"- records: `{payload.get('record_counts')}`",
        "",
        "## CV Metrics (val)",
        "",
        f"- qwk_mean±std: `{qwk_mean:.4f}` ± `{qwk_std:.4f}`",
        f"- mae_mean±std: `{mae_mean:.4f}` ± `{mae_std:.4f}`",
        f"- adjacent_acc_mean±std: `{adj_mean:.4f}` ± `{adj_std:.4f}`",
        f"- elapsed_s: `{elapsed_s:.1f}`",
        "",
        "## Folds",
        "",
        _fold_table(folds),
        "",
        "## Final (single split) + Locked Test",
        "",
        _final_table(final_eval),
        "",
    ]
    return "\n".join(lines)


def _fold_table(folds: list[dict[str, Any]]) -> str:
    rows: list[tuple[str, ...]] = [("fold", "train", "val", "val_qwk", "val_mae", "best_iter")]
    for fold in folds:
        rows.append(
            (
                str(fold.get("fold")),
                str((fold.get("sizes") or {}).get("train")),
                str((fold.get("sizes") or {}).get("val")),
                f"{(fold.get('val') or {}).get('qwk', 0.0):.4f}",
                f"{(fold.get('val') or {}).get('mean_absolute_error', 0.0):.4f}",
                str(fold.get("best_iteration")),
            )
        )
    return _markdown_table(rows)


def _final_table(final_eval: dict[str, Any]) -> str:
    rows: list[tuple[str, ...]] = [
        ("split", "qwk", "mae", "adjacent_acc"),
        (
            "val",
            f"{(final_eval.get('val') or {}).get('qwk', 0.0):.4f}",
            f"{(final_eval.get('val') or {}).get('mean_absolute_error', 0.0):.4f}",
            f"{(final_eval.get('val') or {}).get('adjacent_accuracy', 0.0):.4f}",
        ),
        (
            "test",
            f"{(final_eval.get('test') or {}).get('qwk', 0.0):.4f}",
            f"{(final_eval.get('test') or {}).get('mean_absolute_error', 0.0):.4f}",
            f"{(final_eval.get('test') or {}).get('adjacent_accuracy', 0.0):.4f}",
        ),
    ]
    return _markdown_table(rows)


def _markdown_table(rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return ""
    headers = rows[0]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows[1:]:
        escaped = [cell.replace("\n", " ").replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(escaped) + " |")
    return "\n".join(lines)
