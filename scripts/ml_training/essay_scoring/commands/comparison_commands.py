"""CV comparison command registrations for Gate G1 decision checks.

Purpose:
    Register run-comparison commands that evaluate candidate CV runs against a
    baseline using paired fold deltas, bootstrap confidence intervals, and
    explicit gate thresholds.

Relationships:
    - Registered by `scripts.ml_training.essay_scoring.cli`.
    - Delegates comparison logic to `scripts.ml_training.essay_scoring.cv_comparison`.
"""

from __future__ import annotations

from pathlib import Path

import typer

from scripts.ml_training.essay_scoring.cv_comparison import (
    ComparisonGateProfile,
    compare_cv_runs,
)
from scripts.ml_training.essay_scoring.logging_utils import configure_console_logging


def register(app: typer.Typer) -> None:
    """Register comparison commands on the provided app."""

    @app.command("compare-cv-runs")
    def compare_cv_runs_command(
        reference_run_dir: Path = typer.Option(
            ...,
            help="Reference CV run directory (contains artifacts/cv_metrics.json).",
            exists=True,
            dir_okay=True,
            file_okay=False,
        ),
        candidate_run_dir: Path = typer.Option(
            ...,
            help="Candidate CV run directory to compare against the reference.",
            exists=True,
            dir_okay=True,
            file_okay=False,
        ),
        gate_profile: ComparisonGateProfile = typer.Option(
            ComparisonGateProfile.PROMPT_HOLDOUT_PRIMARY,
            help=(
                "Gate profile to evaluate: prompt_holdout_primary, stratified_stability, or none."
            ),
        ),
        min_prompt_n: int = typer.Option(
            30,
            help="Minimum prompt sample size for prompt-level diagnostics.",
            min=1,
        ),
        bottom_k_prompts: int = typer.Option(
            5,
            help="Number of bottom prompts to include in the comparison report.",
            min=1,
        ),
        bootstrap_iterations: int = typer.Option(
            5000,
            help="Bootstrap resamples for fold-paired mean-delta confidence intervals.",
            min=100,
        ),
        bootstrap_seed: int = typer.Option(
            42,
            help="Seed for bootstrap resampling.",
        ),
        worst_prompt_min_delta: float = typer.Option(
            0.010,
            help="Required minimum worst-prompt QWK delta for prompt-holdout gate.",
        ),
        mean_qwk_max_regression: float = typer.Option(
            0.003,
            help="Maximum allowed mean-QWK regression for prompt-holdout gate.",
            min=0.0,
        ),
        tail_adjacent_max_regression: float = typer.Option(
            0.010,
            help=(
                "Maximum allowed low/high tail adjacent-accuracy regression for "
                "prompt-holdout gate."
            ),
            min=0.0,
        ),
        stability_mean_qwk_max_regression: float = typer.Option(
            0.005,
            help="Maximum allowed mean-QWK regression for stratified-stability gate.",
            min=0.0,
        ),
        run_name: str | None = typer.Option(
            None,
            help="Optional run name suffix for the comparison output directory.",
        ),
    ) -> None:
        """Compare two CV runs and evaluate gate thresholds."""

        configure_console_logging()
        summary = compare_cv_runs(
            reference_run_dir=reference_run_dir,
            candidate_run_dir=candidate_run_dir,
            gate_profile=gate_profile,
            min_prompt_n=min_prompt_n,
            bottom_k_prompts=bottom_k_prompts,
            bootstrap_iterations=bootstrap_iterations,
            bootstrap_seed=bootstrap_seed,
            worst_prompt_min_delta=worst_prompt_min_delta,
            mean_qwk_max_regression=mean_qwk_max_regression,
            tail_adjacent_max_regression=tail_adjacent_max_regression,
            stability_mean_qwk_max_regression=stability_mean_qwk_max_regression,
            run_name=run_name,
        )
        typer.echo(f"Comparison complete: {summary.run_dir}")
        typer.echo(f"Artifact: {summary.artifact_path}")
        typer.echo(f"Report: {summary.report_path}")
        typer.echo(f"Gate passed: {summary.gate_passed}")
