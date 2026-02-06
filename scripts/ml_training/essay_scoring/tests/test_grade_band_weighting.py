"""Tests for grade-band weighting utilities."""

from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.training.grade_band_weighting import (
    GradeBandWeighting,
    compute_grade_band_sample_weights,
)


def test_none_mode_returns_none() -> None:
    weights = compute_grade_band_sample_weights(
        np.array([1.0, 2.0, 3.0], dtype=np.float32),
        mode=GradeBandWeighting.NONE,
        cap=3.0,
    )
    assert weights is None


def test_sqrt_inv_freq_boosts_rare_bands() -> None:
    y = np.array([1.0] * 100 + [5.0] * 10, dtype=np.float32)
    weights = compute_grade_band_sample_weights(
        y,
        mode=GradeBandWeighting.SQRT_INV_FREQ,
        cap=3.0,
    )
    assert weights is not None
    assert float(weights[0]) < float(weights[-1])
    assert float(weights[-1]) <= 3.0


def test_cap_applies_to_extreme_imbalance() -> None:
    y = np.array([1.0] * 1000 + [5.0], dtype=np.float32)
    weights = compute_grade_band_sample_weights(
        y,
        mode=GradeBandWeighting.SQRT_INV_FREQ,
        cap=3.0,
    )
    assert weights is not None
    assert float(weights[-1]) == 3.0
