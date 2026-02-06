"""Cross-validation runner for the essay scoring research pipeline.

Purpose:
    Execute K-fold cross-validation (CV) for ELLIPSE using precomputed split definitions, while
    producing machine-readable metrics artifacts plus a human-readable Markdown report.

Relationships:
    - Uses split definitions from `scripts.ml_training.essay_scoring.split_definitions`.
    - Trains/evaluates folds via helpers in `scripts.ml_training.essay_scoring.cv_shared`.
    - Persists metrics under the run directory managed by `scripts.ml_training.essay_scoring.paths`.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.cv_feature_store import (
    load_cv_feature_store,
)
from scripts.ml_training.essay_scoring.cv_shared import (
    FoldPredictions,
    FoldResult,
    SplitScheme,
    filter_by_word_count,
    indices_for_ids,
    prepare_cv_feature_store,
    raise_on_overlap,
    run_fold_with_predictions,
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
from scripts.ml_training.essay_scoring.logging_utils import (
    ProgressWriter,
    run_file_logger,
    stage_timer,
)
from scripts.ml_training.essay_scoring.paths import RunPaths, build_run_paths
from scripts.ml_training.essay_scoring.reports.cv_report import build_cv_report
from scripts.ml_training.essay_scoring.reports.residual_diagnostics import (
    build_residual_frame,
    generate_residual_diagnostics_report,
    persist_residual_artifacts,
)
from scripts.ml_training.essay_scoring.split_definitions import (
    load_splits,
)
from scripts.ml_training.essay_scoring.splitters import DatasetSplit, stratified_split
from scripts.ml_training.essay_scoring.training.evaluation import evaluate_predictions
from scripts.ml_training.essay_scoring.training.feature_selection import (
    feature_selection_summary,
    resolve_keep_feature_indices,
)
from scripts.ml_training.essay_scoring.training.grade_band_weighting import (
    GradeBandWeighting,
    compute_grade_band_sample_weights,
)
from scripts.ml_training.essay_scoring.training.prediction_mapping import (
    PredictionMapping,
    apply_cutpoints,
    fit_qwk_cutpoints_coordinate_ascent,
    half_band_values,
)
from scripts.ml_training.essay_scoring.training.trainer import train_model
from scripts.ml_training.essay_scoring.training.training_modes import (
    TrainingMode,
    decode_predictions,
)

logger = logging.getLogger(__name__)

_CV_METRICS_SCHEMA_VERSION = 4


class WordCountWindow(TypedDict):
    min: int
    max: int


class RecordCounts(TypedDict):
    train: int
    test: int


class CrossValidationValSummary(TypedDict):
    val_qwk_mean: float
    val_qwk_std: float
    val_mae_mean: float
    val_mae_std: float
    val_adjacent_accuracy_mean: float
    val_adjacent_accuracy_std: float
    elapsed_s: float


class TrainValSplitSizes(TypedDict):
    train: int
    val: int
    test: int


class SplitEval(TypedDict):
    qwk: float
    adjacent_accuracy: float
    mean_absolute_error: float


class FinalTrainValTestEval(TypedDict):
    train_val_split: TrainValSplitSizes
    val: SplitEval
    test: SplitEval
    test_record_count: int
    best_iteration: int


class CrossValidationMetricsPayload(TypedDict):
    schema_version: int
    created_at: str
    dataset_kind: str
    feature_set: str
    ensemble_size: int
    ensemble_seed_base: int
    ensemble_member_seeds_by_fold: dict[str, list[int]]
    ensemble_member_seeds_final_fit: list[int]
    training_mode: str
    grade_band_weighting: str
    grade_band_weight_cap: float
    prediction_mapping: str
    predictor_feature_selection: dict[str, object]
    scheme: SplitScheme
    n_splits: int
    word_count_window: WordCountWindow
    record_counts: RecordCounts
    cv_feature_store_dir: str
    folds: list[FoldResult]
    summary: CrossValidationValSummary
    final_train_val_test: FinalTrainValTestEval


@dataclass(frozen=True)
class CrossValidationSummary:
    run_paths: RunPaths
    cv_feature_store_dir: Path
    metrics_path: Path
    report_path: Path
    residual_report_path: Path


def run_cross_validation(
    config: ExperimentConfig,
    *,
    feature_set: FeatureSet,
    splits_path: Path,
    scheme: SplitScheme,
    ensemble_size: int = 1,
    reuse_cv_feature_store_dir: Path | None = None,
    min_words: int | None = None,
    max_words: int | None = None,
    handcrafted_keep: list[str] | None = None,
    handcrafted_drop: list[str] | None = None,
    training_mode: TrainingMode = TrainingMode.REGRESSION,
    grade_band_weighting: GradeBandWeighting = GradeBandWeighting.NONE,
    grade_band_weight_cap: float = 3.0,
    prediction_mapping: PredictionMapping = PredictionMapping.ROUND_HALF_BAND,
) -> CrossValidationSummary:
    """Run cross-validation for ELLIPSE using reusable split definitions."""

    if config.dataset_kind != DatasetKind.ELLIPSE:
        raise ValueError("cv currently supports only --dataset-kind=ellipse")
    if ensemble_size < 1:
        raise ValueError("ensemble_size must be >= 1.")

    splits = load_splits(splits_path)
    validate_splits_compatibility(
        config=config, splits=splits, min_words=min_words, max_words=max_words
    )

    min_words = int(splits.word_count_window["min"])
    max_words = int(splits.word_count_window["max"])
    word_window: WordCountWindow = {"min": min_words, "max": max_words}

    run_paths = build_run_paths(config.output)
    metrics_path = run_paths.artifacts_dir / "cv_metrics.json"
    report_path = run_paths.reports_dir / "cv_report.md"
    residual_report_path = run_paths.reports_dir / "residual_diagnostics.md"

    with run_file_logger(run_paths.log_path):
        progress = ProgressWriter(run_paths.run_dir)
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

        keep_feature_indices = resolve_keep_feature_indices(
            store.train_features.feature_names,
            feature_set=feature_set,
            handcrafted_keep=handcrafted_keep,
            handcrafted_drop=handcrafted_drop,
        )
        predictor_selection = feature_selection_summary(
            store.train_features.feature_names,
            feature_set=feature_set,
            keep_feature_indices=keep_feature_indices,
            handcrafted_keep=handcrafted_keep,
            handcrafted_drop=handcrafted_drop,
        )
        (run_paths.artifacts_dir / "predictor_feature_selection.json").write_text(
            json.dumps(predictor_selection, indent=2),
            encoding="utf-8",
        )

        folds = select_folds(splits, scheme=scheme)
        train_id_to_idx = {rid: idx for idx, rid in enumerate(store.manifest.train_record_ids)}

        min_band = float(np.min(store.y_train))
        max_band = float(np.max(store.y_train))

        fold_results: list[FoldResult] = []
        fold_predictions: list[FoldPredictions] = []
        ensemble_seeds_by_fold: dict[str, list[int]] = {}
        ensemble_member_seeds = _ensemble_member_seeds(
            base_seed=int(config.training.random_seed),
            ensemble_size=int(ensemble_size),
        )
        oof_val_record_ids: list[str] = []
        oof_val_fold_ids: list[int] = []
        oof_val_indices: list[np.ndarray] = []
        oof_val_pred_raw: list[np.ndarray] = []
        train_id_to_prompt = {record.record_id: record.question for record in train_records}

        with stage_timer(
            run_paths.run_dir,
            logger,
            "cv_folds_train_eval",
            scheme=scheme,
            n_splits=int(splits.n_splits),
            feature_set=feature_set.value,
        ):
            start = time.monotonic()
            for index, fold in enumerate(folds):
                ensemble_seeds_by_fold[str(fold.fold)] = list(ensemble_member_seeds)
                fold_outcome = run_fold_with_predictions(
                    fold=fold,
                    train_id_to_idx=train_id_to_idx,
                    features=store.train_features,
                    y=store.y_train,
                    config=config,
                    member_seeds=ensemble_member_seeds,
                    min_band=min_band,
                    max_band=max_band,
                    keep_feature_indices=keep_feature_indices,
                    training_mode=training_mode,
                    grade_band_weighting=grade_band_weighting,
                    grade_band_weight_cap=grade_band_weight_cap,
                )
                fold_predictions.append(fold_outcome)
                fold_result = fold_outcome.fold_result
                fold_results.append(fold_result)
                oof_val_record_ids.extend(fold_outcome.val_record_ids)
                fold_id = int(fold_result["fold"])
                oof_val_fold_ids.extend([fold_id] * len(fold_outcome.val_record_ids))
                oof_val_indices.append(fold_outcome.val_indices)
                oof_val_pred_raw.append(fold_outcome.val_pred_raw)
                progress.update(
                    substage="cv.folds",
                    processed=index + 1,
                    total=len(folds),
                    unit="folds",
                )

            elapsed = time.monotonic() - start
        oof_pred_mapped: np.ndarray | None = None
        locked_test_pred_mapped: np.ndarray | None = None
        global_cutpoints: np.ndarray | None = None

        if prediction_mapping == PredictionMapping.QWK_CUTPOINTS_LFO and oof_val_record_ids:
            oof_fold_ids_arr = np.array(oof_val_fold_ids, dtype=int)
            oof_indices_arr = np.concatenate(oof_val_indices).astype(int)
            oof_pred_raw_arr = np.concatenate(oof_val_pred_raw).astype(float)
            oof_true_arr = store.y_train[oof_indices_arr].astype(float)

            band_vals = half_band_values(min_band=min_band, max_band=max_band).astype(float)
            cutpoints_by_fold: dict[int, list[float]] = {}
            for fold_id in sorted(set(oof_fold_ids_arr.tolist())):
                mask = oof_fold_ids_arr != fold_id
                calibration = fit_qwk_cutpoints_coordinate_ascent(
                    y_true=oof_true_arr[mask],
                    y_pred_raw=oof_pred_raw_arr[mask],
                    min_band=min_band,
                    max_band=max_band,
                )
                cutpoints_by_fold[int(fold_id)] = [float(x) for x in calibration.cutpoints.tolist()]

            oof_pred_mapped = np.empty_like(oof_pred_raw_arr, dtype=float)
            for fold_id, cutpoints in cutpoints_by_fold.items():
                mask = oof_fold_ids_arr == int(fold_id)
                oof_pred_mapped[mask] = apply_cutpoints(
                    y_pred_raw=oof_pred_raw_arr[mask],
                    cutpoints=np.array(cutpoints, dtype=float),
                    band_values=band_vals,
                    min_band=min_band,
                    max_band=max_band,
                )

            # Update fold-level val metrics to reflect the calibrated mapping.
            for fold_outcome in fold_predictions:
                fold_result = fold_outcome.fold_result
                fold_id = int(fold_result["fold"])
                cutpoints = cutpoints_by_fold[fold_id]
                mapped = apply_cutpoints(
                    y_pred_raw=fold_outcome.val_pred_raw.astype(float),
                    cutpoints=np.array(cutpoints, dtype=float),
                    band_values=band_vals,
                    min_band=min_band,
                    max_band=max_band,
                )
                eval_val = evaluate_predictions(
                    fold_outcome.val_true.astype(float),
                    mapped.astype(float),
                    min_band=min_band,
                    max_band=max_band,
                )
                fold_result["val"] = {
                    "qwk": float(eval_val.qwk),
                    "adjacent_accuracy": float(eval_val.adjacent_accuracy),
                    "mean_absolute_error": float(eval_val.mean_absolute_error),
                }

            # Fit a global calibration on all OOF predictions to apply to locked_test.
            global_calibration = fit_qwk_cutpoints_coordinate_ascent(
                y_true=oof_true_arr,
                y_pred_raw=oof_pred_raw_arr,
                min_band=min_band,
                max_band=max_band,
            )
            global_cutpoints = global_calibration.cutpoints.astype(float)

            (run_paths.artifacts_dir / "calibration_cutpoints_by_fold.json").write_text(
                json.dumps(
                    {
                        "mode": prediction_mapping.value,
                        "min_band": float(min_band),
                        "max_band": float(max_band),
                        "band_values": [float(x) for x in band_vals.tolist()],
                        "cutpoints_by_fold": cutpoints_by_fold,
                        "global_cutpoints": [float(x) for x in global_cutpoints.tolist()],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (run_paths.artifacts_dir / "calibration_summary.json").write_text(
                json.dumps(
                    {
                        "mode": prediction_mapping.value,
                        "leave_one_fold_out": True,
                        "candidate_quantiles": 64,
                        "max_iter": 10,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        # Aggregate fold metrics (after any optional mapping override).
        fold_val_qwk = [float(fold["val"]["qwk"]) for fold in fold_results]
        fold_val_mae = [float(fold["val"]["mean_absolute_error"]) for fold in fold_results]
        fold_val_adj = [float(fold["val"]["adjacent_accuracy"]) for fold in fold_results]
        summary: CrossValidationValSummary = {
            "val_qwk_mean": float(np.mean(fold_val_qwk)) if fold_val_qwk else 0.0,
            "val_qwk_std": float(np.std(fold_val_qwk)) if fold_val_qwk else 0.0,
            "val_mae_mean": float(np.mean(fold_val_mae)) if fold_val_mae else 0.0,
            "val_mae_std": float(np.std(fold_val_mae)) if fold_val_mae else 0.0,
            "val_adjacent_accuracy_mean": float(np.mean(fold_val_adj)) if fold_val_adj else 0.0,
            "val_adjacent_accuracy_std": float(np.std(fold_val_adj)) if fold_val_adj else 0.0,
            "elapsed_s": float(elapsed),
        }

        with stage_timer(
            run_paths.run_dir,
            logger,
            "cv_final_train_test_eval",
            scheme=scheme,
            feature_set=feature_set.value,
        ):
            final_eval, locked_test_pred_raw = _run_final_train_and_test_eval(
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
                keep_feature_indices=keep_feature_indices,
                training_mode=training_mode,
                grade_band_weighting=grade_band_weighting,
                grade_band_weight_cap=grade_band_weight_cap,
                member_seeds=ensemble_member_seeds,
            )

        if global_cutpoints is not None:
            band_vals = half_band_values(min_band=min_band, max_band=max_band).astype(float)
            locked_test_pred_mapped = apply_cutpoints(
                y_pred_raw=locked_test_pred_raw.astype(float),
                cutpoints=global_cutpoints.astype(float),
                band_values=band_vals,
                min_band=min_band,
                max_band=max_band,
            )

        payload: CrossValidationMetricsPayload = {
            "schema_version": _CV_METRICS_SCHEMA_VERSION,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "dataset_kind": config.dataset_kind.value,
            "feature_set": feature_set.value,
            "ensemble_size": int(ensemble_size),
            "ensemble_seed_base": int(config.training.random_seed),
            "ensemble_member_seeds_by_fold": ensemble_seeds_by_fold,
            "ensemble_member_seeds_final_fit": list(ensemble_member_seeds),
            "training_mode": training_mode.value,
            "grade_band_weighting": grade_band_weighting.value,
            "grade_band_weight_cap": float(grade_band_weight_cap),
            "prediction_mapping": prediction_mapping.value,
            "predictor_feature_selection": predictor_selection,
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

        report_md = build_cv_report(payload)
        report_path.write_text(report_md, encoding="utf-8")

        locked_test_record_ids = [record.record_id for record in test_records]
        locked_test_prompts = [record.question for record in test_records]
        locked_test_frame = build_residual_frame(
            record_ids=locked_test_record_ids,
            prompts=locked_test_prompts,
            y_true=store.y_test.astype(float),
            y_pred_raw=locked_test_pred_raw.astype(float),
            y_pred_mapped=locked_test_pred_mapped.astype(float)
            if locked_test_pred_mapped is not None
            else None,
            min_band=min_band,
            max_band=max_band,
            split_label="locked_test",
            feature_matrix=store.test_features,
        )
        persist_residual_artifacts(
            locked_test_frame,
            output_stem=run_paths.artifacts_dir / "residuals_locked_test",
        )

        frames_for_report = {"locked_test": locked_test_frame}
        if oof_val_record_ids:
            oof_indices = np.concatenate(oof_val_indices).astype(int)
            oof_pred_raw = np.concatenate(oof_val_pred_raw).astype(float)
            oof_true = store.y_train[oof_indices].astype(float)
            oof_prompts = [train_id_to_prompt[record_id] for record_id in oof_val_record_ids]
            cv_val_frame = build_residual_frame(
                record_ids=oof_val_record_ids,
                prompts=oof_prompts,
                y_true=oof_true,
                y_pred_raw=oof_pred_raw,
                y_pred_mapped=oof_pred_mapped.astype(float)
                if oof_pred_mapped is not None
                else None,
                min_band=min_band,
                max_band=max_band,
                split_label="cv_val_oof",
                feature_matrix=store.train_features,
                row_indices=oof_indices,
                fold_ids=oof_val_fold_ids,
            )
            persist_residual_artifacts(
                cv_val_frame,
                output_stem=run_paths.artifacts_dir / "residuals_cv_val_oof",
            )
            frames_for_report["cv_val_oof"] = cv_val_frame

        generate_residual_diagnostics_report(
            frames=frames_for_report,
            min_band=min_band,
            max_band=max_band,
            output_path=residual_report_path,
        )

        logger.info("CV complete: %s", run_paths.run_dir)

    return CrossValidationSummary(
        run_paths=run_paths,
        cv_feature_store_dir=cv_store_dir,
        metrics_path=metrics_path,
        report_path=report_path,
        residual_report_path=residual_report_path,
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
    keep_feature_indices: list[int] | None,
    training_mode: TrainingMode,
    grade_band_weighting: GradeBandWeighting,
    grade_band_weight_cap: float,
    member_seeds: list[int],
) -> tuple[FinalTrainValTestEval, np.ndarray]:
    split = _train_val_split(train_records, config=config)
    train_ids = [record.record_id for record in split.train]
    val_ids = [record.record_id for record in split.val]

    train_idx = indices_for_ids(train_ids, id_to_idx=train_id_to_idx)
    val_idx = indices_for_ids(val_ids, id_to_idx=train_id_to_idx)

    feature_names = list(train_features.feature_names)
    train_mat = train_features.matrix[train_idx]
    val_mat = train_features.matrix[val_idx]
    test_mat = test_features.matrix

    if keep_feature_indices is not None:
        feature_names = [feature_names[idx] for idx in keep_feature_indices]
        train_mat = train_mat[:, keep_feature_indices]
        val_mat = val_mat[:, keep_feature_indices]
        test_mat = test_mat[:, keep_feature_indices]

    sample_weight_train = compute_grade_band_sample_weights(
        y_train[train_idx],
        mode=grade_band_weighting,
        cap=grade_band_weight_cap,
    )
    dval = xgb.DMatrix(val_mat, feature_names=feature_names)
    dtest = xgb.DMatrix(test_mat, feature_names=feature_names)

    if not member_seeds:
        raise ValueError("member_seeds must be non-empty for CV final fit.")

    member_best_iterations: list[int] = []
    member_predt_val: list[np.ndarray] = []
    member_predt_test: list[np.ndarray] = []
    for seed in member_seeds:
        training_config = config.training.model_copy(update={"random_seed": int(seed)})
        artifacts = train_model(
            FeatureMatrix(matrix=train_mat, feature_names=feature_names),
            FeatureMatrix(matrix=val_mat, feature_names=feature_names),
            y_train[train_idx],
            y_train[val_idx],
            training_config,
            min_band=min_band,
            max_band=max_band,
            training_mode=training_mode,
            sample_weight_train=sample_weight_train,
        )
        member_best_iterations.append(int(artifacts.best_iteration))
        member_predt_val.append(np.asarray(artifacts.model.predict(dval)))
        member_predt_test.append(np.asarray(artifacts.model.predict(dtest)))

    best_iteration = (
        int(round(float(np.mean(member_best_iterations)))) if member_best_iterations else 0
    )
    predt_val = np.mean(np.stack(member_predt_val, axis=0), axis=0)
    predt_test = np.mean(np.stack(member_predt_test, axis=0), axis=0)

    pred_val = decode_predictions(
        predt_val,
        min_band=min_band,
        max_band=max_band,
        mode=training_mode,
    )
    pred_test = decode_predictions(
        predt_test,
        min_band=min_band,
        max_band=max_band,
        mode=training_mode,
    )

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

    return (
        {
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
            "best_iteration": best_iteration,
        },
        pred_test,
    )


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


def _ensemble_member_seeds(*, base_seed: int, ensemble_size: int) -> list[int]:
    """Build deterministic ensemble seeds for CV runs.

    Seed strategy:
        The baseline CV implementation uses a single fixed seed for every fold. For fair
        comparison between `ensemble_size=1` and `ensemble_size>1`, we keep that behavior by
        deriving member seeds as:

            base_seed + i, for i in [0..ensemble_size-1]

        This means:
        - `ensemble_size=1` matches the historical behavior (seed=`base_seed`).
        - `ensemble_size>1` ensembles across a small, deterministic neighborhood of seeds.
    """

    if ensemble_size < 1:
        raise ValueError("ensemble_size must be >= 1.")
    base = int(base_seed)
    return [int(base + offset) for offset in range(int(ensemble_size))]
