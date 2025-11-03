"""Analytical helpers for CJ confidence validation.

This module replicates the current confidence heuristics and compares them
against Fisher-Information-based standard error estimates for Bradley–Terry
abilities under non-adaptive random pairing. It provides utilities for
generating summary tables that highlight mismatches between the existing
logistic comparison-count curve and statistically grounded confidence metrics.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


# --- Current Production Heuristics -------------------------------------------------

def logistic_comparison_confidence(comparison_count: int) -> float:
    """Reproduce the comparison-count logistic used in `confidence_calculator`.

    Args:
        comparison_count: Number of comparisons involving a single essay.

    Returns:
        Confidence contribution in [0, 1].
    """
    return 1.0 / (1.0 + math.exp(-(comparison_count - 5) / 3.0))


def logistic_confidence_label(confidence: float) -> str:
    """Map a confidence score to the production labels."""
    if confidence >= 0.75:
        return "HIGH"
    if confidence >= 0.40:
        return "MID"
    return "LOW"


# --- Bradley–Terry Information Approximations --------------------------------------

def bt_standard_error_from_counts(
    comparison_count: int,
    probability: float = 0.5,
) -> float:
    """Approximate SE for a Bradley–Terry ability using Fisher Information.

    For balanced abilities the per-comparison information equals
    ``p * (1 - p)``. With random pair assignment and moderate ability
    separation, ``p`` stays close to 0.5. The variance of the MLE then
    shrinks roughly with the reciprocal of accumulated information.

    Args:
        comparison_count: Number of independent comparisons involving the essay.
        probability: Estimated Bradley–Terry win probability. Default 0.5.

    Returns:
        Approximate standard error. Infinity if the information is zero.
    """
    information = comparison_count * probability * (1.0 - probability)
    if information <= 0:
        return float("inf")
    return 1.0 / math.sqrt(information)


def probability_within_interval(delta: float, se: float) -> float:
    """Probability that a normal deviate lies within ±delta of its mean."""
    if se <= 0:
        return 1.0
    z = abs(delta) / se
    # Normal CDF via error function.
    return math.erf(z / math.sqrt(2.0))


def boundary_crossing_confidence(
    distance_to_boundary: float,
    se: float,
) -> float:
    """Probability of remaining on the same side of the nearest grade boundary."""
    within = probability_within_interval(distance_to_boundary, se)
    # within is P(|X| <= delta); convert to one-sided stay probability.
    return 0.5 + 0.5 * within


# --- n log n versus Information Targets --------------------------------------------

def comparison_budget_n_log_n(
    n_items: int,
    target_se: float,
    connectivity: float = 2.0,
) -> int:
    """Mirror the heuristic from `bt_inference.estimate_required_comparisons`."""
    if n_items <= 0:
        return 0
    k = (1.0 / target_se) ** 2 / max(n_items, 1)
    estimated = int(k * n_items * math.log(max(n_items, 2)) * connectivity)
    min_comparisons = int(n_items * connectivity)
    return max(estimated, min_comparisons)


# --- Summary Generation ------------------------------------------------------------

@dataclass(frozen=True)
class ConfidenceRow:
    comparisons: int
    logistic_confidence: float
    logistic_label: str
    approx_se: float
    boundary_distance: float
    boundary_stay_probability: float


def generate_confidence_table(
    comparison_counts: Iterable[int],
    boundary_distances: Sequence[float],
    probability: float = 0.5,
) -> list[ConfidenceRow]:
    """Generate comparison of logistic vs. Fisher-based confidence."""
    rows: list[ConfidenceRow] = []
    for count in comparison_counts:
        logistic_score = logistic_comparison_confidence(count)
        label = logistic_confidence_label(logistic_score)
        se = bt_standard_error_from_counts(count, probability)
        for boundary_distance in boundary_distances:
            stay_prob = boundary_crossing_confidence(boundary_distance, se)
            rows.append(
                ConfidenceRow(
                    comparisons=count,
                    logistic_confidence=logistic_score,
                    logistic_label=label,
                    approx_se=se,
                    boundary_distance=boundary_distance,
                    boundary_stay_probability=stay_prob,
                )
            )
    return rows


def rows_to_json(rows: Sequence[ConfidenceRow]) -> list[dict[str, float | int | str]]:
    """Serialize rows for inspection or plotting."""
    return [
        {
            "comparisons": row.comparisons,
            "logistic_confidence": round(row.logistic_confidence, 4),
            "logistic_label": row.logistic_label,
            "approx_se": round(row.approx_se, 4),
            "boundary_distance": round(row.boundary_distance, 4),
            "boundary_stay_probability": round(row.boundary_stay_probability, 4),
        }
        for row in rows
    ]


def save_summary_to_file(rows: Sequence[ConfidenceRow], output_path: Path) -> None:
    """Persist the summary table as JSON."""
    output_path.write_text(json.dumps(rows_to_json(rows), indent=2))


def main() -> None:
    """Generate a default summary for inspection."""
    counts = range(1, 31)
    boundary_distances = (0.05, 0.10, 0.15, 0.20)
    rows = generate_confidence_table(counts, boundary_distances)
    output_path = Path(__file__).with_name("cj_confidence_summary.json")
    save_summary_to_file(rows, output_path)
    print(f"Saved summary with {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    main()
