"""Prediction mapping and post-hoc calibration utilities for essay scoring.

Purpose:
    Convert continuous regression outputs (`y_pred_raw`) into discrete half-band predictions
    (`y_pred`) using either:
    - the baseline mapping (round-to-nearest-half-band + clip), or
    - a post-hoc calibrated mapping that learns monotone cutpoints that improve tail behavior.

    Gate D uses these mappings to reduce grade-band compression and tail bias *without* changing
    the underlying feature extraction pipeline (feature store reuse remains valid).

Relationships:
    - Used by `scripts.ml_training.essay_scoring.cross_validation` to optionally map predictions
      before computing CV metrics and residual diagnostics artifacts/reports.
    - Residual diagnostics persist both `y_pred_raw` and mapped `y_pred`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class PredictionMapping(str, Enum):
    """Mapping mode from `y_pred_raw` to discrete half-band predictions."""

    ROUND_HALF_BAND = "round_half_band"
    QWK_CUTPOINTS_LFO = "qwk_cutpoints_lfo"


@dataclass(frozen=True)
class CutpointCalibration:
    """Monotone cutpoints that map continuous predictions to half-band classes."""

    min_band: float
    max_band: float
    band_values: np.ndarray
    cutpoints: np.ndarray

    def apply(self, y_pred_raw: np.ndarray) -> np.ndarray:
        return apply_cutpoints(
            y_pred_raw=y_pred_raw,
            cutpoints=self.cutpoints,
            band_values=self.band_values,
            min_band=self.min_band,
            max_band=self.max_band,
        )


def half_band_values(*, min_band: float, max_band: float) -> np.ndarray:
    """Return the supported half-band values in [min_band, max_band]."""

    step = 0.5
    n = int(round((max_band - min_band) / step)) + 1
    values = min_band + step * np.arange(n, dtype=float)
    # Defensive: avoid tiny float drift (e.g. 3.5000000004)
    return np.round(values * 2.0) / 2.0


def map_round_half_band(*, y_pred_raw: np.ndarray, min_band: float, max_band: float) -> np.ndarray:
    """Baseline mapping: round-to-nearest-half-band then clip."""

    rounded = np.round(y_pred_raw.astype(float) * 2.0) / 2.0
    return np.clip(rounded, min_band, max_band)


def apply_cutpoints(
    *,
    y_pred_raw: np.ndarray,
    cutpoints: np.ndarray,
    band_values: np.ndarray,
    min_band: float,
    max_band: float,
) -> np.ndarray:
    """Apply cutpoints to map predictions into discrete half-band values."""

    if int(band_values.size) < 2:
        raise ValueError("band_values must contain at least 2 classes")
    if int(cutpoints.size) != int(band_values.size) - 1:
        raise ValueError("cutpoints must have length len(band_values)-1")

    clipped = np.clip(y_pred_raw.astype(float), min_band, max_band)
    class_ids = np.digitize(clipped, cutpoints.astype(float), right=False)
    return band_values[class_ids]


def fit_qwk_cutpoints_coordinate_ascent(
    *,
    y_true: np.ndarray,
    y_pred_raw: np.ndarray,
    min_band: float,
    max_band: float,
    max_iter: int = 10,
    candidate_quantiles: int = 64,
) -> CutpointCalibration:
    """Fit monotone cutpoints to maximize QWK via coordinate ascent.

    Notes:
        - This is a discrete, piecewise-constant objective. Coordinate ascent is deterministic and
          fast enough for CV use at ELLIPSE scale.
        - Predictions are clipped to [min_band, max_band] before thresholding.
        - Initialization matches the marginal grade distribution using quantiles of predictions.
    """

    band_vals = half_band_values(min_band=min_band, max_band=max_band)
    n_classes = int(band_vals.size)
    true_ids = _to_class_ids(y_true.astype(float), min_band=min_band)

    preds = np.clip(y_pred_raw.astype(float), min_band, max_band)
    if preds.size == 0:
        raise ValueError("Empty y_pred_raw for cutpoint fitting")

    # Quantile initialization: match predicted class proportions to true label proportions.
    counts = np.bincount(true_ids, minlength=n_classes).astype(float)
    cum = np.cumsum(counts)[:-1]
    qs = (cum / float(np.sum(counts))).astype(float)
    cutpoints = np.quantile(preds, qs).astype(float)
    cutpoints = _enforce_strictly_increasing(cutpoints)

    best_qwk = _qwk_from_class_ids(true_ids, np.digitize(preds, cutpoints, right=False), n_classes)
    best = cutpoints.copy()

    if candidate_quantiles < 8:
        raise ValueError("candidate_quantiles must be >= 8 for stable cutpoint search")

    for _ in range(max_iter):
        improved = False
        for idx in range(best.size):
            low = best[idx - 1] if idx > 0 else float(min_band)
            high = best[idx + 1] if idx + 1 < best.size else float(max_band)
            if not low < high:
                continue

            mask = (preds > low) & (preds < high)
            region = preds[mask]
            if int(region.size) < 4:
                continue

            qs_region = np.linspace(0.05, 0.95, candidate_quantiles, dtype=float)
            candidates = np.unique(np.quantile(region, qs_region).astype(float))
            for candidate in candidates:
                if not (low < float(candidate) < high):
                    continue
                trial = best.copy()
                trial[idx] = float(candidate)
                trial = _enforce_strictly_increasing(trial)
                if np.any(trial <= min_band) or np.any(trial >= max_band):
                    # Keep cutpoints inside the clipped prediction range.
                    continue

                qwk = _qwk_from_class_ids(
                    true_ids, np.digitize(preds, trial, right=False), n_classes
                )
                if qwk > best_qwk + 1e-7:
                    best_qwk = qwk
                    best = trial
                    improved = True

        if not improved:
            break

    return CutpointCalibration(
        min_band=float(min_band),
        max_band=float(max_band),
        band_values=band_vals.astype(float),
        cutpoints=best.astype(float),
    )


def _to_class_ids(values: np.ndarray, *, min_band: float) -> np.ndarray:
    """Convert half-band floats to contiguous class IDs starting at min_band."""

    min_half_id = int(round(float(min_band) * 2.0))
    half_ids = np.round(values.astype(float) * 2.0).astype(int)
    return half_ids - min_half_id


def _qwk_from_class_ids(y_true_ids: np.ndarray, y_pred_ids: np.ndarray, n_classes: int) -> float:
    """Fast QWK implementation using confusion matrix math (quadratic weights)."""

    if int(n_classes) < 2:
        return 0.0

    y_true = y_true_ids.astype(int)
    y_pred = y_pred_ids.astype(int)
    y_true = np.clip(y_true, 0, n_classes - 1)
    y_pred = np.clip(y_pred, 0, n_classes - 1)

    n = int(y_true.size)
    if n == 0:
        return 0.0

    conf = np.bincount(y_true * n_classes + y_pred, minlength=n_classes * n_classes).reshape(
        (n_classes, n_classes)
    )
    true_hist = conf.sum(axis=1).astype(float)
    pred_hist = conf.sum(axis=0).astype(float)
    expected = np.outer(true_hist, pred_hist) / float(n)

    w = np.zeros((n_classes, n_classes), dtype=float)
    denom = float((n_classes - 1) ** 2)
    for i in range(n_classes):
        for j in range(n_classes):
            w[i, j] = ((i - j) ** 2) / denom

    observed_score = float(np.sum(w * conf))
    expected_score = float(np.sum(w * expected))
    if expected_score <= 0:
        return 0.0
    return 1.0 - (observed_score / expected_score)


def _enforce_strictly_increasing(values: np.ndarray, *, eps: float = 1e-6) -> np.ndarray:
    """Ensure a strictly increasing cutpoint vector (monotone thresholds)."""

    out = values.astype(float).copy()
    for i in range(1, out.size):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + eps
    return out
