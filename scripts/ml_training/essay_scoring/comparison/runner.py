"""Orchestrate end-to-end CV comparison and gate decisions.

This runner takes a reference and candidate run directory, computes paired
deltas and bootstrap CIs, evaluates gate thresholds, and writes comparison
artifacts/reports to a new run directory under `output/essay_scoring/`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.ml_training.essay_scoring.comparison.gates import (
    evaluate_gate_checks,
    validate_gate_scheme_compatibility,
)
from scripts.ml_training.essay_scoring.comparison.loader import load_run_metrics
from scripts.ml_training.essay_scoring.comparison.models import (
    ComparisonGateProfile,
    CvRunComparisonSummary,
)
from scripts.ml_training.essay_scoring.comparison.reporting import (
    build_artifact_payload,
    build_report_markdown,
    write_outputs,
)
from scripts.ml_training.essay_scoring.comparison.statistics import (
    pairwise_metric_delta,
    summarize_deltas,
)
from scripts.ml_training.essay_scoring.config import OutputConfig


def compare_cv_runs(
    *,
    reference_run_dir: Path,
    candidate_run_dir: Path,
    gate_profile: ComparisonGateProfile,
    min_prompt_n: int = 30,
    bottom_k_prompts: int = 5,
    bootstrap_iterations: int = 5000,
    bootstrap_seed: int = 42,
    worst_prompt_min_delta: float = 0.010,
    mean_qwk_max_regression: float = 0.003,
    tail_adjacent_max_regression: float = 0.010,
    stability_mean_qwk_max_regression: float = 0.005,
    run_name: str | None = None,
) -> CvRunComparisonSummary:
    """Compare two completed CV runs and evaluate gate thresholds."""

    if min_prompt_n <= 0:
        raise ValueError("min_prompt_n must be > 0.")
    if bottom_k_prompts <= 0:
        raise ValueError("bottom_k_prompts must be > 0.")
    if bootstrap_iterations <= 0:
        raise ValueError("bootstrap_iterations must be > 0.")

    reference = load_run_metrics(
        run_dir=reference_run_dir,
        min_prompt_n=min_prompt_n,
        bottom_k_prompts=bottom_k_prompts,
    )
    candidate = load_run_metrics(
        run_dir=candidate_run_dir,
        min_prompt_n=min_prompt_n,
        bottom_k_prompts=bottom_k_prompts,
    )
    validate_gate_scheme_compatibility(
        gate_profile=gate_profile,
        reference_scheme=reference.scheme,
        candidate_scheme=candidate.scheme,
    )

    val_qwk_deltas = pairwise_metric_delta(reference.fold_val_qwk, candidate.fold_val_qwk)
    val_adjacent_deltas = pairwise_metric_delta(
        reference.fold_val_adjacent_accuracy,
        candidate.fold_val_adjacent_accuracy,
    )
    val_mae_deltas = pairwise_metric_delta(reference.fold_val_mae, candidate.fold_val_mae)

    qwk_delta_summary = summarize_deltas(
        deltas=val_qwk_deltas,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed,
    )
    adjacent_delta_summary = summarize_deltas(
        deltas=val_adjacent_deltas,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed + 1,
    )
    mae_delta_summary = summarize_deltas(
        deltas=val_mae_deltas,
        bootstrap_iterations=bootstrap_iterations,
        bootstrap_seed=bootstrap_seed + 2,
    )

    deltas = {
        "mean_qwk": float(candidate.mean_qwk - reference.mean_qwk),
        "worst_prompt_qwk": float(candidate.worst_prompt_qwk - reference.worst_prompt_qwk),
        "low_tail_adjacent_accuracy": float(
            candidate.low_tail.adjacent_accuracy - reference.low_tail.adjacent_accuracy
        ),
        "high_tail_adjacent_accuracy": float(
            candidate.high_tail.adjacent_accuracy - reference.high_tail.adjacent_accuracy
        ),
    }

    checks = evaluate_gate_checks(
        gate_profile=gate_profile,
        deltas=deltas,
        worst_prompt_min_delta=worst_prompt_min_delta,
        mean_qwk_max_regression=mean_qwk_max_regression,
        tail_adjacent_max_regression=tail_adjacent_max_regression,
        stability_mean_qwk_max_regression=stability_mean_qwk_max_regression,
    )
    gate_passed = all(check.passed for check in checks) if checks else True

    comparison_run_name = run_name or (
        "cv_compare_"
        f"{gate_profile.value}_"
        f"{_path_id(reference_run_dir)}_vs_{_path_id(candidate_run_dir)}"
    )
    resolved_run_dir = OutputConfig(
        base_dir=Path("output/essay_scoring"),
        run_name=comparison_run_name,
    ).resolve_run_dir()

    artifact_payload = build_artifact_payload(
        gate_profile=gate_profile,
        reference=reference,
        candidate=candidate,
        deltas=deltas,
        qwk_delta_summary=qwk_delta_summary,
        adjacent_delta_summary=adjacent_delta_summary,
        mae_delta_summary=mae_delta_summary,
        checks=checks,
        gate_passed=gate_passed,
        worst_prompt_min_delta=worst_prompt_min_delta,
        mean_qwk_max_regression=mean_qwk_max_regression,
        tail_adjacent_max_regression=tail_adjacent_max_regression,
        stability_mean_qwk_max_regression=stability_mean_qwk_max_regression,
    )
    report_markdown = build_report_markdown(
        gate_profile=gate_profile,
        reference=reference,
        candidate=candidate,
        deltas=deltas,
        qwk_delta_summary=qwk_delta_summary,
        adjacent_delta_summary=adjacent_delta_summary,
        mae_delta_summary=mae_delta_summary,
        checks=checks,
        gate_passed=gate_passed,
        min_prompt_n=min_prompt_n,
        bottom_k_prompts=bottom_k_prompts,
    )
    artifact_path, report_path = write_outputs(
        run_dir=resolved_run_dir,
        artifact_payload=artifact_payload,
        report_markdown=report_markdown,
    )

    return CvRunComparisonSummary(
        run_dir=resolved_run_dir,
        report_path=report_path,
        artifact_path=artifact_path,
        gate_passed=gate_passed,
    )


def _path_id(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()
    return digest[:8]
