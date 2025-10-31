from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence

from ..d_optimal_optimizer import (
    DesignEntry,
    PairCandidate,
    compute_log_det,
    derive_anchor_adjacency_constraints,
    derive_required_student_anchor_pairs,
    select_design,
)
from .data_loaders import (
    load_baseline_design,
    load_baseline_from_records,
)
from .design_analysis import (
    derive_student_anchor_requirements,
    summarize_design,
    unique_pair_count,
)
from .models import (
    DEFAULT_ANCHOR_ORDER,
    BaselinePayload,
    DynamicSpec,
    OptimizationResult,
)


def optimize_from_payload(
    payload: BaselinePayload,
    *,
    total_slots: int | None,
    max_repeat: int,
    anchor_order: Sequence[str] | None = None,
) -> OptimizationResult:
    """Run optimization for a pre-normalized baseline payload."""
    effective_slots = total_slots if total_slots is not None else payload.total_slots
    effective_anchor_order = (
        list(anchor_order) if anchor_order is not None else list(payload.anchor_order)
    )

    return optimize_schedule(
        pairs_path=None,
        total_slots=effective_slots,
        max_repeat=max_repeat,
        anchor_order=effective_anchor_order,
        baseline_records=payload.records,
    )


def optimize_from_dynamic_spec(
    spec: DynamicSpec,
    *,
    max_repeat: int = 3,
) -> OptimizationResult:
    """Run the optimizer using a dynamic input specification."""
    students = list(spec.students)
    anchors = list(spec.anchors)
    anchor_set = set(anchors)

    baseline_design: List[DesignEntry] = []
    if spec.previous_comparisons:
        for rec in spec.previous_comparisons:
            candidate = PairCandidate(rec.essay_a_id, rec.essay_b_id, rec.comparison_type)
            baseline_design.append(DesignEntry(candidate, locked=False))

    locked_candidates: List[PairCandidate] = []
    for essay_a, essay_b in spec.locked_pairs:
        a_is_anchor = essay_a in anchor_set
        b_is_anchor = essay_b in anchor_set
        if a_is_anchor and b_is_anchor:
            comp_type = "anchor_anchor"
        elif a_is_anchor or b_is_anchor:
            comp_type = "student_anchor"
        else:
            comp_type = "student_student"
        locked_candidates.append(PairCandidate(essay_a, essay_b, comp_type))

    required_pairs = derive_required_student_anchor_pairs(
        students=students,
        anchors=anchors,
        anchor_order=anchors,
        baseline_design=baseline_design,
    )

    adjacency_pairs = derive_anchor_adjacency_constraints(anchors)
    anchor_adjacency_count = unique_pair_count(adjacency_pairs)

    locked_count = unique_pair_count(locked_candidates)
    required_count = unique_pair_count(required_pairs)
    min_slots_required = anchor_adjacency_count + locked_count + required_count
    if spec.total_slots < min_slots_required:
        raise ValueError(
            f"Minimum required slots not met: requested "
            f"{spec.total_slots}, but anchor adjacency requires {anchor_adjacency_count}, "
            f"locked pairs require {locked_count}, "
            f"and baseline coverage requires {required_count} "
            f"(total {min_slots_required}). Increase total slots."
        )

    optimized_design, _ = select_design(
        students,
        anchors,
        total_slots=spec.total_slots,
        anchor_order=anchors,
        locked_pairs=locked_candidates,
        required_pairs=required_pairs,
        max_repeat=max_repeat,
        include_anchor_anchor=spec.include_anchor_anchor,
    )

    combined_items = list(students) + list(anchors)
    index_map = {item: idx for idx, item in enumerate(combined_items)}
    if baseline_design:
        baseline_log_det = compute_log_det(baseline_design, index_map)
    else:
        baseline_log_det = float("-inf")
    optimized_log_det = compute_log_det(optimized_design, index_map)

    baseline_diag = summarize_design(baseline_design, anchors)
    optimized_diag = summarize_design(optimized_design, anchors)

    return OptimizationResult(
        students=students,
        anchor_order=anchors,
        baseline_design=baseline_design,
        optimized_design=optimized_design,
        baseline_log_det=baseline_log_det,
        optimized_log_det=optimized_log_det,
        baseline_diagnostics=baseline_diag,
        optimized_diagnostics=optimized_diag,
        anchor_adjacency_count=anchor_adjacency_count,
        required_pair_count=required_count,
        max_repeat=max_repeat,
    )


def optimize_schedule(
    pairs_path: Optional[Path] = None,
    *,
    total_slots: int | None,
    max_repeat: int,
    anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
    baseline_records: Optional[Iterable[Mapping[str, object]]] = None,
) -> OptimizationResult:
    """Run the optimizer against a baseline design and return metrics."""
    if baseline_records is not None:
        students, baseline_design = load_baseline_from_records(
            baseline_records,
            anchor_order=anchor_order,
        )
    else:
        if pairs_path is None:
            raise ValueError("Provide either pairs_path or baseline_records to optimize.")
        students, baseline_design = load_baseline_design(
            pairs_path,
            anchor_order=anchor_order,
        )
    if not students:
        raise ValueError("No student essays detected in the baseline design.")

    slots = total_slots if total_slots is not None else len(baseline_design)
    adjacency_pairs = derive_anchor_adjacency_constraints(anchor_order)
    required_pairs = derive_student_anchor_requirements(baseline_design, anchor_order)
    anchor_adjacency_count = unique_pair_count(adjacency_pairs)
    required_pair_count = unique_pair_count(required_pairs)
    min_slots_required = anchor_adjacency_count + required_pair_count
    if slots < min_slots_required:
        raise ValueError(
            "Minimum required slots not met: requested "
            f"{slots}, but anchor adjacency requires {anchor_adjacency_count} "
            f"and baseline coverage requires {required_pair_count} "
            f"(total {min_slots_required}). Increase total slots or relax the baseline payload."
        )

    optimized_design, _ = select_design(
        students,
        anchor_order,
        total_slots=slots,
        anchor_order=anchor_order,
        required_pairs=required_pairs,
        max_repeat=max_repeat,
    )

    combined_items = list(students) + list(anchor_order)
    index_map = {item: idx for idx, item in enumerate(combined_items)}
    baseline_log_det = compute_log_det(baseline_design, index_map)
    optimized_log_det = compute_log_det(optimized_design, index_map)

    baseline_diag = summarize_design(baseline_design, anchor_order)
    optimized_diag = summarize_design(optimized_design, anchor_order)

    return OptimizationResult(
        students=students,
        anchor_order=list(anchor_order),
        baseline_design=baseline_design,
        optimized_design=optimized_design,
        baseline_log_det=baseline_log_det,
        optimized_log_det=optimized_log_det,
        baseline_diagnostics=baseline_diag,
        optimized_diagnostics=optimized_diag,
        anchor_adjacency_count=anchor_adjacency_count,
        required_pair_count=required_pair_count,
        max_repeat=max_repeat,
    )


__all__ = [
    "optimize_from_dynamic_spec",
    "optimize_from_payload",
    "optimize_schedule",
]
