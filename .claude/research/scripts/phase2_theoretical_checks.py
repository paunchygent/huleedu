"""Phase 2 theoretical validation helpers.

This module reproduces the analytical sanity checks performed during
Phase 2 of the CJ confidence validation task. It allows future sessions
to re-run the Fisher-information approximation experiments that compare
the `compute_bt_standard_errors` implementation against the theoretical
`2 / sqrt(n)` rule of thumb under random non-adaptive pairing.

Usage:
    pdm run python -m .claude.research.scripts.phase2_theoretical_checks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import choix  # type: ignore
import numpy as np

from services.cj_assessment_service.cj_core_logic import bt_inference


@dataclass(frozen=True)
class SimulationResult:
    """Container for a single random-pairing simulation outcome."""

    target_min_comparisons: int
    mean_comparisons: float
    median_se: float
    theoretical_se: float


def run_random_pair_simulation(
    n_items: int,
    target_min_comparisons: int,
    seed: int,
) -> SimulationResult:
    """Generate random pair outcomes until every item meets the target count."""

    rng = np.random.default_rng(seed)
    counts = np.zeros(n_items, dtype=int)
    comparisons: list[tuple[int, int]] = []

    while np.min(counts) < target_min_comparisons:
        i, j = rng.choice(n_items, size=2, replace=False)
        winner, loser = (i, j) if rng.random() < 0.5 else (j, i)
        comparisons.append((winner, loser))
        counts[winner] += 1
        counts[loser] += 1

    params = choix.ilsr_pairwise(n_items, comparisons, alpha=1e-3)
    se = bt_inference.compute_bt_standard_errors(n_items, comparisons, np.asarray(params))

    # Exclude reference item with SE=0.0
    positive_se = se[:-1]
    mean_count = counts[:-1].mean()
    theoretical = 2.0 / np.sqrt(mean_count)

    return SimulationResult(
        target_min_comparisons=target_min_comparisons,
        mean_comparisons=mean_count,
        median_se=float(np.median(positive_se)),
        theoretical_se=float(theoretical),
    )


def run_experiments(
    targets: Iterable[int],
    n_items: int = 10,
    base_seed: int = 42,
) -> list[SimulationResult]:
    """Execute simulations for a collection of comparison targets."""

    results: list[SimulationResult] = []
    for offset, target in enumerate(targets):
        seed = base_seed + offset * 17
        results.append(run_random_pair_simulation(n_items, target, seed))
    return results


def main() -> None:
    """Run the default experiment set and print a summary table."""

    targets = (4, 8, 12, 20)
    results = run_experiments(targets)

    print("target_min\tmean_comparisons\tmedian_se\ttheoretical_se\tinflation_ratio")
    for r in results:
        ratio = r.median_se / r.theoretical_se if r.theoretical_se else float("inf")
        print(
            f"{r.target_min_comparisons:>10}\t"
            f"{r.mean_comparisons:>16.2f}\t"
            f"{r.median_se:>9.3f}\t"
            f"{r.theoretical_se:>13.3f}\t"
            f"{ratio:>14.3f}"
        )


if __name__ == "__main__":
    main()
