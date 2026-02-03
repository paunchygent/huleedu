"""Drop-column importance for handcrafted features (CV wrapper)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.cv_feature_store import load_cv_feature_store
from scripts.ml_training.essay_scoring.cv_shared import (
    SplitScheme,
    filter_by_word_count,
    prepare_cv_feature_store,
    raise_on_overlap,
    run_fold,
    select_folds,
    validate_record_ids_against_splits,
    validate_splits_compatibility,
)
from scripts.ml_training.essay_scoring.dataset import load_ellipse_train_test_dataset
from scripts.ml_training.essay_scoring.features.schema import (
    TIER1_FEATURE_NAMES,
    TIER2_FEATURE_NAMES,
    TIER3_FEATURE_NAMES,
)
from scripts.ml_training.essay_scoring.logging_utils import run_file_logger
from scripts.ml_training.essay_scoring.paths import RunPaths, build_run_paths
from scripts.ml_training.essay_scoring.split_definitions import load_splits

logger = logging.getLogger(__name__)

_DROP_COLUMN_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class DropColumnSummary:
    run_paths: RunPaths
    cv_feature_store_dir: Path
    metrics_path: Path
    report_path: Path


def run_drop_column_importance(
    config: ExperimentConfig,
    *,
    feature_set: FeatureSet,
    splits_path: Path,
    scheme: SplitScheme,
    reuse_cv_feature_store_dir: Path | None = None,
    min_words: int | None = None,
    max_words: int | None = None,
) -> DropColumnSummary:
    """Compute drop-column importance deltas for Tier1-3 features.

    Interpretation:
    - ΔQWK = baseline_qwk - dropped_qwk (positive means the feature helps).
    - ΔMAE = dropped_mae - baseline_mae (positive means the feature helps).
    """

    if config.dataset_kind != DatasetKind.ELLIPSE:
        raise ValueError("drop-column currently supports only --dataset-kind=ellipse")
    if feature_set == FeatureSet.EMBEDDINGS:
        raise ValueError("drop-column requires handcrafted features (use combined or handcrafted).")

    splits = load_splits(splits_path)
    validate_splits_compatibility(
        config=config, splits=splits, min_words=min_words, max_words=max_words
    )

    min_words = int(splits.word_count_window["min"])
    max_words = int(splits.word_count_window["max"])
    word_window = {"min": min_words, "max": max_words}

    run_paths = build_run_paths(config.output)
    metrics_path = run_paths.artifacts_dir / "drop_column_importance.json"
    report_path = run_paths.reports_dir / "drop_column_importance.md"

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

        baseline_start = time.monotonic()
        baseline_folds = [
            run_fold(
                fold=fold,
                train_id_to_idx=train_id_to_idx,
                features=store.train_features,
                y=store.y_train,
                config=config,
                min_band=min_band,
                max_band=max_band,
                keep_feature_indices=None,
            )
            for fold in folds
        ]
        baseline_elapsed = time.monotonic() - baseline_start

        candidate_features = _candidate_handcrafted_features(store.train_features.feature_names)
        feature_name_to_idx = {
            name: idx for idx, name in enumerate(store.train_features.feature_names)
        }

        start = time.monotonic()
        per_feature: list[dict[str, Any]] = []
        for feature_name in candidate_features:
            drop_idx = feature_name_to_idx[feature_name]
            keep_indices = [
                idx for idx in range(len(store.train_features.feature_names)) if idx != drop_idx
            ]

            deltas_qwk: list[float] = []
            deltas_mae: list[float] = []
            deltas_adj: list[float] = []
            fold_payloads: list[dict[str, Any]] = []

            for fold, baseline in zip(folds, baseline_folds, strict=True):
                dropped = run_fold(
                    fold=fold,
                    train_id_to_idx=train_id_to_idx,
                    features=store.train_features,
                    y=store.y_train,
                    config=config,
                    min_band=min_band,
                    max_band=max_band,
                    keep_feature_indices=keep_indices,
                )

                baseline_val = baseline["val"]
                dropped_val = dropped["val"]

                delta_qwk = float(baseline_val["qwk"] - dropped_val["qwk"])
                delta_mae = float(
                    dropped_val["mean_absolute_error"] - baseline_val["mean_absolute_error"]
                )
                delta_adj = float(
                    baseline_val["adjacent_accuracy"] - dropped_val["adjacent_accuracy"]
                )

                deltas_qwk.append(delta_qwk)
                deltas_mae.append(delta_mae)
                deltas_adj.append(delta_adj)
                fold_payloads.append(
                    {
                        "fold": int(fold.fold),
                        "baseline_val": dict(baseline_val),
                        "dropped_val": dict(dropped_val),
                        "delta": {
                            "qwk": delta_qwk,
                            "mean_absolute_error": delta_mae,
                            "adjacent_accuracy": delta_adj,
                        },
                    }
                )

            per_feature.append(
                _summarize_deltas(
                    feature_name=feature_name,
                    deltas_qwk=np.array(deltas_qwk, dtype=float),
                    deltas_mae=np.array(deltas_mae, dtype=float),
                    deltas_adj=np.array(deltas_adj, dtype=float),
                    folds=fold_payloads,
                )
            )

        elapsed = time.monotonic() - start

        payload: dict[str, Any] = {
            "schema_version": _DROP_COLUMN_SCHEMA_VERSION,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "dataset_kind": config.dataset_kind.value,
            "feature_set": feature_set.value,
            "scheme": scheme,
            "n_splits": splits.n_splits,
            "word_count_window": word_window,
            "record_counts": {"train": len(train_records), "test": len(test_records)},
            "cv_feature_store_dir": str(cv_store_dir),
            "baseline": {
                "folds": baseline_folds,
                "summary": _summarize_baseline(baseline_folds),
                "elapsed_s": float(baseline_elapsed),
            },
            "handcrafted_features": per_feature,
            "elapsed_s": float(elapsed),
        }

        metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        report_path.write_text(_build_report(payload), encoding="utf-8")

        logger.info("Drop-column importance complete: %s", run_paths.run_dir)

    return DropColumnSummary(
        run_paths=run_paths,
        cv_feature_store_dir=cv_store_dir,
        metrics_path=metrics_path,
        report_path=report_path,
    )


def _candidate_handcrafted_features(feature_names: list[str]) -> list[str]:
    handcrafted = list(TIER1_FEATURE_NAMES) + list(TIER2_FEATURE_NAMES) + list(TIER3_FEATURE_NAMES)
    return [name for name in handcrafted if name in feature_names]


def _summarize_baseline(folds: list[dict[str, Any]]) -> dict[str, float]:
    val_qwk = np.array([float(fold["val"]["qwk"]) for fold in folds], dtype=float)
    val_mae = np.array([float(fold["val"]["mean_absolute_error"]) for fold in folds], dtype=float)
    val_adj = np.array([float(fold["val"]["adjacent_accuracy"]) for fold in folds], dtype=float)
    return {
        "val_qwk_mean": float(np.mean(val_qwk)) if len(val_qwk) else 0.0,
        "val_qwk_std": float(np.std(val_qwk)) if len(val_qwk) else 0.0,
        "val_mae_mean": float(np.mean(val_mae)) if len(val_mae) else 0.0,
        "val_mae_std": float(np.std(val_mae)) if len(val_mae) else 0.0,
        "val_adjacent_accuracy_mean": float(np.mean(val_adj)) if len(val_adj) else 0.0,
        "val_adjacent_accuracy_std": float(np.std(val_adj)) if len(val_adj) else 0.0,
    }


def _summarize_deltas(
    *,
    feature_name: str,
    deltas_qwk: np.ndarray,
    deltas_mae: np.ndarray,
    deltas_adj: np.ndarray,
    folds: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "feature": feature_name,
        "deltas": {
            "qwk": _delta_stats(deltas_qwk),
            "mean_absolute_error": _delta_stats(deltas_mae),
            "adjacent_accuracy": _delta_stats(deltas_adj),
        },
        "stability": {
            "qwk_positive_fraction": float(np.mean(deltas_qwk > 0.0)) if len(deltas_qwk) else 0.0,
            "mae_positive_fraction": float(np.mean(deltas_mae > 0.0)) if len(deltas_mae) else 0.0,
            "adjacent_positive_fraction": float(np.mean(deltas_adj > 0.0))
            if len(deltas_adj)
            else 0.0,
        },
        "folds": folds,
    }


def _delta_stats(values: np.ndarray) -> dict[str, Any]:
    return {
        "mean": float(np.mean(values)) if len(values) else 0.0,
        "std": float(np.std(values)) if len(values) else 0.0,
        "per_fold": [float(v) for v in values.tolist()],
    }


def _build_report(payload: dict[str, Any]) -> str:
    baseline_summary = payload.get("baseline", {}).get("summary", {})
    features = payload.get("handcrafted_features", [])
    elapsed = float(payload.get("elapsed_s", 0.0))

    qwk_mean = float(baseline_summary.get("val_qwk_mean", 0.0))
    qwk_std = float(baseline_summary.get("val_qwk_std", 0.0))
    mae_mean = float(baseline_summary.get("val_mae_mean", 0.0))
    mae_std = float(baseline_summary.get("val_mae_std", 0.0))
    adj_mean = float(baseline_summary.get("val_adjacent_accuracy_mean", 0.0))
    adj_std = float(baseline_summary.get("val_adjacent_accuracy_std", 0.0))

    rows: list[tuple[str, ...]] = [
        (
            "feature",
            "Δqwk_mean±std",
            "Δmae_mean±std",
            "qwk_stability",
            "mae_stability",
        )
    ]
    for entry in sorted(
        features,
        key=lambda item: float(item["deltas"]["qwk"]["mean"]),
        reverse=True,
    ):
        dq = entry["deltas"]["qwk"]
        dm = entry["deltas"]["mean_absolute_error"]
        rows.append(
            (
                str(entry["feature"]),
                f"{float(dq['mean']):.4f} ± {float(dq['std']):.4f}",
                f"{float(dm['mean']):.4f} ± {float(dm['std']):.4f}",
                f"{float(entry['stability']['qwk_positive_fraction']):.2f}",
                f"{float(entry['stability']['mae_positive_fraction']):.2f}",
            )
        )

    table = _md_table(rows)
    return "\n".join(
        [
            "# Drop-Column Importance (Handcrafted Features)",
            "",
            "## Summary",
            "",
            f"- dataset_kind: `{payload.get('dataset_kind')}`",
            f"- feature_set: `{payload.get('feature_set')}`",
            f"- scheme: `{payload.get('scheme')}`",
            f"- n_splits: `{payload.get('n_splits')}`",
            f"- word_count_window: `{payload.get('word_count_window')}`",
            f"- records: `{payload.get('record_counts')}`",
            f"- elapsed_s: `{elapsed:.1f}`",
            "",
            "## Baseline (val)",
            "",
            f"- qwk_mean±std: `{qwk_mean:.4f}` ± `{qwk_std:.4f}`",
            f"- mae_mean±std: `{mae_mean:.4f}` ± `{mae_std:.4f}`",
            f"- adjacent_acc_mean±std: `{adj_mean:.4f}` ± `{adj_std:.4f}`",
            "",
            "## Drop-Column Deltas (val)",
            "",
            "Interpretation: positive deltas mean the feature helps "
            "(removing it makes metrics worse).",
            "",
            table,
            "",
        ]
    )


def _md_table(rows: list[tuple[str, ...]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)
