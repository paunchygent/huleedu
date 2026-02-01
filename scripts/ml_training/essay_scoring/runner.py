"""Experiment runner for the essay scoring research pipeline."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.config import ExperimentConfig, FeatureSet
from scripts.ml_training.essay_scoring.dataset import EssayDataset, load_ielts_dataset
from scripts.ml_training.essay_scoring.environment import gather_git_sha, repo_root_from_package
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


def run_experiment(config: ExperimentConfig, feature_set: FeatureSet | None = None) -> RunSummary:
    """Execute a full training + evaluation run."""

    feature_set = feature_set or config.feature_set
    run_paths = build_run_paths(config.output)
    with run_file_logger(run_paths.log_path):
        logger.info(
            "Starting run feature_set=%s run_dir=%s",
            feature_set.value,
            run_paths.run_dir,
        )
        logger.info("Loading dataset from %s", config.dataset_path)
        dataset = load_ielts_dataset(config.dataset_path)
        logger.info("Loaded dataset records=%d", len(dataset.records))
        split = stratified_split(dataset, config.training)
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
        )

        model = training_artifacts.model

        logger.info("Evaluating model")
        train_pred = model.predict(_as_dmatrix(train_features.matrix, train_features.feature_names))
        val_pred = model.predict(_as_dmatrix(val_features.matrix, val_features.feature_names))
        test_pred = model.predict(_as_dmatrix(test_features.matrix, test_features.feature_names))

        train_eval = evaluate_predictions(y_train, train_pred)
        val_eval = evaluate_predictions(y_val, val_pred)
        test_eval = evaluate_predictions(y_test, test_pred)

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
        )
        _persist_feature_schema(run_paths, embedding_dim)

        model.save_model(str(run_paths.model_path))

        logger.info("Generating SHAP artifacts")
        generate_shap_artifacts(
            model=model,
            features=test_features.matrix,
            feature_names=test_features.feature_names,
            output_dir=run_paths.shap_dir,
        )

        logger.info("Generating grade-scale report")
        generate_grade_scale_report(
            records=split.test,
            y_true=y_test,
            y_pred=test_pred,
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
) -> None:
    repo_root = repo_root_from_package()
    metadata = {
        "dataset_path": str(config.dataset_path),
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
