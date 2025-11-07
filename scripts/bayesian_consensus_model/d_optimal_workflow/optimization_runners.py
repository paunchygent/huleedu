from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

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
    student_index = {student: idx for idx, student in enumerate(students)}
    anchor_index = {anchor: idx for idx, anchor in enumerate(anchors)}

    baseline_design: List[DesignEntry] = [
        DesignEntry(entry.candidate, locked=True) for entry in spec.baseline_design
    ]
    baseline_counts: Counter[Tuple[str, str]] = Counter()
    for entry in baseline_design:
        baseline_counts[entry.candidate.key()] += 1
        count = baseline_counts[entry.candidate.key()]
        if count > max_repeat:
            raise ValueError(
                "Baseline pair "
                f"{entry.candidate.essay_a} vs {entry.candidate.essay_b} "
                f"({entry.candidate.comparison_type}) occurs {count} times, "
                f"exceeding max_repeat {max_repeat}."
            )

    locked_candidates: List[PairCandidate] = []
    for essay_a, essay_b in spec.locked_pairs:
        a_is_anchor = essay_a in anchor_set
        b_is_anchor = essay_b in anchor_set
        if a_is_anchor and b_is_anchor:
            comp_type = "anchor_anchor"
            if anchor_index[essay_a] > anchor_index[essay_b]:
                essay_a, essay_b = essay_b, essay_a
        elif a_is_anchor or b_is_anchor:
            comp_type = "student_anchor"
            if a_is_anchor:
                essay_a, essay_b = essay_b, essay_a
        else:
            comp_type = "student_student"
            if student_index[essay_a] > student_index[essay_b]:
                essay_a, essay_b = essay_b, essay_a
        locked_candidates.append(PairCandidate(essay_a, essay_b, comp_type))

    required_pairs = derive_required_student_anchor_pairs(
        students=students,
        anchors=anchors,
        anchor_order=anchors,
        baseline_design=baseline_design,
    )

    adjacency_pairs = derive_anchor_adjacency_constraints(anchors)
    anchor_adjacency_needed = sum(
        1 for pair in adjacency_pairs if baseline_counts.get(pair.key(), 0) == 0
    )

    locked_required_keys = {
        pair.key() for pair in locked_candidates if baseline_counts.get(pair.key(), 0) == 0
    }
    locked_required_count = len(locked_required_keys)

    required_count = unique_pair_count(required_pairs)
    baseline_slots = len(baseline_design)
    min_slots_required = anchor_adjacency_needed + locked_required_count + required_count
    if spec.total_slots < min_slots_required:
        raise ValueError(
            f"Minimum required new slots not met: requested "
            f"{spec.total_slots}, but anchor adjacency adds {anchor_adjacency_needed}, "
            f"locked pairs add {locked_required_count}, "
            f"and coverage requires {required_count} "
            f"(total {min_slots_required}). Increase total slots."
        )

    optimized_design, _ = select_design(
        students,
        anchors,
        total_slots=spec.total_slots,
        anchor_order=anchors,
        baseline_design=baseline_design,
        locked_pairs=locked_candidates,
        required_pairs=required_pairs,
        max_repeat=max_repeat,
        include_anchor_anchor=spec.include_anchor_anchor,
    )

    combined_items = list(students) + list(anchors)
    index_map = {item: idx for idx, item in enumerate(combined_items)}
    baseline_log_det = (
        compute_log_det(baseline_design, index_map) if baseline_design else float("-inf")
    )
    optimized_log_det = compute_log_det(optimized_design, index_map)

    baseline_diag = summarize_design(baseline_design, anchors)
    optimized_diag = summarize_design(optimized_design, anchors)

    baseline_signature_counts: Counter[Tuple[str, str, str]] = Counter(
        (entry.candidate.essay_a, entry.candidate.essay_b, entry.candidate.comparison_type)
        for entry in baseline_design
    )
    new_design: List[DesignEntry] = []
    for entry in optimized_design:
        signature = (
            entry.candidate.essay_a,
            entry.candidate.essay_b,
            entry.candidate.comparison_type,
        )
        if baseline_signature_counts.get(signature, 0) > 0:
            baseline_signature_counts[signature] -= 1
            continue
        new_design.append(entry)

    return OptimizationResult(
        students=students,
        anchor_order=anchors,
        baseline_design=baseline_design,
        new_design=new_design,
        optimized_design=optimized_design,
        baseline_log_det=baseline_log_det,
        optimized_log_det=optimized_log_det,
        baseline_diagnostics=baseline_diag,
        optimized_diagnostics=optimized_diag,
        anchor_adjacency_count=anchor_adjacency_needed,
        required_pair_count=required_count,
        locked_pair_count=locked_required_count,
        baseline_slots_in_design=baseline_slots,
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
        new_design=list(optimized_design),
        optimized_design=optimized_design,
        baseline_log_det=baseline_log_det,
        optimized_log_det=optimized_log_det,
        baseline_diagnostics=baseline_diag,
        optimized_diagnostics=optimized_diag,
        anchor_adjacency_count=anchor_adjacency_count,
        required_pair_count=required_pair_count,
        locked_pair_count=0,
        baseline_slots_in_design=0,
        max_repeat=max_repeat,
    )


__all__ = [
    "optimize_from_dynamic_spec",
    "optimize_from_payload",
    "optimize_schedule",
]
