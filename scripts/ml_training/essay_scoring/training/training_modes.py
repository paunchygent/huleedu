"""Training-mode utilities for essay scoring models.

Purpose:
    Provide a small, explicit abstraction for switching between:
    - regression (continuous prediction), and
    - ordinal-as-multiclass (predict a probability distribution over half-band classes),
    while keeping downstream evaluation/reporting compatible with the existing pipeline.

    The research workflow evaluates *score predictions* in band units (e.g., 1.0–5.0 in 0.5
    increments for ELLIPSE). For ordinal multiclass, we therefore:
    - encode labels into class IDs (0..num_class-1) based on half-band steps, and
    - decode probability outputs back into band-unit predictions via either:
        - expected value (probability-weighted band value), or
        - argmax (most-likely band).

Relationships:
    - Used by `scripts.ml_training.essay_scoring.training.trainer` to configure XGBoost params,
      label encoding, and QWK early-stopping metrics.
    - Used by CV runners to decode XGBoost predictions into band-unit arrays for the shared
      evaluation + residual diagnostics pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

import numpy as np
import xgboost as xgb

from scripts.ml_training.essay_scoring.training.qwk import qwk_score


class TrainingMode(str, Enum):
    """Supported training modes for the research pipeline."""

    REGRESSION = "regression"
    ORDINAL_MULTICLASS_EXPECTED = "ordinal_multiclass_expected"
    ORDINAL_MULTICLASS_ARGMAX = "ordinal_multiclass_argmax"


def is_ordinal_multiclass(mode: TrainingMode) -> bool:
    return mode in {
        TrainingMode.ORDINAL_MULTICLASS_EXPECTED,
        TrainingMode.ORDINAL_MULTICLASS_ARGMAX,
    }


def ordinal_num_classes(*, min_band: float, max_band: float) -> int:
    min_half_id = int(round(min_band * 2.0))
    max_half_id = int(round(max_band * 2.0))
    return int(max_half_id - min_half_id + 1)


def encode_ordinal_labels(
    y_true: np.ndarray,
    *,
    min_band: float,
    max_band: float,
) -> np.ndarray:
    """Encode half-band scores into contiguous class IDs.

    Args:
        y_true: Score labels in band units (e.g., 1.0, 1.5, ...).
        min_band: Minimum band value (inclusive).
        max_band: Maximum band value (inclusive).

    Returns:
        Integer class IDs in range [0, num_class-1].
    """

    min_half_id = int(round(min_band * 2.0))
    max_half_id = int(round(max_band * 2.0))
    half_ids = np.round(y_true.astype(float) * 2.0).astype(int)
    class_ids = half_ids - min_half_id

    if np.any(half_ids < min_half_id) or np.any(half_ids > max_half_id):
        raise ValueError(
            "Ordinal label out of range for half-band encoding "
            f"min_band={min_band} max_band={max_band} "
            f"half_ids_range=({half_ids.min()},{half_ids.max()})"
        )
    return class_ids.astype(int)


def decode_ordinal_predictions(
    pred_proba: np.ndarray,
    *,
    min_band: float,
    max_band: float,
    mode: TrainingMode,
) -> np.ndarray:
    """Decode multi:softprob outputs into band-unit predictions."""

    if pred_proba.ndim != 2:
        raise ValueError(
            "Ordinal multiclass predictions must be 2D (n_samples, n_classes) "
            f"got shape={pred_proba.shape}."
        )

    n_classes = ordinal_num_classes(min_band=min_band, max_band=max_band)
    if pred_proba.shape[1] != n_classes:
        raise ValueError(
            "Ordinal multiclass prediction class count mismatch "
            f"expected={n_classes} got={pred_proba.shape[1]}."
        )

    min_half_id = int(round(min_band * 2.0))
    class_band_values = (np.arange(n_classes) + min_half_id) / 2.0

    if mode == TrainingMode.ORDINAL_MULTICLASS_EXPECTED:
        return np.asarray(pred_proba @ class_band_values, dtype=float)
    if mode == TrainingMode.ORDINAL_MULTICLASS_ARGMAX:
        class_ids = np.argmax(pred_proba, axis=1)
        return np.asarray(class_band_values[class_ids], dtype=float)
    raise ValueError(f"Unsupported ordinal decode mode: {mode}")


def decode_predictions(
    predt: np.ndarray,
    *,
    min_band: float,
    max_band: float,
    mode: TrainingMode,
) -> np.ndarray:
    """Decode raw XGBoost predictions into band-unit predictions."""

    if is_ordinal_multiclass(mode):
        return decode_ordinal_predictions(predt, min_band=min_band, max_band=max_band, mode=mode)
    return predt.reshape(-1)


def qwk_custom_metric(
    *,
    min_band: float,
    max_band: float,
    mode: TrainingMode,
) -> Callable[[np.ndarray, xgb.DMatrix], tuple[str, float]]:
    """Create a QWK custom metric compatible with the chosen training mode."""

    if is_ordinal_multiclass(mode):
        min_half_id = int(round(min_band * 2.0))

        def qwk_eval_ordinal(preds: np.ndarray, dtrain: xgb.DMatrix) -> tuple[str, float]:
            labels = dtrain.get_label().astype(float)
            y_true = (np.round(labels).astype(int) + min_half_id) / 2.0
            y_pred = decode_ordinal_predictions(
                preds, min_band=min_band, max_band=max_band, mode=mode
            )
            return "qwk", qwk_score(y_true, y_pred, min_band=min_band, max_band=max_band)

        return qwk_eval_ordinal

    def qwk_eval_regression(preds: np.ndarray, dtrain: xgb.DMatrix) -> tuple[str, float]:
        labels = dtrain.get_label()
        return "qwk", qwk_score(labels, preds, min_band=min_band, max_band=max_band)

    return qwk_eval_regression
