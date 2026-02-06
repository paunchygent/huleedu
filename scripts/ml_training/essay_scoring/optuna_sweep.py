"""Optuna-based CV sweep utilities for essay-scoring (CV-first).

Purpose:
    Provide a reusable Optuna sweep runner that optimizes XGBoost training
    parameters against prompt-holdout CV while preserving existing quality
    guardrails (tail-slice stability + prompt-slice diagnostics).

Relationships:
    - Invoked by `scripts.ml_training.essay_scoring.cli` via `optuna-sweep`.
    - Reuses `run_cross_validation` for each trial (single source of CV truth).
    - Reuses `compute_tail_slice_metrics` from `hyperparameter_sweep`.
    - Writes machine-readable progress via `ProgressWriter`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from scripts.ml_training.essay_scoring.config import ExperimentConfig, OutputConfig
from scripts.ml_training.essay_scoring.cross_validation import run_cross_validation
from scripts.ml_training.essay_scoring.cv_shared import SplitScheme
from scripts.ml_training.essay_scoring.hyperparameter_sweep import (
    SliceMetrics,
    compute_tail_slice_metrics,
    stable_config_id,
)
from scripts.ml_training.essay_scoring.logging_utils import ProgressWriter, update_status
from scripts.ml_training.essay_scoring.training.evaluation import evaluate_predictions
from scripts.ml_training.essay_scoring.training.grade_band_weighting import GradeBandWeighting
from scripts.ml_training.essay_scoring.training.prediction_mapping import PredictionMapping
from scripts.ml_training.essay_scoring.training.training_modes import TrainingMode

OPTUNA_OBJECTIVE_WORST_PROMPT_THEN_MEAN = "worst_prompt_qwk_then_mean_qwk"
DEFAULT_TAIL_ADJACENT_TOLERANCE = 0.02
_LEXICOGRAPHIC_PRIMARY_SCALE = 1000.0
_DEFAULT_OPTUNA_SEARCH_SPACE: dict[str, list[int | float]] = {
    "max_depth": [3, 4, 5],
    "min_child_weight": [5, 10, 20],
    "reg_lambda": [2.0, 5.0, 10.0],
    "reg_alpha": [0.0, 1.0],
}


class OptunaSweepConfigError(ValueError):
    """Raised when an Optuna sweep configuration is invalid."""


@dataclass(frozen=True)
class PromptSliceMetrics:
    """Per-prompt diagnostics computed from CV residual rows."""

    prompt: str
    n: int
    qwk: float
    mae: float
    adjacent_accuracy: float


@dataclass(frozen=True)
class BaselineMetrics:
    """Baseline metrics used for trial guardrail checks."""

    mean_qwk: float
    worst_prompt_qwk: float
    low_tail: SliceMetrics
    high_tail: SliceMetrics
    bottom_prompts: list[PromptSliceMetrics]


@dataclass(frozen=True)
class OptunaTrialResult:
    """Materialized result for one Optuna trial."""

    trial_number: int
    config_id: str
    training_params: dict[str, Any]
    run_dir: str
    objective_score_raw: float
    objective_score_penalized: float
    mean_qwk: float
    worst_prompt_qwk: float
    low_tail: SliceMetrics
    high_tail: SliceMetrics
    mid_band_adjacent_accuracy: float
    rejected_by_guardrail: bool
    guardrail_violations: list[str]
    bottom_prompts: list[PromptSliceMetrics]


def compute_prompt_slice_metrics(
    *,
    residuals_path: Path,
    min_prompt_n: int,
) -> list[PromptSliceMetrics]:
    """Compute prompt-level QWK/MAE/adjacent diagnostics from residual rows."""

    frame = pd.read_csv(residuals_path)
    required_columns = {"prompt", "y_true", "y_pred"}
    missing = required_columns - set(frame.columns)
    if missing:
        missing_sorted = ", ".join(sorted(missing))
        raise OptunaSweepConfigError(
            f"Residual file missing required columns: {missing_sorted} ({residuals_path})"
        )

    min_band = float(frame["y_true"].min())
    max_band = float(frame["y_true"].max())
    metrics: list[PromptSliceMetrics] = []

    for prompt_value, group in frame.groupby("prompt", dropna=False):
        n_rows = int(group.shape[0])
        if n_rows < min_prompt_n:
            continue

        evaluation = evaluate_predictions(
            y_true=group["y_true"].to_numpy(dtype=float),
            y_pred=group["y_pred"].to_numpy(dtype=float),
            min_band=min_band,
            max_band=max_band,
        )
        prompt_label = str(prompt_value) if pd.notna(prompt_value) else "unknown_prompt"
        metrics.append(
            PromptSliceMetrics(
                prompt=prompt_label,
                n=n_rows,
                qwk=_sanitize_metric(evaluation.qwk),
                mae=_sanitize_metric(evaluation.mean_absolute_error),
                adjacent_accuracy=_sanitize_metric(evaluation.adjacent_accuracy),
            )
        )

    metrics.sort(key=lambda item: (item.qwk, -item.mae, item.adjacent_accuracy, -item.n))
    return metrics


def lexicographic_objective_score(*, worst_prompt_qwk: float, mean_qwk: float) -> float:
    """Map lexicographic optimization to a single scalar score.

    The primary signal (`worst_prompt_qwk`) dominates the secondary signal
    (`mean_qwk`) via a large scale factor, so improvement on worst-prompt
    performance always outranks mean-QWK-only gains.
    """

    return (worst_prompt_qwk * _LEXICOGRAPHIC_PRIMARY_SCALE) + mean_qwk


def guardrail_violations(
    *,
    baseline_low_tail_adjacent_accuracy: float,
    baseline_high_tail_adjacent_accuracy: float,
    trial_low_tail_adjacent_accuracy: float,
    trial_high_tail_adjacent_accuracy: float,
    tolerance: float,
) -> list[str]:
    """Return guardrail violations relative to baseline tail-slice adjacencies."""

    violations: list[str] = []
    if trial_low_tail_adjacent_accuracy + tolerance < baseline_low_tail_adjacent_accuracy:
        violations.append(
            "low_tail_adjacent_accuracy regression "
            f"({trial_low_tail_adjacent_accuracy:.5f} < "
            f"{baseline_low_tail_adjacent_accuracy:.5f} - tol {tolerance:.5f})"
        )
    if trial_high_tail_adjacent_accuracy + tolerance < baseline_high_tail_adjacent_accuracy:
        violations.append(
            "high_tail_adjacent_accuracy regression "
            f"({trial_high_tail_adjacent_accuracy:.5f} < "
            f"{baseline_high_tail_adjacent_accuracy:.5f} - tol {tolerance:.5f})"
        )
    return violations


def run_optuna_sweep(
    *,
    base_config: ExperimentConfig,
    splits_path: Path,
    scheme: SplitScheme,
    reuse_cv_feature_store_dir: Path,
    sweep_run_name: str,
    feature_set: Any,
    n_trials: int,
    objective: str,
    min_prompt_n: int,
    bottom_k_prompts: int,
    baseline_best_run_dir: Path,
    handcrafted_keep: list[str] | None,
    handcrafted_drop: list[str] | None,
    training_mode: TrainingMode,
    grade_band_weighting: GradeBandWeighting,
    grade_band_weight_cap: float,
    prediction_mapping: PredictionMapping,
    tail_adjacent_tolerance: float = DEFAULT_TAIL_ADJACENT_TOLERANCE,
) -> Path:
    """Run an Optuna CV sweep and persist trial + selection artifacts."""

    _validate_objective(objective)
    if n_trials <= 0:
        raise OptunaSweepConfigError("n_trials must be > 0")
    if min_prompt_n <= 0:
        raise OptunaSweepConfigError("min_prompt_n must be > 0")
    if bottom_k_prompts <= 0:
        raise OptunaSweepConfigError("bottom_k_prompts must be > 0")

    optuna = _require_optuna()
    sweep_dir = OutputConfig(
        base_dir=base_config.output.base_dir,
        run_name=sweep_run_name,
    ).resolve_run_dir()
    sweep_artifacts_dir = sweep_dir / "artifacts"
    sweep_reports_dir = sweep_dir / "reports"
    sweep_variants_base_dir = sweep_dir / "variants"
    sweep_artifacts_dir.mkdir(parents=True, exist_ok=True)
    sweep_reports_dir.mkdir(parents=True, exist_ok=True)
    sweep_variants_base_dir.mkdir(parents=True, exist_ok=True)

    baseline = _load_baseline_metrics(
        baseline_best_run_dir=baseline_best_run_dir,
        min_prompt_n=min_prompt_n,
        bottom_k_prompts=bottom_k_prompts,
    )

    update_status(
        sweep_dir,
        stage="optuna_sweep",
        state="running",
        scheme=str(scheme),
        n_trials=n_trials,
        objective=objective,
        min_prompt_n=min_prompt_n,
        bottom_k_prompts=bottom_k_prompts,
        baseline_best_run_dir=str(baseline_best_run_dir),
    )
    progress = ProgressWriter(sweep_dir)
    progress.update(
        substage="optuna_trials",
        processed=0,
        total=n_trials,
        unit="trials",
        force=True,
    )

    trial_results: list[OptunaTrialResult] = []

    def objective_fn(trial: Any) -> float:
        params = _suggest_training_params(trial)
        config_id = stable_config_id(params)
        run_name = f"{sweep_run_name}_{config_id}_trial{trial.number:03d}"

        updated_training = base_config.training.model_copy(
            update={"params": {**base_config.training.params, **params}}
        )
        updated_output = base_config.output.model_copy(
            update={"base_dir": sweep_variants_base_dir, "run_name": run_name}
        )
        variant_config = base_config.model_copy(
            update={"training": updated_training, "output": updated_output}
        )

        summary = run_cross_validation(
            variant_config,
            feature_set=feature_set,
            splits_path=splits_path,
            scheme=scheme,
            reuse_cv_feature_store_dir=reuse_cv_feature_store_dir,
            handcrafted_keep=handcrafted_keep,
            handcrafted_drop=handcrafted_drop,
            training_mode=training_mode,
            grade_band_weighting=grade_band_weighting,
            grade_band_weight_cap=grade_band_weight_cap,
            prediction_mapping=prediction_mapping,
        )
        metrics_payload = _read_cv_metrics_payload(summary.metrics_path)
        residuals_path = summary.run_paths.artifacts_dir / "residuals_cv_val_oof.csv"
        mean_qwk = _sanitize_metric(float(metrics_payload["summary"]["val_qwk_mean"]))
        prompt_metrics = compute_prompt_slice_metrics(
            residuals_path=residuals_path,
            min_prompt_n=min_prompt_n,
        )
        bottom_prompts = prompt_metrics[:bottom_k_prompts]
        worst_prompt_qwk = bottom_prompts[0].qwk if bottom_prompts else mean_qwk
        low_tail, high_tail, mid_adjacent_accuracy = compute_tail_slice_metrics(residuals_path)
        violations = guardrail_violations(
            baseline_low_tail_adjacent_accuracy=baseline.low_tail.adjacent_accuracy,
            baseline_high_tail_adjacent_accuracy=baseline.high_tail.adjacent_accuracy,
            trial_low_tail_adjacent_accuracy=low_tail.adjacent_accuracy,
            trial_high_tail_adjacent_accuracy=high_tail.adjacent_accuracy,
            tolerance=tail_adjacent_tolerance,
        )
        score_raw = lexicographic_objective_score(
            worst_prompt_qwk=worst_prompt_qwk,
            mean_qwk=mean_qwk,
        )
        is_rejected = bool(violations)
        score_penalized = score_raw - 10_000.0 if is_rejected else score_raw

        trial.set_user_attr("config_id", config_id)
        trial.set_user_attr("run_dir", str(summary.run_paths.run_dir))
        trial.set_user_attr("mean_qwk", mean_qwk)
        trial.set_user_attr("worst_prompt_qwk", worst_prompt_qwk)
        trial.set_user_attr("rejected_by_guardrail", is_rejected)
        trial.set_user_attr("guardrail_violations", violations)

        trial_result = OptunaTrialResult(
            trial_number=int(trial.number),
            config_id=config_id,
            training_params=params,
            run_dir=str(summary.run_paths.run_dir),
            objective_score_raw=float(score_raw),
            objective_score_penalized=float(score_penalized),
            mean_qwk=mean_qwk,
            worst_prompt_qwk=worst_prompt_qwk,
            low_tail=low_tail,
            high_tail=high_tail,
            mid_band_adjacent_accuracy=float(mid_adjacent_accuracy),
            rejected_by_guardrail=is_rejected,
            guardrail_violations=violations,
            bottom_prompts=bottom_prompts,
        )
        trial_results.append(trial_result)
        _write_trials_artifact(
            output_path=sweep_artifacts_dir / "optuna_trials.json",
            sweep_run_name=sweep_run_name,
            objective=objective,
            baseline=baseline,
            trial_results=trial_results,
            min_prompt_n=min_prompt_n,
            bottom_k_prompts=bottom_k_prompts,
            tail_adjacent_tolerance=tail_adjacent_tolerance,
        )
        progress.update(
            substage="optuna_trials",
            processed=len(trial_results),
            total=n_trials,
            unit="trials",
            details={
                "current_trial": int(trial.number),
                "current_config_id": config_id,
                "current_worst_prompt_qwk": worst_prompt_qwk,
                "current_mean_qwk": mean_qwk,
                "rejected_by_guardrail": is_rejected,
            },
            force=True,
        )
        return score_penalized

    try:
        study = optuna.create_study(
            study_name=sweep_run_name,
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=base_config.training.random_seed),
        )
        study.optimize(
            objective_fn,
            n_trials=n_trials,
            gc_after_trial=True,
            show_progress_bar=False,
        )
        selected_trial = _select_trial(trial_results)
        _write_selected_params_artifact(
            output_path=sweep_artifacts_dir / "selected_params.json",
            selected_trial=selected_trial,
            objective=objective,
            baseline=baseline,
            min_prompt_n=min_prompt_n,
            bottom_k_prompts=bottom_k_prompts,
            baseline_best_run_dir=baseline_best_run_dir,
        )
        _write_optuna_summary(
            output_path=sweep_reports_dir / "optuna_summary.md",
            sweep_run_name=sweep_run_name,
            objective=objective,
            baseline=baseline,
            selected_trial=selected_trial,
            trial_results=trial_results,
            min_prompt_n=min_prompt_n,
            bottom_k_prompts=bottom_k_prompts,
        )
        update_status(
            sweep_dir,
            stage="optuna_sweep",
            state="completed",
            selected_trial_number=selected_trial.trial_number,
            selected_config_id=selected_trial.config_id,
        )
    except Exception as exc:
        update_status(
            sweep_dir,
            stage="optuna_sweep",
            state="failed",
            error_type=type(exc).__name__,
            message=str(exc),
        )
        raise

    return sweep_dir


def _require_optuna() -> Any:
    try:
        import optuna
    except ImportError as exc:
        raise OptunaSweepConfigError(
            "optuna is required for optuna-sweep. Install it with `pdm install -G ml-research`."
        ) from exc
    return optuna


def _validate_objective(objective: str) -> None:
    if objective != OPTUNA_OBJECTIVE_WORST_PROMPT_THEN_MEAN:
        raise OptunaSweepConfigError(
            f"Unsupported objective. Supported values: `{OPTUNA_OBJECTIVE_WORST_PROMPT_THEN_MEAN}`"
        )


def _suggest_training_params(trial: Any) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, choices in _DEFAULT_OPTUNA_SEARCH_SPACE.items():
        params[key] = trial.suggest_categorical(key, choices)
    return params


def _load_baseline_metrics(
    *,
    baseline_best_run_dir: Path,
    min_prompt_n: int,
    bottom_k_prompts: int,
) -> BaselineMetrics:
    metrics_path = baseline_best_run_dir / "artifacts" / "cv_metrics.json"
    residuals_path = baseline_best_run_dir / "artifacts" / "residuals_cv_val_oof.csv"
    if not metrics_path.exists():
        raise OptunaSweepConfigError(f"Missing baseline metrics file: {metrics_path}")
    if not residuals_path.exists():
        raise OptunaSweepConfigError(f"Missing baseline residual rows file: {residuals_path}")

    payload = _read_cv_metrics_payload(metrics_path)
    mean_qwk = _sanitize_metric(float(payload["summary"]["val_qwk_mean"]))
    low_tail, high_tail, _ = compute_tail_slice_metrics(residuals_path)
    prompt_metrics = compute_prompt_slice_metrics(
        residuals_path=residuals_path,
        min_prompt_n=min_prompt_n,
    )
    bottom_prompts = prompt_metrics[:bottom_k_prompts]
    worst_prompt_qwk = bottom_prompts[0].qwk if bottom_prompts else mean_qwk

    return BaselineMetrics(
        mean_qwk=mean_qwk,
        worst_prompt_qwk=worst_prompt_qwk,
        low_tail=low_tail,
        high_tail=high_tail,
        bottom_prompts=bottom_prompts,
    )


def _read_cv_metrics_payload(metrics_path: Path) -> dict[str, Any]:
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    if "summary" not in payload:
        raise OptunaSweepConfigError(
            f"Invalid CV metrics payload (missing summary): {metrics_path}"
        )
    return payload


def _select_trial(trial_results: list[OptunaTrialResult]) -> OptunaTrialResult:
    if not trial_results:
        raise OptunaSweepConfigError("No completed trials were recorded.")
    accepted = [result for result in trial_results if not result.rejected_by_guardrail]
    candidates = accepted if accepted else trial_results
    return max(candidates, key=lambda result: (result.worst_prompt_qwk, result.mean_qwk))


def _write_trials_artifact(
    *,
    output_path: Path,
    sweep_run_name: str,
    objective: str,
    baseline: BaselineMetrics,
    trial_results: list[OptunaTrialResult],
    min_prompt_n: int,
    bottom_k_prompts: int,
    tail_adjacent_tolerance: float,
) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sweep_run_name": sweep_run_name,
        "objective": objective,
        "min_prompt_n": min_prompt_n,
        "bottom_k_prompts": bottom_k_prompts,
        "tail_adjacent_tolerance": tail_adjacent_tolerance,
        "baseline": asdict(baseline),
        "results": [asdict(result) for result in trial_results],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_selected_params_artifact(
    *,
    output_path: Path,
    selected_trial: OptunaTrialResult,
    objective: str,
    baseline: BaselineMetrics,
    min_prompt_n: int,
    bottom_k_prompts: int,
    baseline_best_run_dir: Path,
) -> None:
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": objective,
        "min_prompt_n": min_prompt_n,
        "bottom_k_prompts": bottom_k_prompts,
        "baseline_best_run_dir": str(baseline_best_run_dir),
        "baseline": asdict(baseline),
        "selected_trial": asdict(selected_trial),
        "selected_params": selected_trial.training_params,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_optuna_summary(
    *,
    output_path: Path,
    sweep_run_name: str,
    objective: str,
    baseline: BaselineMetrics,
    selected_trial: OptunaTrialResult,
    trial_results: list[OptunaTrialResult],
    min_prompt_n: int,
    bottom_k_prompts: int,
) -> None:
    sorted_results = sorted(
        trial_results,
        key=lambda item: (
            0 if not item.rejected_by_guardrail else 1,
            -item.worst_prompt_qwk,
            -item.mean_qwk,
        ),
    )
    lines = [
        f"# Optuna sweep: `{sweep_run_name}`",
        "",
        "## Objective",
        "",
        f"- objective: `{objective}`",
        f"- min_prompt_n: `{min_prompt_n}`",
        f"- bottom_k_prompts: `{bottom_k_prompts}`",
        "",
        "## Baseline guardrails",
        "",
        f"- mean_qwk: `{baseline.mean_qwk:.5f}`",
        f"- worst_prompt_qwk: `{baseline.worst_prompt_qwk:.5f}`",
        f"- low_tail_adjacent_accuracy: `{baseline.low_tail.adjacent_accuracy:.5f}`",
        f"- high_tail_adjacent_accuracy: `{baseline.high_tail.adjacent_accuracy:.5f}`",
        "",
        "## Selected trial",
        "",
        f"- trial_number: `{selected_trial.trial_number}`",
        f"- config_id: `{selected_trial.config_id}`",
        f"- worst_prompt_qwk: `{selected_trial.worst_prompt_qwk:.5f}`",
        f"- mean_qwk: `{selected_trial.mean_qwk:.5f}`",
        f"- rejected_by_guardrail: `{selected_trial.rejected_by_guardrail}`",
        f"- run_dir: `{selected_trial.run_dir}`",
        "",
        "## Trial ranking",
        "",
        "| Rank | Trial | Config | Rejected | Worst prompt QWK | Mean QWK | "
        "Low tail adj_acc | High tail adj_acc | Run dir |",
        "|---:|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for rank, result in enumerate(sorted_results, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    str(result.trial_number),
                    result.config_id,
                    "yes" if result.rejected_by_guardrail else "no",
                    f"{result.worst_prompt_qwk:.5f}",
                    f"{result.mean_qwk:.5f}",
                    f"{result.low_tail.adjacent_accuracy:.5f}",
                    f"{result.high_tail.adjacent_accuracy:.5f}",
                    f"`{result.run_dir}`",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Baseline bottom prompts",
            "",
            "```text",
            _format_prompt_metrics_table(baseline.bottom_prompts),
            "```",
            "",
            "## Selected trial bottom prompts",
            "",
            "```text",
            _format_prompt_metrics_table(selected_trial.bottom_prompts),
            "```",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _format_prompt_metrics_table(metrics: list[PromptSliceMetrics]) -> str:
    if not metrics:
        return "No prompts met min_prompt_n."
    frame = pd.DataFrame(
        [
            {
                "prompt": metric.prompt,
                "n": metric.n,
                "qwk": metric.qwk,
                "mae": metric.mae,
                "adjacent_accuracy": metric.adjacent_accuracy,
            }
            for metric in metrics
        ]
    )
    return frame.to_string(index=False)


def _sanitize_metric(value: float) -> float:
    if np.isnan(value):
        return 0.0
    return float(value)
