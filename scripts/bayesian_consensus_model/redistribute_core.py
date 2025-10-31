from __future__ import annotations

import csv
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

# REMOVED: StatusSelector enum - status filtering is no longer used


@dataclass(frozen=True)
class Comparison:
    pair_id: int
    essay_a_id: str
    essay_b_id: str
    comparison_type: str


def read_pairs(path: Path) -> List[Comparison]:
    if not path.exists():
        raise FileNotFoundError(f"Pairs CSV not found: {path}")

    comparisons: List[Comparison] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"pair_id", "essay_a_id", "essay_b_id", "comparison_type"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            fields = ", ".join(sorted(missing))
            raise ValueError(f"Pairs CSV missing required columns: {fields}")

        for row in reader:
            try:
                pair_id = int(row["pair_id"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid pair_id '{row['pair_id']}' in {path}") from exc
            comparisons.append(
                Comparison(
                    pair_id=pair_id,
                    essay_a_id=row["essay_a_id"],
                    essay_b_id=row["essay_b_id"],
                    comparison_type=row["comparison_type"],
                )
            )

    comparisons.sort(key=lambda item: item.pair_id)
    return comparisons


def build_rater_list(
    count: Optional[int],
    names: Optional[Sequence[str]],
) -> List[str]:
    if names:
        parsed: List[str] = []
        for entry in names:
            parsed.extend(name.strip() for name in entry.split(",") if name.strip())
        if not parsed:
            raise ValueError("No valid rater names supplied.")
        return parsed

    if count is None:
        raise ValueError("Provide a positive rater count or explicit names.")
    if count <= 0:
        raise ValueError("Rater count must be a positive integer.")

    return [f"Rater_{idx:02d}" for idx in range(1, count + 1)]


# REMOVED: filter_comparisons - status filtering is no longer used


def select_comparisons(
    comparisons: Sequence[Comparison],
    total_needed: int,
) -> List[Comparison]:
    if total_needed > len(comparisons):
        raise ValueError(
            f"Requested {total_needed} comparisons but only {len(comparisons)} available."
        )
    return list(comparisons[:total_needed])


def compute_quota_distribution(
    rater_names: Sequence[str],
    desired_per_rater: int,
    total_available: int,
) -> Dict[str, int]:
    if desired_per_rater <= 0:
        raise ValueError("Comparisons per rater must be a positive integer.")
    if total_available < 0:
        raise ValueError("Total available comparisons cannot be negative.")

    quotas: Dict[str, int] = {}
    rater_count = len(rater_names)
    if rater_count == 0:
        return quotas

    base = min(desired_per_rater, total_available // rater_count) if rater_count else 0
    remainder = total_available - (base * rater_count)

    for index, name in enumerate(rater_names):
        extra = 1 if remainder > 0 and base < desired_per_rater else 0
        if extra:
            remainder -= 1
        quota = min(desired_per_rater, base + extra)
        quotas[name] = quota

    # Distribute any remaining comparisons without exceeding desired_per_rater
    idx = 0
    while remainder > 0 and rater_names:
        name = rater_names[idx % rater_count]
        if quotas[name] < desired_per_rater:
            quotas[name] += 1
            remainder -= 1
        idx += 1

    assigned_total = sum(quotas.values())
    if assigned_total > total_available:
        # Trim excess starting from last to preserve earlier allocations
        overflow = assigned_total - total_available
        for name in reversed(rater_names):
            reclaimable = min(overflow, quotas[name])
            quotas[name] -= reclaimable
            overflow -= reclaimable
            if overflow == 0:
                break

    return quotas


def load_comparisons_from_records(
    records: Iterable[Mapping[str, Union[str, int]]],
) -> List[Comparison]:
    comparisons: List[Comparison] = []
    next_pair_id = 1
    for record in records:
        try:
            essay_a_id = str(record["essay_a_id"])
            essay_b_id = str(record["essay_b_id"])
            comparison_type = str(record.get("comparison_type", "student_anchor"))
        except KeyError as exc:
            raise ValueError(f"Missing comparison field: {exc.args[0]}") from exc

        raw_pair = record.get("pair_id")
        if raw_pair is None:
            pair_id = next_pair_id
        else:
            try:
                pair_id = int(raw_pair)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise ValueError(f"Invalid pair_id value: {raw_pair}") from exc

        comparisons.append(
            Comparison(
                pair_id=pair_id,
                essay_a_id=essay_a_id,
                essay_b_id=essay_b_id,
                comparison_type=comparison_type,
            )
        )
        next_pair_id = max(next_pair_id, pair_id + 1)

    comparisons.sort(key=lambda item: item.pair_id)
    return comparisons


def assign_pairs(
    comparisons: Sequence[Comparison],
    rater_names: Sequence[str],
    per_rater: Union[int, Sequence[int], Mapping[str, int]],
) -> List[Tuple[str, Comparison]]:
    quotas: Dict[str, int]
    if isinstance(per_rater, int):
        if per_rater <= 0:
            raise ValueError("Comparisons per rater must be a positive integer.")
        quotas = {rater: per_rater for rater in rater_names}
    elif isinstance(per_rater, Mapping):
        missing = [name for name in rater_names if name not in per_rater]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(f"Missing quota for raters: {missing_list}")
        quotas = {name: int(per_rater[name]) for name in rater_names}
    else:
        per_rater_list = list(per_rater)
        if len(per_rater_list) != len(rater_names):
            raise ValueError("Per-rater sequence length must match number of rater names.")
        quotas = {name: int(count) for name, count in zip(rater_names, per_rater_list)}

    total_needed = sum(max(count, 0) for count in quotas.values())
    ordered: List[Comparison] = list(comparisons)[:total_needed]
    if len(ordered) < total_needed:
        raise ValueError(
            f"Requested {total_needed} assignments but only {len(ordered)} comparisons available."
        )

    type_queues: Dict[str, Deque[Comparison]] = {}
    for comparison in ordered:
        type_queues.setdefault(comparison.comparison_type, deque()).append(comparison)

    rater_state: Dict[str, _RaterAllocation] = {
        rater: _RaterAllocation(remaining=max(quotas.get(rater, 0), 0), type_counts=Counter())
        for rater in rater_names
    }

    type_cycle = deque(sorted(type_queues, key=lambda key: (-len(type_queues[key]), key)))
    assignments: List[Tuple[str, Comparison]] = []

    while type_cycle:
        comparison_type = type_cycle[0]
        queue = type_queues[comparison_type]
        if not queue:
            type_cycle.popleft()
            continue

        comparison = queue.popleft()
        rater = _select_rater_for_type(rater_state, comparison_type)

        state = rater_state[rater]
        state.remaining -= 1
        state.type_counts[comparison_type] += 1

        assignments.append((rater, comparison))

        if queue:
            type_cycle.rotate(-1)
        else:
            type_cycle.popleft()

    if any(state.remaining for state in rater_state.values()):
        raise ValueError("Insufficient comparisons to satisfy the requested allocation.")

    return assignments


def _select_rater_for_type(
    rater_state: Dict[str, "_RaterAllocation"],
    comparison_type: str,
) -> str:
    eligible = [
        (name, state)
        for name, state in rater_state.items()
        if state.remaining
    ]
    if not eligible:
        raise ValueError("No raters remain eligible for additional comparisons.")

    def sort_key(item: Tuple[str, "_RaterAllocation"]) -> Tuple[int, int, str]:
        name, state = item
        return (state.type_counts.get(comparison_type, 0), -state.remaining, name)

    selected_name, _ = min(eligible, key=sort_key)
    return selected_name


@dataclass
class _RaterAllocation:
    remaining: int
    type_counts: Counter[str]


def write_assignments(
    output_path: Path,
    assignments: Sequence[Tuple[str, Comparison]],
) -> None:
    # Build auto-generated display name mapping for complete anonymization
    all_essay_ids: set[str] = set()
    for _, comparison in assignments:
        all_essay_ids.add(comparison.essay_a_id)
        all_essay_ids.add(comparison.essay_b_id)

    # Sort for deterministic mapping (same input → same display codes)
    sorted_essays = sorted(all_essay_ids)
    display_mapping = {
        essay_id: f"essay_{idx:02d}"
        for idx, essay_id in enumerate(sorted_essays, start=1)
    }

    fieldnames = [
        "rater_name",
        "pair_id",
        "essay_a_id",
        "essay_b_id",
        "essay_a_display",
        "essay_b_display",
        "comparison_type",
    ]
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for rater, comparison in assignments:
            writer.writerow(
                {
                    "rater_name": rater,
                    "pair_id": comparison.pair_id,
                    "essay_a_id": comparison.essay_a_id,
                    "essay_b_id": comparison.essay_b_id,
                    "essay_a_display": display_mapping[comparison.essay_a_id],
                    "essay_b_display": display_mapping[comparison.essay_b_id],
                    "comparison_type": comparison.comparison_type,
                }
            )
