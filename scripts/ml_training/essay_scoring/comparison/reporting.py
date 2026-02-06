"""Render comparison outputs for human review and automation.

Builds:
- `cv_comparison.json` with deltas, CIs, thresholds, and pass/fail checks,
- `cv_comparison.md` with a compact decision-ready summary.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from scripts.ml_training.essay_scoring.comparison.models import (
    ComparisonGateProfile,
    GateCheck,
    PairwiseDeltaSummary,
    RunMetrics,
)
from scripts.ml_training.essay_scoring.optuna_sweep import PromptSliceMetrics

_SCHEMA_VERSION = 1


def build_artifact_payload(
    *,
    gate_profile: ComparisonGateProfile,
    reference: RunMetrics,
    candidate: RunMetrics,
    deltas: dict[str, float],
    qwk_delta_summary: PairwiseDeltaSummary,
    adjacent_delta_summary: PairwiseDeltaSummary,
    mae_delta_summary: PairwiseDeltaSummary,
    checks: list[GateCheck],
    gate_passed: bool,
    worst_prompt_min_delta: float,
    mean_qwk_max_regression: float,
    tail_adjacent_max_regression: float,
    stability_mean_qwk_max_regression: float,
) -> dict[str, object]:
    """Build a machine-readable comparison artifact payload."""

    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate_profile": gate_profile.value,
        "reference": _serialize_run_metrics(reference),
        "candidate": _serialize_run_metrics(candidate),
        "deltas": {
            **deltas,
            "fold_paired": {
                "val_qwk": asdict(qwk_delta_summary),
                "val_adjacent_accuracy": asdict(adjacent_delta_summary),
                "val_mae": asdict(mae_delta_summary),
            },
        },
        "thresholds": {
            "worst_prompt_min_delta": worst_prompt_min_delta,
            "mean_qwk_max_regression": mean_qwk_max_regression,
            "tail_adjacent_max_regression": tail_adjacent_max_regression,
            "stability_mean_qwk_max_regression": stability_mean_qwk_max_regression,
        },
        "gate": {
            "passed": gate_passed,
            "checks": [asdict(check) for check in checks],
        },
    }


def build_report_markdown(
    *,
    gate_profile: ComparisonGateProfile,
    reference: RunMetrics,
    candidate: RunMetrics,
    deltas: dict[str, float],
    qwk_delta_summary: PairwiseDeltaSummary,
    adjacent_delta_summary: PairwiseDeltaSummary,
    mae_delta_summary: PairwiseDeltaSummary,
    checks: list[GateCheck],
    gate_passed: bool,
    min_prompt_n: int,
    bottom_k_prompts: int,
) -> str:
    """Build a markdown comparison report."""

    lines = [
        "# CV Comparison Report",
        "",
        "## Scope",
        "",
        f"- gate_profile: `{gate_profile.value}`",
        f"- min_prompt_n: `{min_prompt_n}`",
        f"- bottom_k_prompts: `{bottom_k_prompts}`",
        "",
        "## Runs",
        "",
        f"- reference: `{reference.run_dir}`",
        f"- candidate: `{candidate.run_dir}`",
        f"- scheme: `{reference.scheme}`",
        "",
        "## Primary Deltas (candidate - reference)",
        "",
        f"- mean_qwk: `{deltas['mean_qwk']:+.5f}`",
        f"- worst_prompt_qwk: `{deltas['worst_prompt_qwk']:+.5f}`",
        f"- low_tail_adjacent_accuracy: `{deltas['low_tail_adjacent_accuracy']:+.5f}`",
        f"- high_tail_adjacent_accuracy: `{deltas['high_tail_adjacent_accuracy']:+.5f}`",
        "",
        "## Fold-Paired Delta + Bootstrap CI",
        "",
        "| Metric | n_folds | mean_delta | std_delta | bootstrap_95pct_ci |",
        "|---|---:|---:|---:|---:|",
        (
            "| val_qwk | "
            f"{qwk_delta_summary.n_folds} | "
            f"{qwk_delta_summary.mean_delta:+.5f} | "
            f"{qwk_delta_summary.std_delta:.5f} | "
            f"[{qwk_delta_summary.bootstrap_ci_low:+.5f}, "
            f"{qwk_delta_summary.bootstrap_ci_high:+.5f}] |"
        ),
        (
            "| val_adjacent_accuracy | "
            f"{adjacent_delta_summary.n_folds} | "
            f"{adjacent_delta_summary.mean_delta:+.5f} | "
            f"{adjacent_delta_summary.std_delta:.5f} | "
            f"[{adjacent_delta_summary.bootstrap_ci_low:+.5f}, "
            f"{adjacent_delta_summary.bootstrap_ci_high:+.5f}] |"
        ),
        (
            "| val_mae | "
            f"{mae_delta_summary.n_folds} | "
            f"{mae_delta_summary.mean_delta:+.5f} | "
            f"{mae_delta_summary.std_delta:.5f} | "
            f"[{mae_delta_summary.bootstrap_ci_low:+.5f}, "
            f"{mae_delta_summary.bootstrap_ci_high:+.5f}] |"
        ),
        "",
        "## Gate Checks",
        "",
    ]
    if not checks:
        lines.extend(
            [
                "- gate profile `none` selected (no threshold checks applied).",
                f"- gate_passed: `{gate_passed}`",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- gate_passed: `{gate_passed}`",
                "",
                "| Check | Observed | Threshold | Pass |",
                "|---|---:|---|---:|",
            ]
        )
        for check in checks:
            lines.append(
                "| "
                + " | ".join(
                    [
                        check.name,
                        f"{check.observed:+.5f}",
                        check.threshold,
                        "yes" if check.passed else "no",
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "## Bottom Prompt Slices",
            "",
            "### Reference",
            "",
            "```text",
            _format_prompt_rows(reference.bottom_prompts),
            "```",
            "",
            "### Candidate",
            "",
            "```text",
            _format_prompt_rows(candidate.bottom_prompts),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _serialize_run_metrics(run_metrics: RunMetrics) -> dict[str, object]:
    return {
        "run_dir": str(run_metrics.run_dir),
        "scheme": run_metrics.scheme,
        "model_family": run_metrics.model_family,
        "mean_qwk": run_metrics.mean_qwk,
        "worst_prompt_qwk": run_metrics.worst_prompt_qwk,
        "low_tail": asdict(run_metrics.low_tail),
        "high_tail": asdict(run_metrics.high_tail),
        "mid_band_adjacent_accuracy": run_metrics.mid_band_adjacent_accuracy,
        "fold_val_qwk": run_metrics.fold_val_qwk,
        "fold_val_adjacent_accuracy": run_metrics.fold_val_adjacent_accuracy,
        "fold_val_mae": run_metrics.fold_val_mae,
        "bottom_prompts": [asdict(metric) for metric in run_metrics.bottom_prompts],
    }


def _format_prompt_rows(metrics: list[PromptSliceMetrics]) -> str:
    if not metrics:
        return "No prompts met min_prompt_n."
    header = "prompt | n | qwk | mae | adjacent_accuracy"
    divider = "-" * len(header)
    rows = [header, divider]
    for metric in metrics:
        rows.append(
            f"{metric.prompt} | {metric.n} | {metric.qwk:.5f} | "
            f"{metric.mae:.5f} | {metric.adjacent_accuracy:.5f}"
        )
    return "\n".join(rows)


def write_outputs(
    *,
    run_dir: Path,
    artifact_payload: dict[str, object],
    report_markdown: str,
) -> tuple[Path, Path]:
    """Write JSON artifact and markdown report for one comparison run."""

    artifacts_dir = run_dir / "artifacts"
    reports_dir = run_dir / "reports"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = artifacts_dir / "cv_comparison.json"
    report_path = reports_dir / "cv_comparison.md"
    import json

    artifact_path.write_text(json.dumps(artifact_payload, indent=2), encoding="utf-8")
    report_path.write_text(report_markdown, encoding="utf-8")
    return artifact_path, report_path
