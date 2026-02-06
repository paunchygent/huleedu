"""Tests for CV run comparison and gate-threshold evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.ml_training.essay_scoring.cv_comparison import (
    ComparisonGateProfile,
    compare_cv_runs,
)


def test_compare_cv_runs_prompt_holdout_primary_gate_passes(tmp_path: Path) -> None:
    reference_run = _write_mock_cv_run(
        base_dir=tmp_path,
        run_name="reference_prompt",
        scheme="prompt_holdout",
        val_qwk_mean=0.6800,
        fold_rows=[
            (0, 0.6750, 0.8600, 0.4200),
            (1, 0.6850, 0.8700, 0.4100),
        ],
        residual_rows=[
            ("a1", "prompt_a", 1.0, 1.0),
            ("a2", "prompt_a", 2.0, 2.0),
            ("b1", "prompt_b", 1.0, 2.0),
            ("b2", "prompt_b", 2.0, 1.0),
            ("c1", "prompt_c", 4.0, 4.0),
            ("c2", "prompt_c", 4.5, 4.5),
        ],
    )
    candidate_run = _write_mock_cv_run(
        base_dir=tmp_path,
        run_name="candidate_prompt",
        scheme="prompt_holdout",
        val_qwk_mean=0.6810,
        fold_rows=[
            (0, 0.6800, 0.8610, 0.4100),
            (1, 0.6860, 0.8710, 0.4050),
        ],
        residual_rows=[
            ("a1", "prompt_a", 1.0, 1.0),
            ("a2", "prompt_a", 2.0, 2.0),
            ("b1", "prompt_b", 1.0, 1.0),
            ("b2", "prompt_b", 2.0, 2.0),
            ("c1", "prompt_c", 4.0, 4.0),
            ("c2", "prompt_c", 4.5, 4.5),
        ],
    )

    summary = compare_cv_runs(
        reference_run_dir=reference_run,
        candidate_run_dir=candidate_run,
        gate_profile=ComparisonGateProfile.PROMPT_HOLDOUT_PRIMARY,
        min_prompt_n=2,
        bottom_k_prompts=2,
        bootstrap_iterations=200,
        bootstrap_seed=123,
    )

    assert summary.gate_passed is True
    assert summary.artifact_path.exists()
    assert summary.report_path.exists()


def test_compare_cv_runs_stratified_stability_gate_fails_on_large_regression(
    tmp_path: Path,
) -> None:
    reference_run = _write_mock_cv_run(
        base_dir=tmp_path,
        run_name="reference_stratified",
        scheme="stratified_text",
        val_qwk_mean=0.6900,
        fold_rows=[
            (0, 0.6880, 0.8650, 0.4100),
            (1, 0.6920, 0.8700, 0.4000),
        ],
        residual_rows=[
            ("a1", "prompt_a", 1.0, 1.0),
            ("a2", "prompt_a", 2.0, 2.0),
            ("b1", "prompt_b", 4.0, 4.0),
            ("b2", "prompt_b", 5.0, 5.0),
        ],
    )
    candidate_run = _write_mock_cv_run(
        base_dir=tmp_path,
        run_name="candidate_stratified",
        scheme="stratified_text",
        val_qwk_mean=0.6750,
        fold_rows=[
            (0, 0.6720, 0.8550, 0.4300),
            (1, 0.6780, 0.8600, 0.4200),
        ],
        residual_rows=[
            ("a1", "prompt_a", 1.0, 1.0),
            ("a2", "prompt_a", 2.0, 2.0),
            ("b1", "prompt_b", 4.0, 4.5),
            ("b2", "prompt_b", 5.0, 4.0),
        ],
    )

    summary = compare_cv_runs(
        reference_run_dir=reference_run,
        candidate_run_dir=candidate_run,
        gate_profile=ComparisonGateProfile.STRATIFIED_STABILITY,
        min_prompt_n=2,
        bottom_k_prompts=2,
        bootstrap_iterations=200,
        bootstrap_seed=456,
    )

    assert summary.gate_passed is False
    payload = json.loads(summary.artifact_path.read_text(encoding="utf-8"))
    assert payload["gate"]["checks"][0]["name"] == "mean_qwk_delta"
    assert payload["gate"]["checks"][0]["passed"] is False


def test_compare_cv_runs_same_run_has_zero_qwk_fold_delta(tmp_path: Path) -> None:
    run_dir = _write_mock_cv_run(
        base_dir=tmp_path,
        run_name="same_run",
        scheme="prompt_holdout",
        val_qwk_mean=0.6800,
        fold_rows=[
            (0, 0.6780, 0.8600, 0.4100),
            (1, 0.6820, 0.8700, 0.4000),
        ],
        residual_rows=[
            ("a1", "prompt_a", 1.0, 1.0),
            ("a2", "prompt_a", 2.0, 2.0),
            ("b1", "prompt_b", 4.0, 4.0),
            ("b2", "prompt_b", 5.0, 5.0),
        ],
    )

    summary = compare_cv_runs(
        reference_run_dir=run_dir,
        candidate_run_dir=run_dir,
        gate_profile=ComparisonGateProfile.NONE,
        min_prompt_n=2,
        bottom_k_prompts=2,
        bootstrap_iterations=200,
        bootstrap_seed=789,
    )

    payload = json.loads(summary.artifact_path.read_text(encoding="utf-8"))
    assert payload["deltas"]["fold_paired"]["val_qwk"]["mean_delta"] == 0.0


def _write_mock_cv_run(
    *,
    base_dir: Path,
    run_name: str,
    scheme: str,
    val_qwk_mean: float,
    fold_rows: list[tuple[int, float, float, float]],
    residual_rows: list[tuple[str, str, float, float]],
) -> Path:
    run_dir = base_dir / run_name
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    fold_payload = [
        {
            "fold": fold_id,
            "val": {
                "qwk": fold_qwk,
                "adjacent_accuracy": fold_adjacent_accuracy,
                "mean_absolute_error": fold_mae,
            },
        }
        for fold_id, fold_qwk, fold_adjacent_accuracy, fold_mae in fold_rows
    ]
    metrics_payload = {
        "schema_version": 5,
        "scheme": scheme,
        "model_family": "xgboost",
        "summary": {"val_qwk_mean": val_qwk_mean},
        "folds": fold_payload,
    }
    (artifacts_dir / "cv_metrics.json").write_text(
        json.dumps(metrics_payload, indent=2),
        encoding="utf-8",
    )

    rows = [
        "split,fold,record_id,prompt,y_true,y_pred_raw,y_pred,residual,abs_residual,within_half_band"
    ]
    for index, (record_id, prompt, y_true, y_pred) in enumerate(residual_rows):
        residual = y_pred - y_true
        abs_residual = abs(residual)
        within_half_band = 1 if abs_residual <= 0.5 else 0
        rows.append(
            f"cv_val_oof,{index % 2},{record_id},{prompt},{y_true:.1f},{y_pred:.1f},"
            f"{y_pred:.1f},{residual:.1f},{abs_residual:.1f},{within_half_band}"
        )
    (artifacts_dir / "residuals_cv_val_oof.csv").write_text(
        "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return run_dir
