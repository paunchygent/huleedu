from __future__ import annotations

import random
from typing import Dict, List, Sequence, Tuple

from ..d_optimal_optimizer import (
    DesignEntry,
    PairCandidate,
    compute_log_det,
    derive_anchor_adjacency_constraints,
    select_design,
)
from .design_analysis import summarize_design, unique_pair_count
from .models import DEFAULT_ANCHOR_ORDER, OptimizationResult


def _build_random_design(
    students: Sequence[str],
    anchors: Sequence[str],
    *,
    total_slots: int,
    max_repeat: int,
    seed: int,
) -> List[DesignEntry]:
    """Create a random baseline schedule for synthetic demonstrations."""
    candidates: List[PairCandidate] = []
    counts: Dict[Tuple[str, str], int] = {}
    design: List[DesignEntry] = []

    for student in students:
        for anchor in anchors:
            candidates.append(PairCandidate(student, anchor, "student_anchor"))
    for idx in range(len(students)):
        for jdx in range(idx + 1, len(students)):
            candidates.append(PairCandidate(students[idx], students[jdx], "student_student"))
    for idx in range(len(anchors)):
        for jdx in range(idx + 1, len(anchors)):
            candidates.append(PairCandidate(anchors[idx], anchors[jdx], "anchor_anchor"))

    rng = random.Random(seed)
    for _ in range(total_slots):
        eligible = [
            candidate
            for candidate in candidates
            if counts.get(candidate.key(), 0) < max_repeat
        ]
        if not eligible:
            break
        picked = rng.choice(eligible)
        design.append(DesignEntry(picked))
        counts[picked.key()] = counts.get(picked.key(), 0) + 1
    return design


def run_synthetic_optimization(
    *,
    total_slots: int,
    max_repeat: int,
    seed: int,
    anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
) -> OptimizationResult:
    """Execute the optimizer against a deterministic synthetic dataset."""
    students = ["JA24", "II24", "ES24", "EK24", "ER24", "TK24", "SN24", "HJ17"]

    baseline_design = _build_random_design(
        students,
        anchor_order,
        total_slots=total_slots,
        max_repeat=max_repeat,
        seed=seed,
    )

    adjacency_pairs = derive_anchor_adjacency_constraints(anchor_order)
    anchor_adjacency_count = unique_pair_count(adjacency_pairs)
    required_pair_count = 0
    if total_slots < anchor_adjacency_count:
        raise ValueError(
            "Minimum required slots not met: requested "
            f"{total_slots}, but anchor adjacency requires {anchor_adjacency_count}. "
            "Increase total slots to run the synthetic demonstration."
        )

    optimized_design, _ = select_design(
        students,
        anchor_order,
        total_slots=total_slots,
        anchor_order=anchor_order,
        max_repeat=max_repeat,
    )

    index_map = {item: idx for idx, item in enumerate(list(students) + list(anchor_order))}
    baseline_log_det = compute_log_det(baseline_design, index_map)
    optimized_log_det = compute_log_det(optimized_design, index_map)

    baseline_diag = summarize_design(baseline_design, anchor_order)
    optimized_diag = summarize_design(optimized_design, anchor_order)

    return OptimizationResult(
        students=list(students),
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
    "run_synthetic_optimization",
]
