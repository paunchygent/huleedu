#!/usr/bin/env python3
"""Typer CLI wrapper for comparison pair redistribution and optimization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import typer

from scripts.bayesian_consensus_model.d_optimal_workflow import (
    DynamicSpec,
    OptimizationResult,
    load_dynamic_spec,
    load_previous_comparisons_from_csv,
    optimize_from_dynamic_spec,
    write_design,
)
from scripts.bayesian_consensus_model.redistribute_core import (
    assign_pairs,
    build_rater_list,
    compute_quota_distribution,
    read_pairs,
    select_comparisons,
    write_assignments,
)

app = typer.Typer(help="Redistribute CJ comparison pairs across available raters.")


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

        requested_total = len(names) * per_rater
        available_total = len(comparisons)

        if available_total == 0:
            raise ValueError(
                "No comparisons available in pairs CSV."
            )

        shortage = requested_total > available_total
        if shortage:
            quotas = compute_quota_distribution(names, per_rater, available_total)
            total_needed = sum(quotas.values())
            selected = select_comparisons(comparisons, total_needed)
            assignments = assign_pairs(selected, names, quotas)
        else:
            quotas = {name: per_rater for name in names}
            total_needed = requested_total
            selected = select_comparisons(comparisons, total_needed)
            assignments = assign_pairs(selected, names, per_rater)

        write_assignments(output_path, assignments)
    except (FileNotFoundError, ValueError) as error:
        typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

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
    typer.echo(f"Output written to {output_path}")


@app.command("optimize-pairs")
def optimize_pairs(
    students: List[str] = typer.Option(
        ...,
        "--student",
        "-s",
        help="Student essay ID to include in pairing (repeat for multiple students).",
    ),
    output_csv: Path = typer.Option(
        ...,
        "--output-csv",
        "-o",
        metavar="PATH",
        help="Destination for the optimized schedule CSV.",
    ),
    total_slots: int = typer.Option(
        ...,
        "--total-slots",
        "-t",
        min=1,
        help="Required comparison slot budget.",
    ),
    anchors: Optional[str] = typer.Option(
        None,
        "--anchors",
        "-a",
        help="Comma-separated anchor order override (defaults to standard ladder).",
    ),
    include_anchor_anchor: bool = typer.Option(
        True,
        "--include-anchor-anchor/--no-include-anchor-anchor",
        help="Include anchor-anchor comparisons in candidate universe (default: True).",
    ),
    previous_csv: Optional[Path] = typer.Option(
        None,
        "--previous-csv",
        "-p",
        metavar="PATH",
        help=(
            "Previous session CSV for multi-session workflows "
            "(provides historical comparison data)."
        ),
    ),
    locked_pairs: Optional[List[str]] = typer.Option(
        None,
        "--lock-pair",
        "-l",
        help=(
            "Hard constraint pairs that MUST be included "
            "(rare; distinct from previous comparisons)."
        ),
    ),
    max_repeat: int = typer.Option(
        3,
        "--max-repeat",
        "-r",
        min=1,
        help="Maximum allowed repeat count for any pair in the design (default: 3).",
    ),
    report_json: Optional[Path] = typer.Option(
        None,
        "--report-json",
        metavar="PATH",
        help="Optional JSON report path capturing diagnostics and dynamic spec.",
    ),
) -> None:
    """Optimize comparison schedules using dynamic input specification (no baseline CSV needed)."""
    try:
        # Parse student IDs (could be comma-separated in single option)
        student_list: List[str] = []
        for entry in students:
            student_list.extend(s.strip() for s in entry.split(",") if s.strip())

        if not student_list:
            raise ValueError("At least one student essay ID is required.")

        # Parse anchor order
        anchor_list: Optional[List[str]] = None
        if anchors:
            anchor_list = [a.strip() for a in anchors.split(",") if a.strip()]

        # Load previous comparisons if provided (for multi-session workflows)
        previous_comparisons = None
        if previous_csv:
            previous_comparisons = load_previous_comparisons_from_csv(previous_csv)
            typer.echo(
                f"Loaded {len(previous_comparisons)} previous comparisons "
                f"from {previous_csv}"
            )

        # Parse locked pairs
        locked_list: List[Tuple[str, str]] = []
        if locked_pairs:
            for pair_str in locked_pairs:
                parts = [p.strip() for p in pair_str.split(",")]
                if len(parts) != 2:
                    raise ValueError(
                        f"Locked pair must be in format 'essay_a,essay_b', got: {pair_str}"
                    )
                locked_list.append((parts[0], parts[1]))

        # Build dynamic spec
        spec = load_dynamic_spec(
            students=student_list,
            anchors=anchor_list,
            include_anchor_anchor=include_anchor_anchor,
            previous_comparisons=previous_comparisons,
            locked_pairs=locked_list if locked_list else None,
            total_slots=total_slots,
        )

        # Run optimizer
        result = optimize_from_dynamic_spec(spec, max_repeat=max_repeat)

        # Write output
        write_design(result.optimized_design, output_csv)
        typer.echo(f"Optimized schedule written to {output_csv}")

        # Emit summary
        _emit_optimizer_summary(result)

        # Write diagnostics if requested
        if report_json:
            _write_report(report_json, result, spec)
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
    typer.echo(
        "Minimum required slots: "
        f"{result.min_slots_required} "
        f"(anchor adjacency {result.anchor_adjacency_count}, "
        f"baseline-required {result.required_pair_count})"
    )

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


def _write_report(
    path: Path, result: OptimizationResult, spec: Optional[DynamicSpec] = None
) -> None:
    payload = {
        "students": list(result.students),
        "anchor_order": list(result.anchor_order),
        "baseline_log_det": result.baseline_log_det,
        "optimized_log_det": result.optimized_log_det,
        "log_det_gain": result.log_det_gain,
        "max_repeat": result.max_repeat,
        "anchor_adjacency_pairs": result.anchor_adjacency_count,
        "required_pairs": result.required_pair_count,
        "min_slots_required": result.min_slots_required,
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

    # Include dynamic spec if provided
    if spec is not None:
        payload["dynamic_spec"] = {
            "students": list(spec.students),
            "anchors": list(spec.anchors),
            "include_anchor_anchor": spec.include_anchor_anchor,
            "locked_pairs": [list(pair) for pair in spec.locked_pairs],
            "total_slots": spec.total_slots,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))


def main() -> None:
    """Entry point for standalone executable."""
    app()


if __name__ == "__main__":
    main()
