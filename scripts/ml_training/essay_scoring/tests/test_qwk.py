"""Tests for quadratic weighted kappa utilities."""

from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.training.qwk import qwk_score


def test_qwk_score_handles_half_band_floats() -> None:
    y_true = np.array([5.0, 5.5, 6.0, 6.5, 7.0, 7.5])
    y_pred = np.array([5.0, 5.5, 6.0, 6.5, 7.0, 7.5])

    score = qwk_score(y_true, y_pred)

    assert score == 1.0
