"""Statistics for paired CV fold comparisons.

Provides deterministic helpers to:
- align metrics by fold,
- compute candidate-minus-reference deltas,
- estimate a bootstrap confidence interval for the mean delta.
"""

from __future__ import annotations

import numpy as np

from scripts.ml_training.essay_scoring.comparison.models import PairwiseDeltaSummary


def pairwise_metric_delta(
    reference_by_fold: dict[str, float],
    candidate_by_fold: dict[str, float],
) -> dict[str, float]:
    """Compute candidate-reference deltas aligned by fold id."""

    reference_ids = set(reference_by_fold.keys())
    candidate_ids = set(candidate_by_fold.keys())
    if reference_ids != candidate_ids:
        raise ValueError(
            "Fold mismatch between reference and candidate runs. "
            f"reference_only={sorted(reference_ids - candidate_ids)} "
            f"candidate_only={sorted(candidate_ids - reference_ids)}"
        )
    return {
        fold_id: float(candidate_by_fold[fold_id] - reference_by_fold[fold_id])
        for fold_id in sorted(reference_by_fold.keys(), key=int)
    }


def summarize_deltas(
    *,
    deltas: dict[str, float],
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> PairwiseDeltaSummary:
    """Summarize fold deltas with mean/std and 95% bootstrap CI."""

    fold_ids = sorted(deltas.keys(), key=int)
    delta_values = np.array([deltas[fold_id] for fold_id in fold_ids], dtype=float)
    ci_low, ci_high = bootstrap_mean_ci(
        deltas=delta_values,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    return PairwiseDeltaSummary(
        n_folds=int(delta_values.size),
        mean_delta=float(np.mean(delta_values)),
        std_delta=float(np.std(delta_values)),
        bootstrap_ci_low=ci_low,
        bootstrap_ci_high=ci_high,
        deltas_by_fold={fold_id: float(deltas[fold_id]) for fold_id in fold_ids},
    )


def bootstrap_mean_ci(
    *,
    deltas: np.ndarray,
    bootstrap_iterations: int,
    bootstrap_seed: int,
) -> tuple[float, float]:
    """Return a 95% bootstrap CI for the mean of paired deltas."""

    if deltas.size == 0:
        raise ValueError("Cannot bootstrap an empty delta vector.")
    if deltas.size == 1:
        value = float(deltas[0])
        return value, value

    rng = np.random.default_rng(bootstrap_seed)
    sampled_indices = rng.integers(
        low=0,
        high=deltas.size,
        size=(int(bootstrap_iterations), int(deltas.size)),
    )
    sampled_means = deltas[sampled_indices].mean(axis=1)
    ci_low = float(np.quantile(sampled_means, 0.025))
    ci_high = float(np.quantile(sampled_means, 0.975))
    return ci_low, ci_high
