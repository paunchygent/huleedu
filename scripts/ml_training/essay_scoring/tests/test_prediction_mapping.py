"""Tests for prediction mapping + cutpoint calibration utilities."""

from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.training.prediction_mapping import (
    apply_cutpoints,
    fit_qwk_cutpoints_coordinate_ascent,
    half_band_values,
    map_round_half_band,
)


def test_half_band_values_step_and_bounds() -> None:
    values = half_band_values(min_band=1.0, max_band=3.0)
    assert values.tolist() == [1.0, 1.5, 2.0, 2.5, 3.0]


def test_round_half_band_mapping_clips() -> None:
    mapped = map_round_half_band(
        y_pred_raw=np.array([0.9, 1.26, 2.74, 3.6], dtype=float),
        min_band=1.0,
        max_band=3.0,
    )
    assert mapped.tolist() == [1.0, 1.5, 2.5, 3.0]


def test_fit_cutpoints_produces_monotone_thresholds_and_valid_outputs() -> None:
    min_band = 1.0
    max_band = 3.0
    y_true = np.array([1.0, 1.5, 2.0, 2.5, 3.0] * 20, dtype=float)
    # Deliberately compressed predictions (common failure mode in Gate C).
    y_pred_raw = y_true * 0.7 + 0.6

    calibration = fit_qwk_cutpoints_coordinate_ascent(
        y_true=y_true,
        y_pred_raw=y_pred_raw,
        min_band=min_band,
        max_band=max_band,
        max_iter=5,
        candidate_quantiles=16,
    )

    assert calibration.cutpoints.size == calibration.band_values.size - 1
    assert np.all(np.diff(calibration.cutpoints) > 0)

    mapped = calibration.apply(y_pred_raw)
    allowed = set(half_band_values(min_band=min_band, max_band=max_band).tolist())
    assert set(np.unique(mapped).tolist()).issubset(allowed)


def test_apply_cutpoints_maps_to_band_values() -> None:
    band_values = half_band_values(min_band=1.0, max_band=2.0)
    cutpoints = np.array([1.25, 1.75], dtype=float)
    mapped = apply_cutpoints(
        y_pred_raw=np.array([1.0, 1.3, 1.6, 2.0], dtype=float),
        cutpoints=cutpoints,
        band_values=band_values,
        min_band=1.0,
        max_band=2.0,
    )
    assert mapped.tolist() == [1.0, 1.5, 1.5, 2.0]
