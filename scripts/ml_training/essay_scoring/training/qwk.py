"""Quadratic weighted kappa utilities."""

from __future__ import annotations

import numpy as np
import xgboost as xgb
from sklearn.metrics import cohen_kappa_score


def round_to_half_band(predictions: np.ndarray) -> np.ndarray:
    """Round predictions to the nearest 0.5 band."""

    return np.round(predictions * 2.0) / 2.0


def clip_bands(predictions: np.ndarray, min_band: float = 5.0, max_band: float = 7.5) -> np.ndarray:
    """Clip predictions to the valid IELTS band range."""

    return np.clip(predictions, min_band, max_band)


def qwk_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute quadratic weighted kappa for predictions."""

    rounded = clip_bands(round_to_half_band(y_pred))
    true_ids = _to_half_band_ids(y_true)
    pred_ids = _to_half_band_ids(rounded)
    return float(cohen_kappa_score(true_ids, pred_ids, weights="quadratic"))


def qwk_eval(preds: np.ndarray, dtrain: xgb.DMatrix) -> tuple[str, float]:
    """XGBoost custom evaluation metric for QWK."""

    labels = dtrain.get_label()
    return "qwk", qwk_score(labels, preds)


def _to_half_band_ids(values: np.ndarray) -> np.ndarray:
    """Convert band scores to discrete half-band integer IDs."""

    return np.round(values * 2.0).astype(int)
