"""Training utilities for the essay scoring XGBoost regressor."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.config import TrainingConfig
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.training.qwk import qwk_eval_factory


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
) -> TrainingArtifacts:
    """Train an XGBoost regressor with QWK early stopping."""

    if train_features.feature_names != val_features.feature_names:
        raise ValueError("Feature name mismatch between train and validation sets.")

    dtrain = xgb.DMatrix(
        train_features.matrix, label=y_train, feature_names=train_features.feature_names
    )
    dval = xgb.DMatrix(val_features.matrix, label=y_val, feature_names=val_features.feature_names)

    params = dict(config.params)
    params["seed"] = config.random_seed
    params["disable_default_eval_metric"] = 1

    evals_result: dict[str, dict[str, list[float]]] = {}
    model = xgb.train(
        params=params,
        dtrain=dtrain,
        num_boost_round=config.num_boost_round,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=config.early_stopping_rounds,
        custom_metric=qwk_eval_factory(min_band=min_band, max_band=max_band),
        maximize=True,
        evals_result=evals_result,
    )

    best_iteration = int(model.best_iteration or 0)
    return TrainingArtifacts(
        model=model,
        evals_result=evals_result,
        best_iteration=best_iteration,
    )
