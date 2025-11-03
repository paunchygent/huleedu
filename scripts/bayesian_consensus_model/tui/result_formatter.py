"""Format optimization and assignment results for TUI display."""

from __future__ import annotations

from pathlib import Path

from scripts.bayesian_consensus_model.d_optimal_workflow import OptimizationResult


def format_optimization_summary(result: OptimizationResult, output_path: Path) -> list[str]:
    """Format optimization result into display messages.

    Args:
        result: Optimization result containing log-det gains and diagnostics
        output_path: Path where optimized design was written

    Returns:
        List of formatted message strings for display
    """
    messages = []

    messages.append(
        f"[green]Optimization succeeded[/]: "
        f"log-det gain {result.log_det_gain:.4f} "
        f"({result.baseline_log_det:.4f} → {result.optimized_log_det:.4f})"
    )
    messages.append(f"New comparisons written to {output_path}")
    messages.append(
        f"Minimum required new slots: {result.min_slots_required} "
        f"(anchor adjacency additions {result.anchor_adjacency_count}, "
        f"locked pairs {result.locked_pair_count}, "
        f"coverage {result.required_pair_count})"
    )
    messages.append(
        "Total comparisons (combined): "
        f"{result.total_comparisons} | New comparisons: {result.new_comparisons} "
        f"(baseline locked {result.baseline_slots_in_design}, max repeat {result.max_repeat})"
    )

    messages.append("Type distribution (optimized):")
    for comp_type, count in result.optimized_diagnostics.type_counts.items():
        messages.append(f"  {comp_type:<16} {count}")

    coverage = result.optimized_diagnostics.student_anchor_coverage
    if coverage:
        messages.append("Student anchor coverage:")
        for student in sorted(coverage):
            anchors = ", ".join(coverage[student]) or "—"
            messages.append(f"  {student:<10} {anchors}")
    else:
        messages.append("Student anchor coverage: none")

    missing = sorted(set(result.students) - set(coverage))
    if missing:
        messages.append("[yellow]Warning[/]: Missing anchor coverage for " + ", ".join(missing))

    repeats = result.optimized_diagnostics.repeat_counts
    if repeats:
        messages.append("Repeated pairs (>1 occurrence):")
        for key, count in sorted(repeats.items()):
            messages.append(f"  {key}: {count}×")
    else:
        messages.append("Repeated pairs: none")

    return messages


def format_assignment_summary(
    quotas: dict[str, int],
    requested_total: int,
    available_total: int,
    output_path: Path,
) -> list[str]:
    """Format assignment result into display messages.

    Args:
        quotas: Per-rater assignment quotas
        requested_total: Total comparisons requested
        available_total: Total comparisons available
        output_path: Path where assignments were written

    Returns:
        List of formatted message strings for display
    """
    messages = []
    actual_counts = list(quotas.values())
    shortage = requested_total > available_total

    if shortage:
        messages.append(
            f"[yellow]Notice[/]: Requested {requested_total} comparisons but only "
            f"{available_total} available."
        )

    messages.append(
        f"Success: Generated assignments for {len(quotas)} raters "
        f"(min {min(actual_counts)}, max {max(actual_counts)})."
    )
    messages.append(
        f"Total allocated comparisons: {sum(actual_counts)} (requested {requested_total})."
    )
    messages.append(f"Output written to {output_path}")

    return messages
