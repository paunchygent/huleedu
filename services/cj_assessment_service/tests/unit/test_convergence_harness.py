"""Forward-looking convergence harness specs for CJ Assessment (PR-7).

These tests are intentionally marked xfail and serve purely as behavioural
specs for the planned convergence harness work (US-005.4 / PR-7). They do
not exercise real code paths yet and are expected to be rewritten once the
harness is implemented.
"""

from __future__ import annotations

from services.cj_assessment_service.cj_core_logic.convergence_harness import (
    ConvergenceCapReason,
    ConvergenceHarnessConfig,
    run_convergence_harness,
)
from services.cj_assessment_service.models_api import EssayForComparison


def _make_synthetic_essays() -> list[EssayForComparison]:
    """Create a small synthetic net of essays."""

    return [
        EssayForComparison(id="e1", text_content="Essay 1"),
        EssayForComparison(id="e2", text_content="Essay 2"),
        EssayForComparison(id="e3", text_content="Essay 3"),
        EssayForComparison(id="e4", text_content="Essay 4"),
    ]


def _make_true_scores_easy() -> dict[str, float]:
    """Return ground-truth scores for an easy-to-converge net."""

    return {
        "e1": -1.0,
        "e2": -0.3,
        "e3": 0.3,
        "e4": 1.0,
    }


def test_convergence_harness_stops_on_stability_before_max_iterations() -> None:
    """Convergence harness should stop once stability is achieved."""

    essays = _make_synthetic_essays()
    true_scores = _make_true_scores_easy()

    config = ConvergenceHarnessConfig(
        comparisons_per_iteration=6,  # full nC2 for 4 essays
        min_comparisons_for_stability_check=6,
        max_iterations=5,
        max_pairwise_comparisons=30,
        stability_threshold=10.0,  # permissive threshold ensures stability once deltas are bounded
    )

    result = run_convergence_harness(
        essays=essays,
        true_scores=true_scores,
        config=config,
        random_seed=123,
    )

    # All essays receive BT scores.
    assert set(result.final_scores.keys()) == {essay.id for essay in essays}

    # Stability is achieved before hitting iteration or budget caps.
    assert result.stability_achieved is True
    assert result.cap_reason is ConvergenceCapReason.STABILITY
    assert result.iterations_run < config.max_iterations
    assert result.total_comparisons <= config.max_pairwise_comparisons

    # Diagnostics are populated for debugging.
    assert result.max_score_change is not None
    assert result.se_summary is not None


def test_convergence_harness_stops_after_max_iterations_or_budget() -> None:
    """Convergence harness must respect iteration caps when stability is not evaluated."""

    essays = _make_synthetic_essays()
    true_scores = _make_true_scores_easy()

    config = ConvergenceHarnessConfig(
        comparisons_per_iteration=3,
        # Make stability check unreachable so only caps can stop the harness.
        min_comparisons_for_stability_check=1000,
        max_iterations=3,
        max_pairwise_comparisons=100,
        stability_threshold=0.05,
    )

    result = run_convergence_harness(
        essays=essays,
        true_scores=true_scores,
        config=config,
        random_seed=456,
    )

    # All essays still receive BT scores.
    assert set(result.final_scores.keys()) == {essay.id for essay in essays}

    # Stability is not achieved; iteration cap should fire.
    assert result.stability_achieved is False
    assert result.cap_reason is ConvergenceCapReason.ITERATIONS
    assert result.iterations_run == config.max_iterations

    # Global budget is respected.
    assert result.total_comparisons <= config.max_pairwise_comparisons
