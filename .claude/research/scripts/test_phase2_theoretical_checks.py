"""Tests for phase2_theoretical_checks utilities."""

from __future__ import annotations

import math

from .phase2_theoretical_checks import run_experiments


def test_random_pair_simulation_monotonic_se() -> None:
    """Median SE should decrease as target comparisons increase."""
    targets = (4, 8, 12, 20)
    results = run_experiments(targets, n_items=8, base_seed=123)
    median_ses = [r.median_se for r in results]
    assert all(median_ses[i] > median_ses[i + 1] for i in range(len(median_ses) - 1))


def test_random_pair_simulation_inflation_ratio_bounds() -> None:
    """Empirical SE should stay within a reasonable inflation band."""
    results = run_experiments((8,), n_items=10, base_seed=456)
    ratio = results[0].median_se / results[0].theoretical_se
    assert math.isfinite(ratio)
    assert 1.0 <= ratio <= 2.0
