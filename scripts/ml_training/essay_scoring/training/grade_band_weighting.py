"""Grade-band weighting utilities for essay scoring model training.

Purpose:
    Provide a small set of *opt-in* training-time weighting schemes to mitigate label imbalance
    across discrete half-band grade labels (e.g. 1.0, 1.5, 2.0...). These weights are intended to
    reduce grade-band compression and tail bias without changing the model architecture or feature
    set.

Relationships:
    - Used by CV-first Gate D experiments in `scripts.ml_training.essay_scoring.cross_validation`.
    - Weights are passed into XGBoost via `xgboost.DMatrix(..., weight=...)` in
      `scripts.ml_training.essay_scoring.training.trainer`.
"""

from __future__ import annotations

from enum import Enum

import numpy as np


class GradeBandWeighting(str, Enum):
    """Training-time grade-band weighting schemes."""

    NONE = "none"
    SQRT_INV_FREQ = "sqrt_inv_freq"


def compute_grade_band_sample_weights(
    y_true: np.ndarray,
    *,
    mode: GradeBandWeighting,
    cap: float,
) -> np.ndarray | None:
    """Compute per-sample weights for grade-band imbalance mitigation.

    Args:
        y_true: Ground-truth band labels (half-step floats).
        mode: Weighting mode.
        cap: Maximum per-sample weight (rare bands are boosted up to this cap).

    Returns:
        A float32 weight vector aligned with y_true, or None when mode=NONE.
    """

    if mode == GradeBandWeighting.NONE:
        return None

    if cap <= 0:
        raise ValueError("cap must be > 0 for grade-band weighting")

    labels = y_true.astype(float)
    unique, counts = np.unique(labels, return_counts=True)
    if unique.size == 0:
        return None

    median_freq = float(np.median(counts))
    if median_freq <= 0:
        return None

    if mode == GradeBandWeighting.SQRT_INV_FREQ:
        weights_by_band = {
            float(band): min(float(cap), float(np.sqrt(median_freq / float(count))))
            for band, count in zip(unique, counts, strict=True)
        }
    else:
        raise ValueError(f"Unsupported grade-band weighting mode: {mode}")

    weights = np.array([weights_by_band[float(label)] for label in labels], dtype=np.float32)
    return weights
