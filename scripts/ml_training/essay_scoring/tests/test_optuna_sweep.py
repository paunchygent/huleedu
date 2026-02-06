"""Tests for Optuna-based CV sweep helpers."""

from __future__ import annotations

from pathlib import Path

from scripts.ml_training.essay_scoring.optuna_sweep import (
    compute_prompt_slice_metrics,
    guardrail_violations,
    lexicographic_objective_score,
)


def test_lexicographic_objective_prioritizes_worst_prompt_qwk() -> None:
    score_better_worst = lexicographic_objective_score(worst_prompt_qwk=0.61, mean_qwk=0.10)
    score_worse_worst = lexicographic_objective_score(worst_prompt_qwk=0.60, mean_qwk=0.99)
    assert score_better_worst > score_worse_worst


def test_compute_prompt_slice_metrics_filters_and_sorts_by_worst_qwk(tmp_path: Path) -> None:
    residuals_path = tmp_path / "residuals_cv_val_oof.csv"
    residuals_path.write_text(
        "\n".join(
            [
                "split,fold,record_id,prompt,y_true,y_pred_raw,y_pred,residual,abs_residual,within_half_band",
                "cv_val_oof,0,id_a1,prompt_a,1.0,1.0,1.0,0.0,0.0,1",
                "cv_val_oof,0,id_a2,prompt_a,2.0,2.0,2.0,0.0,0.0,1",
                "cv_val_oof,0,id_b1,prompt_b,1.0,2.0,2.0,1.0,1.0,0",
                "cv_val_oof,0,id_b2,prompt_b,2.0,1.0,1.0,-1.0,1.0,0",
                "cv_val_oof,0,id_c1,prompt_c,1.0,1.0,1.0,0.0,0.0,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    metrics = compute_prompt_slice_metrics(residuals_path=residuals_path, min_prompt_n=2)
    prompts = [metric.prompt for metric in metrics]
    assert prompts == ["prompt_b", "prompt_a"]
    assert metrics[0].qwk < metrics[1].qwk


def test_guardrail_violations_detects_tail_regression_with_tolerance() -> None:
    violations = guardrail_violations(
        baseline_low_tail_adjacent_accuracy=0.82,
        baseline_high_tail_adjacent_accuracy=0.90,
        trial_low_tail_adjacent_accuracy=0.79,
        trial_high_tail_adjacent_accuracy=0.89,
        tolerance=0.02,
    )

    assert len(violations) == 1
    assert "low_tail_adjacent_accuracy regression" in violations[0]
