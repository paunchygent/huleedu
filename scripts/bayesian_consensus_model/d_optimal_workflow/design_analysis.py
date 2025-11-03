from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from ..d_optimal_optimizer import DesignEntry, PairCandidate
from .models import DesignDiagnostics


def unique_pair_count(pairs: Iterable[PairCandidate]) -> int:
    """Count distinct comparison pairs by essay IDs."""
    return len({pair.key() for pair in pairs})


def derive_student_anchor_requirements(
    baseline_design: Sequence[DesignEntry],
    anchor_order: Sequence[str],
) -> List[PairCandidate]:
    """Derive minimum student-anchor comparisons needed to preserve brackets."""
    anchor_index = {anchor: idx for idx, anchor in enumerate(anchor_order)}
    student_to_anchors: Dict[str, set[str]] = defaultdict(set)

    for entry in baseline_design:
        if entry.candidate.comparison_type != "student_anchor":
            continue
        essay_a = entry.candidate.essay_a
        essay_b = entry.candidate.essay_b
        if essay_a in anchor_index and essay_b in anchor_index:
            continue
        if essay_a in anchor_index:
            anchor = essay_a
            student = essay_b
        elif essay_b in anchor_index:
            anchor = essay_b
            student = essay_a
        else:
            continue
        student_to_anchors[student].add(anchor)

    requirements: List[PairCandidate] = []
    seen: set[Tuple[str, str]] = set()
    for student, anchors in student_to_anchors.items():
        if not anchors:
            continue
        ordered = sorted(anchors, key=lambda name: anchor_index[name])
        if len(ordered) >= 3:
            picks = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
        else:
            picks = ordered
        for anchor in picks:
            key = (student, anchor)
            if key in seen:
                continue
            requirements.append(PairCandidate(student, anchor, "student_anchor"))
            seen.add(key)
    return requirements


def summarize_design(
    design: Sequence[DesignEntry],
    anchor_order: Sequence[str],
) -> DesignDiagnostics:
    """Return design diagnostics."""
    anchor_index = {anchor: idx for idx, anchor in enumerate(anchor_order)}
    anchor_set = set(anchor_order)

    type_counts: Counter[str] = Counter()
    coverage: Dict[str, set[str]] = defaultdict(set)
    repeats: Counter[Tuple[str, str]] = Counter()

    for entry in design:
        candidate = entry.candidate
        type_counts[candidate.comparison_type] += 1
        repeats[candidate.key()] += 1

        if candidate.comparison_type != "student_anchor":
            continue
        a_is_anchor = candidate.essay_a in anchor_set
        b_is_anchor = candidate.essay_b in anchor_set
        if a_is_anchor == b_is_anchor:
            continue
        student = candidate.essay_b if a_is_anchor else candidate.essay_a
        anchor = candidate.essay_a if a_is_anchor else candidate.essay_b
        coverage[student].add(anchor)

    ordered_coverage: Dict[str, List[str]] = {}
    for student, anchors in coverage.items():
        sorted_anchors = sorted(
            list(anchors),
            key=lambda name: anchor_index.get(name, len(anchor_index)),
        )
        ordered_coverage[student] = sorted_anchors

    repeat_counts = {f"{pair[0]}|{pair[1]}": count for pair, count in repeats.items() if count > 1}

    return DesignDiagnostics(
        total_pairs=len(design),
        type_counts=dict(sorted(type_counts.items())),
        student_anchor_coverage={
            student: ordered_coverage[student] for student in sorted(ordered_coverage)
        },
        repeat_counts=repeat_counts,
    )


__all__ = [
    "derive_student_anchor_requirements",
    "summarize_design",
    "unique_pair_count",
]
