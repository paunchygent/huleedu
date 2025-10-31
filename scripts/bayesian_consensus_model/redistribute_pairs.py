#!/usr/bin/env python3
"""Typer CLI wrapper for comparison pair redistribution and optimization."""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if __package__ in (None, ""):
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

import typer

try:
    from .d_optimal_workflow import (  # type: ignore[attr-defined]
        DEFAULT_ANCHOR_ORDER,
        OptimizationResult,
        load_baseline_payload,
        optimize_from_payload,
        optimize_schedule,
        run_synthetic_optimization,
        write_design,
    )
    from .redistribute_core import (  # type: ignore[attr-defined]
        StatusSelector,
        assign_pairs,
        build_rater_list,
        compute_quota_distribution,
        filter_comparisons,
        read_pairs,
        select_comparisons,
        write_assignments,
    )
except ImportError:  # pragma: no cover - fallback for direct execution
    from scripts.bayesian_consensus_model.d_optimal_workflow import (  # type: ignore[attr-defined]
        DEFAULT_ANCHOR_ORDER,
        OptimizationResult,
        load_baseline_payload,
        optimize_from_payload,
        optimize_schedule,
        run_synthetic_optimization,
        write_design,
    )
    from scripts.bayesian_consensus_model.redistribute_core import (  # type: ignore[attr-defined]
        StatusSelector,
        assign_pairs,
        build_rater_list,
        compute_quota_distribution,
        filter_comparisons,
        read_pairs,
        select_comparisons,
        write_assignments,
    )

app = typer.Typer(help="Redistribute CJ comparison pairs across available raters.")


class OptimizerMode(str, Enum):
    SESSION = "session"
    SYNTHETIC = "synthetic"


def _resolve_raters(
    raters: Optional[int],
    rater_names: Optional[List[str]],
) -> List[str]:
    if rater_names:
        return build_rater_list(None, rater_names)

    if raters is None:
        raise ValueError("Provide --raters or specify --rater-name options.")
    return build_rater_list(raters, None)


@app.command()
def redistribute(
    pairs_csv: Optional[Path] = typer.Option(
        None,
        "--pairs-csv",
        metavar="PATH",
        help="Path to the comparison pairs CSV (e.g. session2_pairs.csv).",
    ),
    output_csv: Optional[Path] = typer.Option(
        None,
        "--output-csv",
        metavar="PATH",
        help="Destination CSV for the generated assignments.",
    ),
    raters: Optional[int] = typer.Option(
        None,
        "--raters",
        "-r",
        help="Number of available raters (mutually exclusive with --rater-name).",
    ),
    per_rater: int = typer.Option(
        10,
        "--per-rater",
        "-p",
        min=1,
        help="Comparisons to allocate per rater (default: 10).",
    ),
    rater_names: Optional[List[str]] = typer.Option(
        None,
        "--rater-name",
        "-n",
        help="Explicit rater names (repeat option per rater or supply comma-separated values).",
    ),
    include_status: StatusSelector = typer.Option(
        StatusSelector.ALL,
        "--include-status",
        case_sensitive=False,
        help="Select from 'core' (84 comparisons) or 'all' (core + extras).",
    ),
) -> None:
    """Redistribute comparison pairs and export a new rater assignment file."""
    try:
        pairs_path = pairs_csv or Path(typer.prompt("Path to pairs CSV"))
        output_path = output_csv or Path(typer.prompt("Path for output CSV"))

        comparisons = read_pairs(pairs_path)

        if rater_names:
            names = build_rater_list(None, rater_names)
        else:
            if raters is None:
                raters = typer.prompt("How many raters will attend?", type=int)
            names = build_rater_list(raters, None)

        pool = filter_comparisons(comparisons, include_status)
        requested_total = len(names) * per_rater
        available_total = len(pool)

        if available_total == 0:
            raise ValueError(
                "No comparisons available after filtering. "
                "Adjust status selection or regenerate pairs."
            )

        shortage = requested_total > available_total
        if shortage:
            quotas = compute_quota_distribution(names, per_rater, available_total)
            total_needed = sum(quotas.values())
            selected = select_comparisons(comparisons, include_status, total_needed)
            assignments = assign_pairs(selected, names, quotas)
        else:
            quotas = {name: per_rater for name in names}
            total_needed = requested_total
            selected = select_comparisons(comparisons, include_status, total_needed)
            assignments = assign_pairs(selected, names, per_rater)

        write_assignments(output_path, assignments)
    except (FileNotFoundError, ValueError) as error:
        typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    statuses = sorted({comparison.status for _, comparison in assignments})
    actual_counts: Sequence[int] = [quotas[name] for name in names]
    min_count = min(actual_counts)
    max_count = max(actual_counts)
    if shortage:
        typer.secho(
            f"Requested {requested_total} comparisons but only {available_total} available.",
            fg=typer.colors.YELLOW,
        )
    typer.secho(
        "Generated assignments for "
        f"{len(names)} raters (min {min_count}, max {max_count} comparisons).",
        fg=typer.colors.GREEN,
    )
    typer.secho(
        "Total allocated comparisons: "
        f"{sum(actual_counts)} (requested {requested_total}).",
        fg=typer.colors.GREEN,
    )
    typer.echo(f"Pairs drawn from statuses: {', '.join(statuses)}")
    typer.echo(f"Output written to {output_path}")


def _status_filter(include_status: StatusSelector) -> Optional[List[str]]:
    if include_status is StatusSelector.ALL:
        return None
    return [include_status.value]


@app.command("optimize-pairs")
def optimize_pairs(
    mode: OptimizerMode = typer.Option(
        OptimizerMode.SESSION,
        "--mode",
        case_sensitive=False,
        help="Run against an existing session CSV ('session') or the synthetic demo ('synthetic').",
    ),
    pairs_csv: Optional[Path] = typer.Option(
        None,
        "--pairs-csv",
        metavar="PATH",
        help="Path to the baseline comparison CSV (session mode).",
    ),
    output_csv: Optional[Path] = typer.Option(
        None,
        "--output-csv",
        metavar="PATH",
        help="Destination for the optimized schedule CSV (session mode).",
    ),
    total_slots: Optional[int] = typer.Option(
        None,
        "--total-slots",
        help="Override the comparison budget (defaults to baseline count or 36 synthetic).",
    ),
    max_repeat: int = typer.Option(
        3,
        "--max-repeat",
        min=1,
        help="Maximum allowed repeat count for a pair in the optimized design (default: 3).",
    ),
    include_status: StatusSelector = typer.Option(
        StatusSelector.CORE,
        "--include-status",
        case_sensitive=False,
        help="Which statuses to treat as the baseline pool when optimizing (session mode).",
    ),
    seed: int = typer.Option(
        17,
        "--seed",
        help="Random seed for the synthetic baseline generator (synthetic mode).",
    ),
    report_json: Optional[Path] = typer.Option(
        None,
        "--report-json",
        metavar="PATH",
        help="Optional JSON report path capturing diagnostics.",
    ),
    baseline_json: Optional[Path] = typer.Option(
        None,
        "--baseline-json",
        metavar="PATH",
        help=(
            "Optional JSON payload describing baseline comparisons (session mode only). "
            "Overrides --pairs-csv when supplied."
        ),
    ),
) -> None:
    """Optimize comparison schedules using the Fisher-information optimizer."""
    try:
        if mode is OptimizerMode.SYNTHETIC:
            if baseline_json is not None:
                raise ValueError("--baseline-json is not supported in synthetic mode.")
            slots = total_slots or 36
            result = run_synthetic_optimization(
                total_slots=slots,
                max_repeat=max_repeat,
                seed=seed,
            )
            if output_csv:
                write_design(result.optimized_design, output_csv)
                typer.echo(f"Optimized schedule written to {output_csv}")
        else:
            output_path = output_csv or Path(typer.prompt("Path for optimized schedule CSV"))
            status_filter = _status_filter(include_status)

            if baseline_json is not None:
                payload = load_baseline_payload(baseline_json)
                result = optimize_from_payload(
                    payload,
                    total_slots=total_slots,
                    max_repeat=max_repeat,
                    anchor_order=None,
                    status_filter=status_filter,
                )
            else:
                pairs_path = pairs_csv or Path(typer.prompt("Path to baseline pairs CSV"))
                result = optimize_schedule(
                    pairs_path,
                    total_slots=total_slots,
                    max_repeat=max_repeat,
                    anchor_order=DEFAULT_ANCHOR_ORDER,
                    status_filter=status_filter,
                )
            write_design(result.optimized_design, output_path)
            typer.echo(f"Optimized schedule written to {output_path}")

        _emit_optimizer_summary(result)

        if report_json:
            _write_report(report_json, result)
            typer.echo(f"Diagnostics written to {report_json}")
    except (FileNotFoundError, ValueError) as error:
        typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


def _emit_optimizer_summary(result: OptimizationResult) -> None:
    typer.secho("Optimization Summary", fg=typer.colors.CYAN, bold=True)
    typer.echo(
        f"Baseline log-det: {result.baseline_log_det:.4f}  |  "
        f"Optimized log-det: {result.optimized_log_det:.4f}  |  "
        f"Gain: {result.log_det_gain:.4f}"
    )
    typer.echo(f"Total comparisons: {result.total_comparisons}  (max repeat {result.max_repeat})")

    typer.echo("\nComparison type distribution (baseline):")
    for comp_type, count in result.baseline_diagnostics.type_counts.items():
        typer.echo(f"  {comp_type:<16} {count}")

    typer.echo("\nComparison type distribution (optimized):")
    for comp_type, count in result.optimized_diagnostics.type_counts.items():
        typer.echo(f"  {comp_type:<16} {count}")

    _print_student_anchor_coverage(result)
    _print_repeat_counts(result.optimized_diagnostics.repeat_counts)


def _print_student_anchor_coverage(result: OptimizationResult) -> None:
    coverage = result.optimized_diagnostics.student_anchor_coverage
    missing = sorted(set(result.students) - set(coverage))

    typer.echo("\nPer-student anchor coverage (optimized):")
    if not coverage:
        typer.echo("  No student-anchor comparisons in design.")
    else:
        for student in sorted(coverage):
            anchors = ", ".join(coverage[student]) or "—"
            typer.echo(f"  {student:<10} {anchors}")

    if missing:
        typer.secho(
            f"  Missing anchor coverage for: {', '.join(missing)}",
            fg=typer.colors.YELLOW,
        )


def _print_repeat_counts(repeat_counts: Dict[str, int]) -> None:
    typer.echo("\nRepeated pairs (>1 occurrence):")
    if not repeat_counts:
        typer.echo("  None")
        return
    for key, count in sorted(repeat_counts.items()):
        typer.echo(f"  {key}: {count}×")


def _write_report(path: Path, result: OptimizationResult) -> None:
    payload = {
        "students": list(result.students),
        "anchor_order": list(result.anchor_order),
        "baseline_log_det": result.baseline_log_det,
        "optimized_log_det": result.optimized_log_det,
        "log_det_gain": result.log_det_gain,
        "max_repeat": result.max_repeat,
        "baseline": {
            "total_pairs": result.baseline_diagnostics.total_pairs,
            "type_counts": result.baseline_diagnostics.type_counts,
            "student_anchor_coverage": result.baseline_diagnostics.student_anchor_coverage,
            "repeat_counts": result.baseline_diagnostics.repeat_counts,
        },
        "optimized": {
            "total_pairs": result.optimized_diagnostics.total_pairs,
            "type_counts": result.optimized_diagnostics.type_counts,
            "student_anchor_coverage": result.optimized_diagnostics.student_anchor_coverage,
            "repeat_counts": result.optimized_diagnostics.repeat_counts,
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    app()
