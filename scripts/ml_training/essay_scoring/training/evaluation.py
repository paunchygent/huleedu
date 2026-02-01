"""Evaluation utilities for essay scoring models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scripts.ml_training.essay_scoring.training.qwk import (
    clip_bands,
    qwk_score,
    round_to_half_band,
)


@dataclass(frozen=True)
class EvaluationResult:
    """Structured evaluation output."""

    qwk: float
    adjacent_accuracy: float
    mean_absolute_error: float
    per_band_mae: dict[str, float]
    confusion_matrix: list[list[int]]
    band_labels: list[float]


def evaluate_predictions(y_true: np.ndarray, y_pred: np.ndarray) -> EvaluationResult:
    """Evaluate predictions with QWK and supporting diagnostics."""

    rounded = clip_bands(round_to_half_band(y_pred))
    qwk = qwk_score(y_true, y_pred)
    adjacent_accuracy = float(np.mean(np.abs(rounded - y_true) <= 0.5))
    mae = float(np.mean(np.abs(rounded - y_true)))

    per_band_mae = _per_band_mae(y_true, rounded)
    confusion_df = _confusion_matrix(y_true, rounded)

    return EvaluationResult(
        qwk=qwk,
        adjacent_accuracy=adjacent_accuracy,
        mean_absolute_error=mae,
        per_band_mae=per_band_mae,
        confusion_matrix=confusion_df.values.tolist(),
        band_labels=[float(label) for label in confusion_df.index.tolist()],
    )


def _per_band_mae(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute MAE per band label."""

    results: dict[str, float] = {}
    for band in sorted(set(y_true)):
        mask = y_true == band
        if not np.any(mask):
            continue
        results[str(band)] = float(np.mean(np.abs(y_pred[mask] - y_true[mask])))
    return results


def _confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray) -> pd.DataFrame:
    """Build a confusion matrix for rounded band predictions."""

    labels = sorted(set(y_true))
    return pd.crosstab(
        pd.Series(y_true, name="Actual"),
        pd.Series(y_pred, name="Predicted"),
        rownames=["Actual"],
        colnames=["Predicted"],
        dropna=False,
    ).reindex(index=labels, columns=labels, fill_value=0)
