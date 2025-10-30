from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

import numpy as np


ComparisonType = str


@dataclass(frozen=True)
class PairCandidate:
    essay_a: str
    essay_b: str
    comparison_type: ComparisonType

    def key(self) -> Tuple[str, str]:
        return (self.essay_a, self.essay_b)


@dataclass(frozen=True)
class DesignEntry:
    candidate: PairCandidate
    locked: bool = False


def _build_index_map(items: Sequence[str]) -> Dict[str, int]:
    return {item: idx for idx, item in enumerate(items)}


def _pair_vector(candidate: PairCandidate, index_map: Dict[str, int]) -> np.ndarray:
    size = len(index_map)
    vec = np.zeros(size, dtype=float)
    vec[index_map[candidate.essay_a]] += 1.0
    vec[index_map[candidate.essay_b]] -= 1.0
    return vec


def compute_log_det(design: Sequence[DesignEntry], index_map: Dict[str, int], *, epsilon: float = 1e-3) -> float:
    size = len(index_map)
    information = np.eye(size, dtype=float) * epsilon
    for entry in design:
        vec = _pair_vector(entry.candidate, index_map)
        information += np.outer(vec, vec)
    sign, log_det = np.linalg.slogdet(information)
    if sign <= 0:
        return float("-inf")
    return float(log_det)


def build_candidate_universe(
    students: Sequence[str],
    anchors: Sequence[str],
    *,
    include_student_student: bool = True,
    include_anchor_anchor: bool = True,
) -> List[PairCandidate]:
    candidates: List[PairCandidate] = []
    for student in students:
        for anchor in anchors:
            candidates.append(PairCandidate(student, anchor, "student_anchor"))

    if include_student_student:
        for idx in range(len(students)):
            for jdx in range(idx + 1, len(students)):
                candidates.append(PairCandidate(students[idx], students[jdx], "student_student"))

    if include_anchor_anchor:
        for idx in range(len(anchors)):
            for jdx in range(idx + 1, len(anchors)):
                candidates.append(PairCandidate(anchors[idx], anchors[jdx], "anchor_anchor"))

    return candidates


def derive_anchor_adjacency_constraints(anchor_order: Sequence[str]) -> List[PairCandidate]:
    constraints: List[PairCandidate] = []
    for idx in range(len(anchor_order) - 1):
        pair = PairCandidate(anchor_order[idx], anchor_order[idx + 1], "anchor_anchor")
        constraints.append(pair)
    return constraints


def ensure_required_pairs(
    design: List[DesignEntry],
    counts: Dict[Tuple[str, str], int],
    required_pairs: Iterable[PairCandidate],
    candidate_lookup: Dict[Tuple[str, str], PairCandidate],
    *,
    max_repeat: int,
) -> None:
    for pair in required_pairs:
        key = pair.key()
        current = counts.get(key, 0)
        if current >= max_repeat:
            continue
        if current == 0:
            candidate = candidate_lookup.get(key, pair)
            design.append(DesignEntry(candidate, locked=True))
            counts[key] = 1


def greedy_fill(
    design: List[DesignEntry],
    counts: Dict[Tuple[str, str], int],
    candidates: Sequence[PairCandidate],
    slots: int,
    index_map: Dict[str, int],
    *,
    max_repeat: int,
    tolerance: float = 1e-9,
) -> float:
    current_score = compute_log_det(design, index_map)
    for _ in range(slots):
        best_candidate: PairCandidate | None = None
        best_score = current_score
        for candidate in candidates:
            key = candidate.key()
            if counts.get(key, 0) >= max_repeat:
                continue
            trial_design = design + [DesignEntry(candidate)]
            score = compute_log_det(trial_design, index_map)
            if score > best_score + tolerance:
                best_candidate = candidate
                best_score = score
        if best_candidate is None:
            break
        design.append(DesignEntry(best_candidate))
        counts[best_candidate.key()] = counts.get(best_candidate.key(), 0) + 1
        current_score = best_score
    return current_score


def fedorov_exchange(
    design: List[DesignEntry],
    counts: Dict[Tuple[str, str], int],
    candidates: Sequence[PairCandidate],
    index_map: Dict[str, int],
    *,
    max_repeat: int,
    max_iterations: int = 25,
    tolerance: float = 1e-9,
) -> float:
    current_score = compute_log_det(design, index_map)
    for _ in range(max_iterations):
        improved = False
        for idx, entry in enumerate(design):
            if entry.locked:
                continue
            remove_key = entry.candidate.key()
            for candidate in candidates:
                add_key = candidate.key()
                if add_key == remove_key:
                    continue
                if counts.get(add_key, 0) >= max_repeat:
                    continue

                trial_design = design.copy()
                trial_counts = counts.copy()

                trial_counts[remove_key] -= 1
                if trial_counts[remove_key] <= 0:
                    trial_counts.pop(remove_key, None)

                trial_counts[add_key] = trial_counts.get(add_key, 0) + 1
                trial_design[idx] = DesignEntry(candidate)

                score = compute_log_det(trial_design, index_map)
                if score > current_score + tolerance:
                    design[:] = trial_design
                    counts.clear()
                    counts.update(trial_counts)
                    current_score = score
                    improved = True
                    break

            if improved:
                break

        if not improved:
            break
    return current_score


def _add_locked_pairs(
    design: List[DesignEntry],
    counts: Dict[Tuple[str, str], int],
    candidate_lookup: Dict[Tuple[str, str], PairCandidate],
    locked_pairs: Sequence[PairCandidate],
    *,
    max_repeat: int,
) -> None:
    for pair in locked_pairs:
        key = pair.key()
        if counts.get(key, 0) >= max_repeat:
            continue
        candidate = candidate_lookup.get(key, pair)
        design.append(DesignEntry(candidate, locked=True))
        counts[key] = counts.get(key, 0) + 1


def select_design(
    students: Sequence[str],
    anchors: Sequence[str],
    *,
    total_slots: int,
    anchor_order: Sequence[str],
    locked_pairs: Sequence[PairCandidate] = (),
    required_pairs: Sequence[PairCandidate] = (),
    max_repeat: int = 3,
) -> Tuple[List[DesignEntry], float]:
    items = list(students) + list(anchors)
    index_map = _build_index_map(items)

    candidates = build_candidate_universe(students, anchors)
    candidate_lookup = {candidate.key(): candidate for candidate in candidates}

    design: List[DesignEntry] = []
    counts: Dict[Tuple[str, str], int] = {}

    _add_locked_pairs(design, counts, candidate_lookup, locked_pairs, max_repeat=max_repeat)

    ensure_required_pairs(
        design,
        counts,
        derive_anchor_adjacency_constraints(anchor_order),
        candidate_lookup,
        max_repeat=max_repeat,
    )

    ensure_required_pairs(
        design,
        counts,
        required_pairs,
        candidate_lookup,
        max_repeat=max_repeat,
    )

    remaining_slots = total_slots - len(design)
    if remaining_slots < 0:
        raise ValueError("No remaining slots after applying locked constraints.")

    score = greedy_fill(design, counts, candidates, remaining_slots, index_map, max_repeat=max_repeat)
    score = fedorov_exchange(design, counts, candidates, index_map, max_repeat=max_repeat)

    return design, score
