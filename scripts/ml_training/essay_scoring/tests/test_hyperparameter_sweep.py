"""Tests for the CV hyperparameter sweep helpers."""

from __future__ import annotations

from pathlib import Path

from scripts.ml_training.essay_scoring.hyperparameter_sweep import (
    compute_tail_slice_metrics,
    iter_grid_configs,
    stable_config_id,
)


def test_stable_config_id_is_order_invariant() -> None:
    params_a = {"max_depth": 3, "reg_lambda": 2.0, "min_child_weight": 10}
    params_b = {"min_child_weight": 10, "reg_lambda": 2.0, "max_depth": 3}
    assert stable_config_id(params_a) == stable_config_id(params_b)


def test_iter_grid_configs_cartesian_product_is_deterministic() -> None:
    grid = {"a": [1, 2], "b": [10]}
    configs = list(iter_grid_configs(grid))
    assert configs == [{"a": 1, "b": 10}, {"a": 2, "b": 10}]


def test_compute_tail_slice_metrics_and_mid_band_accuracy(tmp_path: Path) -> None:
    residuals_path = tmp_path / "residuals.csv"
    residuals_path.write_text(
        "y_true,abs_residual,residual,within_half_band\n"
        "1.5,0.5,0.5,1\n"
        "4.0,1.0,-1.0,0\n"
        "3.0,0.0,0.0,1\n",
        encoding="utf-8",
    )

    low_tail, high_tail, mid_adjacent_accuracy = compute_tail_slice_metrics(residuals_path)
    assert low_tail.count == 1
    assert high_tail.count == 1
    assert mid_adjacent_accuracy == 1.0
