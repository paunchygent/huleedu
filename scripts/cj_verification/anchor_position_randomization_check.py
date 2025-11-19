#!/usr/bin/env python3
"""Chi-squared style verification of CJ pair position randomization.

This script simulates anchor vs student essay pairs using the same
conceptual randomization policy as the CJ Assessment Service
(per-pair 50/50 swap driven by a seeded ``random.Random`` instance).

It is intended as an offline validation tool and does not touch the
CJ database or call into service code. Instead, it mirrors the
pairwise generation pattern and swap logic to check that anchor
positions are statistically balanced across many seeds.

Typical usage (from repo root):

    python -m scripts.cj_verification.anchor_position_randomization_check \
        --n-seeds 200 --scenario both
"""

from __future__ import annotations

import argparse
import math
from random import Random
from typing import Iterable

ANCHOR_LABEL = "anchor"
STUDENT_LABEL = "student"


def _simulate_anchor_positions(
    n_anchors: int,
    n_students: int,
    seeds: Iterable[int],
) -> tuple[int, int]:
    """Return (anchor_a_total, anchor_pair_total) across all seeds.

    The simulation mirrors the nested-loop pair generation pattern
    used in CJ pair generation:

    - Essays are ordered as [anchors..., students...].
    - For each distinct unordered pair (i, j) with i < j, we decide
      whether to swap the two positions using a Bernoulli(0.5)
      draw from a seeded ``Random`` instance.
    - Any pair containing at least one anchor contributes to the
      denominator; we count how often the anchor ends up in the
      first position.
    """

    if n_anchors <= 0:
        raise ValueError("n_anchors must be > 0")
    if n_students <= 0:
        raise ValueError("n_students must be > 0")

    # Represent essays only by their role (anchor vs student). The
    # fairness of the randomization depends on swap probability and
    # loop structure, not on the actual essay content.
    essays: list[str] = [ANCHOR_LABEL] * n_anchors + [STUDENT_LABEL] * n_students

    anchor_a_total = 0
    anchor_pair_total = 0

    for seed in seeds:
        randomizer = Random(seed)

        # Iterate over all unordered pairs (i, j) with i < j
        for i in range(len(essays)):
            for j in range(i + 1, len(essays)):
                essay_a = essays[i]
                essay_b = essays[j]

                # Per-pair 50/50 swap, matching the CJ randomization policy
                if randomizer.random() < 0.5:
                    essay_a, essay_b = essay_b, essay_a

                # Only pairs involving at least one anchor are relevant
                if ANCHOR_LABEL in (essay_a, essay_b):
                    anchor_pair_total += 1
                    if essay_a == ANCHOR_LABEL:
                        anchor_a_total += 1

    return anchor_a_total, anchor_pair_total


def _compute_chi_squared(anchor_a_total: int, anchor_pair_total: int) -> float:
    """Compute chi-squared statistic for anchor A/B positions under 50/50 null.

    We treat the outcome as a 2x1 table:

        - Category 1: anchor appears in position A
        - Category 2: anchor appears in position B

    with expected probability 0.5 for each. The statistic is:

        chi2 = Σ ( (obs_i - exp_i)^2 / exp_i ), df = 1
    """

    if anchor_pair_total <= 0:
        raise ValueError("anchor_pair_total must be > 0 to compute chi-squared")

    expected = anchor_pair_total / 2.0
    anchor_b_total = anchor_pair_total - anchor_a_total

    return ((anchor_a_total - expected) ** 2) / expected + (
        (anchor_b_total - expected) ** 2
    ) / expected


def _chi2_p_value_df1(chi2_value: float) -> float:
    """Approximate p-value for chi-squared(df=1) using the error function.

    For df=1, the CDF has the closed form:

        CDF(x) = erf(sqrt(x / 2))

    so the (upper-tail) p-value is:

        p = 1 - erf(sqrt(x / 2)).

    This avoids introducing scipy as a dependency while still giving
    a useful indication of how extreme the observed imbalance is
    under a 50/50 null hypothesis.
    """

    if chi2_value < 0:
        raise ValueError("chi2_value must be non-negative")

    return 1.0 - math.erf(math.sqrt(chi2_value / 2.0))


def _run_scenario(label: str, n_anchors: int, n_students: int, n_seeds: int) -> None:
    """Run a single simulation scenario and print summary statistics."""

    print(f"\n=== Scenario: {label} ===")
    print(f"Anchors: {n_anchors}, Students: {n_students}, Seeds: {n_seeds}")

    seeds = range(n_seeds)
    anchor_a_total, anchor_pair_total = _simulate_anchor_positions(
        n_anchors=n_anchors,
        n_students=n_students,
        seeds=seeds,
    )

    ratio = anchor_a_total / anchor_pair_total if anchor_pair_total else float("nan")
    chi2 = _compute_chi_squared(anchor_a_total, anchor_pair_total)
    p_value = _chi2_p_value_df1(chi2)

    print(f"Total anchor-involving pairs: {anchor_pair_total}")
    print(f"Anchor in essay_a: {anchor_a_total} ({ratio:.4f})")
    print(f"Chi-squared (df=1): {chi2:.4f}")
    print(f"p-value (two-sided against 50/50): {p_value:.4f}")


def main() -> None:
    """Entry point for CLI execution."""

    parser = argparse.ArgumentParser(
        description=(
            "Offline chi-squared style validation of CJ pair position randomization.\n\n"
            "By default runs two scenarios:\n"
            "  - small: 1 anchor + 2 students (mirrors unit test fixture)\n"
            "  - large: 12 anchors + 12 students (ENG5-scale batch)\n"
        )
    )
    parser.add_argument(
        "--n-seeds",
        type=int,
        default=200,
        help="Number of distinct seeds to sweep over (default: 200)",
    )
    parser.add_argument(
        "--scenario",
        choices=["small", "large", "both"],
        default="both",
        help="Which scenario to run (default: both)",
    )

    args = parser.parse_args()

    if args.n_seeds <= 0:
        raise SystemExit("--n-seeds must be a positive integer")

    if args.scenario in ("small", "both"):
        _run_scenario("small (1 anchor, 2 students)", 1, 2, args.n_seeds)

    if args.scenario in ("large", "both"):
        _run_scenario("large (12 anchors, 12 students)", 12, 12, args.n_seeds)


if __name__ == "__main__":  # pragma: no cover
    main()
