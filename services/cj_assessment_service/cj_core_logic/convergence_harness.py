"""Convergence harness for CJ Assessment (PR-7 / US-005.4).

This module provides a small, test-focused harness that simulates
iterative comparative judgement over synthetic nets using the real
Bradley–Terry scoring helper and stability check.

Design goals:
    - Exercise the BT scoring core (`compute_bt_scores_and_se`) and
      `check_score_stability` in a configurable convergence loop.
    - Model Phase-1 / Phase-2 behaviour at the graph level:
        * Phase-1 (coverage): only unseen pairs are scheduled until the
          n-choose-2 comparison graph is covered or the global budget is
          exhausted.
        * Phase-2 (resampling): once coverage is complete, subsequent
          iterations reuse the same comparison graph (resampling existing
          edges) until stability or caps are reached.
    - Keep the harness database-agnostic and fast by operating purely
      in memory over `EssayForComparison` and synthetic `CJ_ComparisonPair`
      instances. The production scorer uses the same BT helper under the
      hood, so convergence semantics remain aligned.

This harness is intended for unit-level convergence tests and does not
perform any persistence or side-effectful operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from random import Random
from typing import Dict, Iterable, List, Tuple
from uuid import uuid4

from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field

from services.cj_assessment_service.cj_core_logic.scoring_ranking import (
    BTScoringResult,
    check_score_stability,
    compute_bt_scores_and_se,
)
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair

logger = create_service_logger("cj_assessment_service.convergence_harness")


class ConvergenceCapReason(str, Enum):
    """Reason why the convergence harness stopped."""

    STABILITY = "stability"
    ITERATIONS = "iterations"
    BUDGET = "budget"


class HarnessResult(BaseModel):
    """Result of running the convergence harness.

    This model is intentionally simple and test-oriented. It captures:

    - Final BT scores after the last iteration.
    - Whether stability was achieved before caps.
    - Which cap fired (stability, iterations, or budget).
    - High-level diagnostics for debugging convergence behaviour.
    """

    final_scores: dict[str, float] = Field(
        description="Final BT scores keyed by essay ID.",
    )
    stability_achieved: bool = Field(
        description="True when score changes fell below the stability threshold.",
    )
    cap_reason: ConvergenceCapReason = Field(
        description="Primary reason the harness stopped iterating.",
    )
    iterations_run: int = Field(
        ge=0,
        description="Number of iterations actually executed.",
    )
    total_comparisons: int = Field(
        ge=0,
        description="Total comparison edges simulated across all iterations.",
    )
    comparisons_per_iteration: list[int] = Field(
        default_factory=list,
        description="Number of comparisons scheduled per iteration.",
    )
    max_score_change: float | None = Field(
        default=None,
        description=(
            "Maximum BT score change between the last two iterations. "
            "None when stability has never been evaluated."
        ),
    )
    se_summary: dict[str, float | int] | None = Field(
        default=None,
        description=(
            "Batch-level SE diagnostics from the final BT run "
            "(see BTScoringResult.se_summary for shape)."
        ),
    )


@dataclass(frozen=True)
class ConvergenceHarnessConfig:
    """Configuration knobs for the convergence harness.

    These map onto the documented convergence settings used in the
    continuation loop:

    - comparisons_per_iteration: synthetic iteration size used by the harness
    - min_comparisons_for_stability_check: MIN_COMPARISONS_FOR_STABILITY_CHECK
    - max_iterations: MAX_ITERATIONS
    - max_pairwise_comparisons: MAX_PAIRWISE_COMPARISONS
    - stability_threshold: SCORE_STABILITY_THRESHOLD
    """

    comparisons_per_iteration: int
    min_comparisons_for_stability_check: int
    max_iterations: int
    max_pairwise_comparisons: int
    stability_threshold: float


def _build_all_pairs(essay_ids: Iterable[str]) -> list[tuple[str, str]]:
    """Return all unique unordered pairs (n-choose-2) for the given IDs."""

    sorted_ids = sorted(essay_ids)
    return [(a, b) for a, b in combinations(sorted_ids, 2)]


def _simulate_winner(
    essay_a_id: str,
    essay_b_id: str,
    true_scores: Dict[str, float],
    rng: Random,
) -> Tuple[str, str, str]:
    """Return synthetic winner field and normalized pair for a comparison.

    The higher true score wins deterministically; ties are broken at random.
    Returns a tuple of (winner_field, essay_a_id, essay_b_id) where:

    - winner_field is \"essay_a\" or \"essay_b\" for CJ_ComparisonPair.winner
    - essay_a_id / essay_b_id correspond to the winner/loser ordering
    """

    score_a = true_scores.get(essay_a_id, 0.0)
    score_b = true_scores.get(essay_b_id, 0.0)

    if score_a == score_b:
        # Break ties randomly to avoid degenerate nets in tests.
        winner_is_a = rng.random() < 0.5
    else:
        winner_is_a = score_a > score_b

    if winner_is_a:
        return "essay_a", essay_a_id, essay_b_id
    return "essay_b", essay_a_id, essay_b_id


def run_convergence_harness(
    *,
    essays: list[EssayForComparison],
    true_scores: dict[str, float],
    config: ConvergenceHarnessConfig,
    random_seed: int | None = None,
) -> HarnessResult:
    """Run a synthetic convergence loop over the given essays.

    The harness operates purely in memory:

    - It builds the full n-choose-2 comparison graph over `essays`.
    - Phase-1 (coverage): each new iteration schedules only unseen pairs
      until all edges have been compared at least once, or the global
      `max_pairwise_comparisons` budget is exhausted.
    - Phase-2 (resampling): once coverage is complete, later iterations
      schedule comparisons by resampling from the same graph, subject to
      the remaining budget.
    - After each iteration, BT scores and SE diagnostics are computed via
      `compute_bt_scores_and_se`, and stability is evaluated using
      `check_score_stability` once the global minimum comparison count is
      reached.

    The function returns a `HarnessResult` summarizing convergence behaviour.
    """
    if len(essays) < 2:
        raise ValueError("Convergence harness requires at least two essays.")

    if config.max_pairwise_comparisons <= 0:
        raise ValueError("max_pairwise_comparisons must be positive.")

    rng = Random(random_seed)
    essay_ids = [essay.id for essay in essays]
    all_pairs = _build_all_pairs(essay_ids)
    total_possible_pairs = len(all_pairs)

    logger.info(
        "Starting convergence harness over synthetic net",
        extra={
            "essay_count": len(essay_ids),
            "total_possible_pairs": total_possible_pairs,
            "comparisons_per_iteration": config.comparisons_per_iteration,
            "min_comparisons_for_stability_check": config.min_comparisons_for_stability_check,
            "max_iterations": config.max_iterations,
            "max_pairwise_comparisons": config.max_pairwise_comparisons,
            "stability_threshold": config.stability_threshold,
        },
    )

    comparisons: List[CJ_ComparisonPair] = []
    observed_pairs: set[tuple[str, str]] = set()
    comparisons_per_iteration: list[int] = []
    previous_scores: dict[str, float] = {}
    stability_achieved = False
    max_score_change: float | None = None
    last_se_summary: dict[str, float | int] | None = None
    cap_reason: ConvergenceCapReason = ConvergenceCapReason.ITERATIONS

    for iteration in range(1, config.max_iterations + 1):
        budget_remaining = config.max_pairwise_comparisons - len(comparisons)
        if budget_remaining <= 0:
            cap_reason = ConvergenceCapReason.BUDGET
            logger.info(
                "Stopping convergence harness due to exhausted budget before iteration",
                extra={
                    "iteration": iteration,
                    "total_comparisons": len(comparisons),
                    "max_pairwise_comparisons": config.max_pairwise_comparisons,
                },
            )
            break

        coverage_complete = len(observed_pairs) >= total_possible_pairs

        if not coverage_complete:
            candidate_pairs = [pair for pair in all_pairs if pair not in observed_pairs]
            phase = "coverage"
        else:
            candidate_pairs = list(all_pairs)
            phase = "resampling"

        if not candidate_pairs:
            # No pairs left to schedule under current semantics; treat as
            # budget-driven stop since additional comparisons would require
            # expanding the net.
            cap_reason = ConvergenceCapReason.BUDGET
            logger.info(
                "Stopping convergence harness: no candidate pairs available",
                extra={
                    "iteration": iteration,
                    "phase": phase,
                    "total_comparisons": len(comparisons),
                },
            )
            break

        comparisons_this_iter = min(
            config.comparisons_per_iteration,
            budget_remaining,
            len(candidate_pairs),
        )
        if comparisons_this_iter <= 0:
            cap_reason = ConvergenceCapReason.BUDGET
            logger.info(
                "Stopping convergence harness: zero comparisons allowed this iteration",
                extra={
                    "iteration": iteration,
                    "phase": phase,
                    "budget_remaining": budget_remaining,
                },
            )
            break

        rng.shuffle(candidate_pairs)
        selected_pairs = candidate_pairs[:comparisons_this_iter]

        new_comparisons: list[CJ_ComparisonPair] = []
        for essay_id_a, essay_id_b in selected_pairs:
            winner_field, essay_a_id, essay_b_id = _simulate_winner(
                essay_a_id=essay_id_a,
                essay_b_id=essay_id_b,
                true_scores=true_scores,
                rng=rng,
            )
            new_comparisons.append(
                CJ_ComparisonPair(
                    cj_batch_id=0,
                    essay_a_els_id=essay_a_id,
                    essay_b_els_id=essay_b_id,
                    winner=winner_field,
                    prompt_text="synthetic_convergence_harness",
                )
            )
            normalized_pair: tuple[str, str] = tuple(sorted((essay_id_a, essay_id_b)))  # type: ignore[assignment]
            observed_pairs.add(normalized_pair)

        comparisons.extend(new_comparisons)
        comparisons_per_iteration.append(len(new_comparisons))

        logger.debug(
            "Completed convergence harness iteration",
            extra={
                "iteration": iteration,
                "phase": phase,
                "comparisons_this_iteration": len(new_comparisons),
                "total_comparisons": len(comparisons),
                "coverage_complete": coverage_complete,
            },
        )

        # Compute BT scores and SE diagnostics after each iteration.
        bt_result: BTScoringResult = compute_bt_scores_and_se(
            all_essays=essays,
            comparisons=comparisons,
            cj_batch_id=0,
            correlation_id=uuid4(),
        )
        current_scores = bt_result.scores
        last_se_summary = bt_result.se_summary

        # Only evaluate stability once the global minimum comparison count is met.
        if len(comparisons) >= config.min_comparisons_for_stability_check:
            max_score_change = check_score_stability(
                current_bt_scores=current_scores,
                previous_bt_scores=previous_scores,
                stability_threshold=config.stability_threshold,
            )
            if max_score_change <= config.stability_threshold:
                stability_achieved = True
                cap_reason = ConvergenceCapReason.STABILITY
                logger.info(
                    "Convergence harness achieved stability",
                    extra={
                        "iteration": iteration,
                        "total_comparisons": len(comparisons),
                        "max_score_change": max_score_change,
                        "stability_threshold": config.stability_threshold,
                    },
                )
                previous_scores = current_scores
                break

        previous_scores = current_scores

    iterations_run = len(comparisons_per_iteration)

    if not stability_achieved and iterations_run >= config.max_iterations:
        cap_reason = ConvergenceCapReason.ITERATIONS

    logger.info(
        "Convergence harness completed",
        extra={
            "iterations_run": iterations_run,
            "total_comparisons": len(comparisons),
            "stability_achieved": stability_achieved,
            "cap_reason": cap_reason.value,
        },
    )

    return HarnessResult(
        final_scores=previous_scores,
        stability_achieved=stability_achieved,
        cap_reason=cap_reason,
        iterations_run=iterations_run,
        total_comparisons=len(comparisons),
        comparisons_per_iteration=comparisons_per_iteration,
        max_score_change=max_score_change,
        se_summary=last_se_summary,
    )


__all__ = [
    "ConvergenceCapReason",
    "ConvergenceHarnessConfig",
    "HarnessResult",
    "run_convergence_harness",
]
