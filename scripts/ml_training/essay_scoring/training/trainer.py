"""Training utilities for the essay scoring research pipeline.

Purpose:
    Train XGBoost models for essay scoring with a consistent early-stopping signal (QWK) and
    return structured training artifacts. The default mode is regression, but CV experiments
    can also request an ordinal-as-multiclass training mode to study grade-band compression and
    tail behavior.

Relationships:
    - Used by `scripts.ml_training.essay_scoring.runner` for single-run experiments.
    - Used by `scripts.ml_training.essay_scoring.cv_shared` and
      `scripts.ml_training.essay_scoring.cross_validation` for CV experiments.
    - Delegates training-mode-specific encoding/metrics to
      `scripts.ml_training.essay_scoring.training.training_modes`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.config import TrainingConfig
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.training.training_modes import (
    TrainingMode,
    encode_ordinal_labels,
    is_ordinal_multiclass,
    ordinal_num_classes,
    qwk_custom_metric,
)


@dataclass(frozen=True)
class TrainingArtifacts:
    """Artifacts returned from model training."""

    model: xgb.Booster
    evals_result: dict[str, dict[str, list[float]]]
    best_iteration: int


def train_model(
    train_features: FeatureMatrix,
    val_features: FeatureMatrix,
    y_train: np.ndarray,
    y_val: np.ndarray,
    config: TrainingConfig,
    *,
    min_band: float,
    max_band: float,
    training_mode: TrainingMode = TrainingMode.REGRESSION,
    sample_weight_train: np.ndarray | None = None,
) -> TrainingArtifacts:
    """Train an XGBoost model with QWK early stopping."""

    if train_features.feature_names != val_features.feature_names:
        raise ValueError("Feature name mismatch between train and validation sets.")

    if is_ordinal_multiclass(training_mode):
        y_train = encode_ordinal_labels(y_train, min_band=min_band, max_band=max_band)
        y_val = encode_ordinal_labels(y_val, min_band=min_band, max_band=max_band)

    dtrain = xgb.DMatrix(
        train_features.matrix,
        label=y_train,
        feature_names=train_features.feature_names,
        weight=sample_weight_train,
    )
    dval = xgb.DMatrix(val_features.matrix, label=y_val, feature_names=val_features.feature_names)

    params = dict(config.params)
    params["seed"] = config.random_seed
    params["disable_default_eval_metric"] = 1
    if is_ordinal_multiclass(training_mode):
        params["objective"] = "multi:softprob"
        params["num_class"] = ordinal_num_classes(min_band=min_band, max_band=max_band)

    evals_result: dict[str, dict[str, list[float]]] = {}
    model = xgb.train(
        params=params,
        dtrain=dtrain,
        num_boost_round=config.num_boost_round,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=config.early_stopping_rounds,
        custom_metric=qwk_custom_metric(min_band=min_band, max_band=max_band, mode=training_mode),
        maximize=True,
        evals_result=evals_result,
    )

    best_iteration = int(model.best_iteration or 0)
    return TrainingArtifacts(
        model=model,
        evals_result=evals_result,
        best_iteration=best_iteration,
    )
