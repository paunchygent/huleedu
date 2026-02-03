"""Experiment runner for the essay scoring research pipeline."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.config import DatasetKind, ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.dataset import (
    EssayDataset,
    EssayRecord,
    load_ellipse_train_test_dataset,
    load_ielts_dataset,
)
from scripts.ml_training.essay_scoring.environment import gather_git_sha, repo_root_from_package
from scripts.ml_training.essay_scoring.feature_store import (
    load_feature_store,
    persist_feature_store,
    resolve_feature_store_dir,
)
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.features.pipeline import FeaturePipeline
from scripts.ml_training.essay_scoring.features.schema import build_feature_schema
from scripts.ml_training.essay_scoring.logging_utils import run_file_logger
from scripts.ml_training.essay_scoring.paths import RunPaths, build_run_paths
from scripts.ml_training.essay_scoring.reports.grade_scale_report import (
    generate_grade_scale_report,
)
from scripts.ml_training.essay_scoring.splitters import DatasetSplit, stratified_split
from scripts.ml_training.essay_scoring.training.evaluation import (
    EvaluationResult,
    evaluate_predictions,
)
from scripts.ml_training.essay_scoring.training.shap_explainability import generate_shap_artifacts
from scripts.ml_training.essay_scoring.training.trainer import train_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunSummary:
    """Summary of a completed training run."""

    run_paths: RunPaths
    feature_set: FeatureSet
    metrics: dict[str, dict[str, object]]


@dataclass(frozen=True)
class FeaturizeSummary:
    """Summary of a completed featurization run."""

    run_paths: RunPaths
    feature_set: FeatureSet
    feature_store_dir: Path
    record_counts: dict[str, int]


def featurize_experiment(
    config: ExperimentConfig,
    feature_set: FeatureSet | None = None,
) -> FeaturizeSummary:
    """Extract and persist features (train/val/test) for warm-cache iteration."""

    feature_set = feature_set or config.feature_set
    run_paths = build_run_paths(config.output)
    with run_file_logger(run_paths.log_path):
        logger.info(
            "Starting featurize feature_set=%s run_dir=%s",
            feature_set.value,
            run_paths.run_dir,
        )
        dataset, pre_split_train, pre_split_test, dataset_source = _load_dataset(config)
        logger.info("Loading dataset from %s", dataset_source)
        logger.info("Loaded dataset records=%d", len(dataset.records))
        split = _build_split(
            dataset=dataset,
            pre_split_train=pre_split_train,
            pre_split_test=pre_split_test,
            config=config,
        )
        logger.info(
            "Split sizes train=%d val=%d test=%d",
            len(split.train),
            len(split.val),
            len(split.test),
        )

        pipeline = FeaturePipeline(config.embedding, offload=config.offload)
        logger.info("Extracting train features")
        train_features = pipeline.extract(split.train, feature_set)
        logger.info("Extracting validation features")
        val_features = pipeline.extract(split.val, feature_set)
        logger.info("Extracting test features")
        test_features = pipeline.extract(split.test, feature_set)

        feature_store_dir = persist_feature_store(
            run_dir=run_paths.run_dir,
            config=config,
            dataset=dataset,
            split=split,
            feature_set=feature_set,
            spacy_model=pipeline.spacy_model,
            train_features=train_features,
            val_features=val_features,
            test_features=test_features,
        )

        embedding_dim = _embedding_dim(train_features.feature_names)
        _persist_feature_schema(run_paths, embedding_dim)

        logger.info("Featurize complete: %s", feature_store_dir)

    return FeaturizeSummary(
        run_paths=run_paths,
        feature_set=feature_set,
        feature_store_dir=feature_store_dir,
        record_counts={
            "total": len(dataset.records),
            "train": len(split.train),
            "val": len(split.val),
            "test": len(split.test),
        },
    )


def run_experiment(
    config: ExperimentConfig,
    feature_set: FeatureSet | None = None,
    *,
    reuse_feature_store_dir: Path | None = None,
    skip_shap: bool = False,
    skip_grade_scale_report: bool = False,
) -> RunSummary:
    """Execute a full training + evaluation run."""

    feature_set = feature_set or config.feature_set
    run_paths = build_run_paths(config.output)
    with run_file_logger(run_paths.log_path):
        logger.info(
            "Starting run feature_set=%s run_dir=%s",
            feature_set.value,
            run_paths.run_dir,
        )
        dataset, pre_split_train, pre_split_test, dataset_source = _load_dataset(config)
        logger.info("Loading dataset from %s", dataset_source)
        logger.info("Loaded dataset records=%d", len(dataset.records))
        min_band, max_band = _label_range(dataset)
        split: DatasetSplit
        train_features: FeatureMatrix
        val_features: FeatureMatrix
        test_features: FeatureMatrix
        y_train: np.ndarray
        y_val: np.ndarray
        y_test: np.ndarray

        if reuse_feature_store_dir is not None:
            resolved_store_dir = resolve_feature_store_dir(reuse_feature_store_dir)
            logger.info("Reusing feature store from %s", resolved_store_dir)
            store = load_feature_store(
                dataset=dataset,
                store_dir=resolved_store_dir,
                expected_config=config.model_copy(update={"feature_set": feature_set}),
            )
            split = store.split
            train_features = store.train_features
            val_features = store.val_features
            test_features = store.test_features
            y_train = store.y_train
            y_val = store.y_val
            y_test = store.y_test
        else:
            split = _build_split(
                dataset=dataset,
                pre_split_train=pre_split_train,
                pre_split_test=pre_split_test,
                config=config,
            )
            logger.info(
                "Split sizes train=%d val=%d test=%d",
                len(split.train),
                len(split.val),
                len(split.test),
            )
            pipeline = FeaturePipeline(config.embedding, offload=config.offload)
            logger.info("Extracting train features")
            train_features = pipeline.extract(split.train, feature_set)
            logger.info("Extracting validation features")
            val_features = pipeline.extract(split.val, feature_set)
            logger.info("Extracting test features")
            test_features = pipeline.extract(split.test, feature_set)

            y_train = np.array([record.overall for record in split.train])
            y_val = np.array([record.overall for record in split.val])
            y_test = np.array([record.overall for record in split.test])

        logger.info("Training XGBoost model")
        training_artifacts = train_model(
            train_features=train_features,
            val_features=val_features,
            y_train=y_train,
            y_val=y_val,
            config=config.training,
            min_band=min_band,
            max_band=max_band,
        )

        model = training_artifacts.model

        logger.info("Evaluating model")
        train_pred = model.predict(_as_dmatrix(train_features.matrix, train_features.feature_names))
        val_pred = model.predict(_as_dmatrix(val_features.matrix, val_features.feature_names))
        test_pred = model.predict(_as_dmatrix(test_features.matrix, test_features.feature_names))

        train_eval = evaluate_predictions(y_train, train_pred, min_band=min_band, max_band=max_band)
        val_eval = evaluate_predictions(y_val, val_pred, min_band=min_band, max_band=max_band)
        test_eval = evaluate_predictions(y_test, test_pred, min_band=min_band, max_band=max_band)

        metrics = {
            "train": _evaluation_to_dict(train_eval),
            "val": _evaluation_to_dict(val_eval),
            "test": _evaluation_to_dict(test_eval),
        }

        logger.info("Persisting metrics and metadata")
        _persist_metrics(metrics, run_paths.metrics_path)
        embedding_dim = _embedding_dim(train_features.feature_names)
        _persist_metadata(
            config=config,
            dataset=dataset,
            split=split,
            feature_set=feature_set,
            embedding_dim=embedding_dim,
            best_iteration=training_artifacts.best_iteration,
            run_paths=run_paths,
            dataset_source=dataset_source,
            min_band=min_band,
            max_band=max_band,
        )
        _persist_feature_schema(run_paths, embedding_dim)

        model.save_model(str(run_paths.model_path))

        if not skip_shap:
            logger.info("Generating SHAP artifacts")
            generate_shap_artifacts(
                model=model,
                features=test_features.matrix,
                feature_names=test_features.feature_names,
                output_dir=run_paths.shap_dir,
            )

        if not skip_grade_scale_report:
            logger.info("Generating grade-scale report")
            generate_grade_scale_report(
                records=split.test,
                y_true=y_test,
                y_pred=test_pred,
                dataset_source=dataset_source,
                min_band=min_band,
                max_band=max_band,
                output_path=run_paths.grade_scale_report_path,
            )

        logger.info("Run complete: %s", run_paths.run_dir)

    return RunSummary(run_paths=run_paths, feature_set=feature_set, metrics=metrics)


def run_ablation(config: ExperimentConfig) -> list[RunSummary]:
    """Run ablation experiments across feature sets."""

    logger.info("Starting ablation run")
    summaries: list[RunSummary] = []
    for feature_set in [FeatureSet.HANDCRAFTED, FeatureSet.EMBEDDINGS, FeatureSet.COMBINED]:
        logger.info("Running ablation feature_set=%s", feature_set.value)
        updated_output = config.output.model_copy(update={"run_name": feature_set.value})
        updated_config = config.model_copy(update={"output": updated_output})
        summaries.append(run_experiment(updated_config, feature_set=feature_set))
    logger.info("Ablation run complete")
    return summaries


def _evaluation_to_dict(evaluation: EvaluationResult) -> dict[str, object]:
    return {
        "qwk": float(evaluation.qwk),
        "adjacent_accuracy": float(evaluation.adjacent_accuracy),
        "mean_absolute_error": float(evaluation.mean_absolute_error),
        "per_band_mae": evaluation.per_band_mae,
        "confusion_matrix": evaluation.confusion_matrix,
        "band_labels": evaluation.band_labels,
    }


def _persist_metrics(metrics: dict[str, dict[str, object]], path: Path) -> None:
    path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def _persist_metadata(
    config: ExperimentConfig,
    dataset: EssayDataset,
    split: DatasetSplit,
    feature_set: FeatureSet,
    embedding_dim: int,
    best_iteration: int,
    run_paths: RunPaths,
    *,
    dataset_source: str,
    min_band: float,
    max_band: float,
) -> None:
    repo_root = repo_root_from_package()
    metadata = {
        "dataset_kind": config.dataset_kind.value,
        "dataset_source": dataset_source,
        "label_scale": {
            "min": min_band,
            "max": max_band,
        },
        "ellipse_excluded_prompts": (
            config.ellipse_excluded_prompts if config.dataset_kind == DatasetKind.ELLIPSE else []
        ),
        "feature_set": feature_set.value,
        "embedding_model": config.embedding.model_name,
        "embedding_dim": embedding_dim,
        "training_params": config.training.params,
        "num_boost_round": config.training.num_boost_round,
        "early_stopping_rounds": config.training.early_stopping_rounds,
        "best_iteration": best_iteration,
        "git_sha": gather_git_sha(repo_root),
        "record_counts": {
            "total": len(dataset.records),
            "train": len(split.train),
            "val": len(split.val),
            "test": len(split.test),
        },
        "metrics_path": str(run_paths.metrics_path),
        "model_path": str(run_paths.model_path),
    }
    run_paths.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def _persist_feature_schema(run_paths: RunPaths, embedding_dim: int) -> None:
    schema = build_feature_schema(embedding_dim)
    run_paths.feature_schema_path.write_text(schema.model_dump_json(indent=2), encoding="utf-8")


def _as_dmatrix(matrix: np.ndarray, feature_names: list[str]) -> xgb.DMatrix:
    return xgb.DMatrix(matrix, feature_names=feature_names)


def _embedding_dim(feature_names: list[str]) -> int:
    return sum(1 for name in feature_names if name.startswith("embedding_"))


def _load_dataset(
    config: ExperimentConfig,
) -> tuple[EssayDataset, list[EssayRecord] | None, list[EssayRecord] | None, str]:
    if config.dataset_kind == DatasetKind.IELTS:
        dataset = load_ielts_dataset(config.dataset_path)
        return dataset, None, None, str(config.dataset_path)

    ellipse = load_ellipse_train_test_dataset(
        config.ellipse_train_path,
        config.ellipse_test_path,
        excluded_prompts=set(config.ellipse_excluded_prompts),
    )
    dataset_source = f"{config.ellipse_train_path} | {config.ellipse_test_path}"
    if config.ellipse_excluded_prompts:
        dataset_source = (
            f"{dataset_source} (excluded_prompts={sorted(config.ellipse_excluded_prompts)})"
        )
    return ellipse.dataset, ellipse.train_records, ellipse.test_records, dataset_source


def _build_split(
    *,
    dataset: EssayDataset,
    pre_split_train: list[EssayRecord] | None,
    pre_split_test: list[EssayRecord] | None,
    config: ExperimentConfig,
) -> DatasetSplit:
    if pre_split_train is None or pre_split_test is None:
        return stratified_split(dataset, config.training)

    train_plus_val = config.training.train_ratio + config.training.val_ratio
    if train_plus_val <= 0:
        raise ValueError("Training config must have a non-zero train+val ratio for pre-split data.")

    split_config = config.training.model_copy(
        update={
            "train_ratio": config.training.train_ratio / train_plus_val,
            "val_ratio": config.training.val_ratio / train_plus_val,
            "test_ratio": 0.0,
        }
    )

    train_dataset = EssayDataset(records=list(pre_split_train))
    train_val_split = stratified_split(train_dataset, split_config)
    return DatasetSplit(
        train=train_val_split.train,
        val=train_val_split.val,
        test=list(pre_split_test),
    )


def _label_range(dataset: EssayDataset) -> tuple[float, float]:
    labels = np.array(dataset.labels, dtype=float)
    return float(np.min(labels)), float(np.max(labels))
