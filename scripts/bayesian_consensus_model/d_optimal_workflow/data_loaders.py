from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from ..d_optimal_optimizer import DesignEntry, PairCandidate
from ..redistribute_core import load_comparisons_from_records
from .models import (
    DEFAULT_ANCHOR_ORDER,
    BaselinePayload,
    ComparisonRecord,
    DynamicSpec,
)


def load_dynamic_spec(
    students: Sequence[str],
    *,
    anchors: Optional[Sequence[str]] = None,
    include_anchor_anchor: bool = True,
    previous_comparisons: Optional[Sequence[ComparisonRecord]] = None,
    locked_pairs: Optional[Sequence[Tuple[str, str]]] = None,
    total_slots: int,
) -> DynamicSpec:
    """Build and validate a dynamic input specification for the optimizer."""
    student_list = list(students)
    if not student_list:
        raise ValueError("Students list cannot be empty.")

    anchor_list = list(anchors) if anchors is not None else list(DEFAULT_ANCHOR_ORDER)
    if not anchor_list:
        raise ValueError("Anchors list cannot be empty.")

    previous_list: List[ComparisonRecord] = []
    if previous_comparisons is not None:
        previous_list = list(previous_comparisons)

    locked_list: List[Tuple[str, str]] = []
    if locked_pairs is not None:
        essay_ids = set(student_list) | set(anchor_list)
        for pair in locked_pairs:
            if len(pair) != 2:
                raise ValueError(f"Locked pair must have exactly 2 elements: {pair}")
            essay_a, essay_b = pair
            if essay_a not in essay_ids:
                raise ValueError(f"Locked pair references unknown essay ID: {essay_a}")
            if essay_b not in essay_ids:
                raise ValueError(f"Locked pair references unknown essay ID: {essay_b}")
            locked_list.append((essay_a, essay_b))

    if total_slots <= 0:
        raise ValueError(f"Total slots must be positive, got: {total_slots}")

    adjacency_count = len(anchor_list) - 1
    locked_count = len(locked_list)
    min_required = adjacency_count + locked_count

    if total_slots < min_required:
        raise ValueError(
            f"Total slots ({total_slots}) insufficient: "
            f"anchor adjacency requires {adjacency_count}, "
            f"locked pairs require {locked_count} "
            f"(minimum {min_required} slots needed)."
        )

    return DynamicSpec(
        students=student_list,
        anchors=anchor_list,
        include_anchor_anchor=include_anchor_anchor,
        previous_comparisons=previous_list,
        locked_pairs=locked_list,
        total_slots=total_slots,
    )


def load_baseline_payload(
    path: Path,
    *,
    fallback_anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
) -> BaselinePayload:
    """Parse a JSON payload describing baseline comparisons for optimization."""
    if not path.exists():
        raise FileNotFoundError(f"Baseline JSON not found: {path}")

    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid JSON payload in {path}") from exc

    anchor_order: Sequence[str] = list(fallback_anchor_order)
    total_slots: Optional[int] = None

    def _normalize_string_sequence(value: object, field: str) -> List[str]:
        if isinstance(value, str) or not isinstance(value, Iterable):
            raise ValueError(f"'{field}' must be an array of strings.")
        return [str(item) for item in value]

    if isinstance(raw, Mapping):
        records_obj = raw["comparisons"] if "comparisons" in raw else raw.get("records")
        if records_obj is None:
            raise ValueError("Baseline payload must include a 'comparisons' array.")
        if "anchor_order" in raw:
            anchor_order = _normalize_string_sequence(raw["anchor_order"], "anchor_order")
        if "total_slots" in raw and raw["total_slots"] is not None:
            try:
                total_slots = int(raw["total_slots"])
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise ValueError("'total_slots' must be an integer if supplied.") from exc
    elif isinstance(raw, Sequence):
        records_obj = raw
    else:
        raise ValueError("Baseline payload must be a JSON object or array.")

    if not isinstance(records_obj, Sequence):
        raise ValueError("'comparisons' must be an array of objects.")

    normalized_records: List[Mapping[str, object]] = []
    for index, record in enumerate(records_obj):
        if not isinstance(record, Mapping):
            raise ValueError(f"Comparison at index {index} is not an object.")
        normalized_records.append(dict(record))

    if not anchor_order:
        raise ValueError("Anchor order cannot be empty.")

    return BaselinePayload(
        records=normalized_records,
        anchor_order=list(anchor_order),
        total_slots=total_slots,
    )


def load_baseline_design(
    pairs_path: Path,
    *,
    anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
) -> Tuple[List[str], List[DesignEntry]]:
    """Load a baseline design from CSV for optimization."""
    if not pairs_path.exists():
        raise FileNotFoundError(f"Pairs CSV not found: {pairs_path}")

    anchors = set(anchor_order)
    students: set[str] = set()
    design: List[DesignEntry] = []

    with pairs_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"essay_a_id", "essay_b_id", "comparison_type"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            field_list = ", ".join(sorted(missing))
            raise ValueError(f"Pairs CSV missing required columns: {field_list}")

        for row in reader:
            candidate = PairCandidate(
                essay_a=row["essay_a_id"],
                essay_b=row["essay_b_id"],
                comparison_type=row["comparison_type"],
            )
            design.append(DesignEntry(candidate))
            for essay in (candidate.essay_a, candidate.essay_b):
                if essay not in anchors:
                    students.add(essay)

    if not design:
        raise ValueError("No comparisons found in CSV.")

    return sorted(students), design


def load_previous_comparisons_from_csv(csv_path: Path) -> List[ComparisonRecord]:
    """Load previous comparison records from a CSV file."""
    if not csv_path.exists():
        raise FileNotFoundError(f"Previous comparisons CSV not found: {csv_path}")

    records: List[ComparisonRecord] = []

    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"essay_a_id", "essay_b_id", "comparison_type"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            field_list = ", ".join(sorted(missing))
            raise ValueError(f"CSV missing required columns: {field_list}")

        for row in reader:
            records.append(
                ComparisonRecord(
                    essay_a_id=row["essay_a_id"],
                    essay_b_id=row["essay_b_id"],
                    comparison_type=row["comparison_type"],
                )
            )

    if not records:
        raise ValueError("No comparisons found in CSV.")

    return records


def load_baseline_from_records(
    records: Iterable[Mapping[str, object]],
    *,
    anchor_order: Sequence[str] = DEFAULT_ANCHOR_ORDER,
) -> Tuple[List[str], List[DesignEntry]]:
    """Load a baseline design from in-memory records."""
    raw_comparisons = load_comparisons_from_records(records)
    anchors = set(anchor_order)
    students: set[str] = set()
    design: List[DesignEntry] = []

    for comparison in raw_comparisons:
        candidate = PairCandidate(
            essay_a=comparison.essay_a_id,
            essay_b=comparison.essay_b_id,
            comparison_type=comparison.comparison_type,
        )
        design.append(DesignEntry(candidate))
        for essay in (candidate.essay_a, candidate.essay_b):
            if essay not in anchors:
                students.add(essay)

    if not design:
        raise ValueError("No comparisons found in records.")

    return sorted(students), design


__all__ = [
    "load_baseline_design",
    "load_baseline_from_records",
    "load_baseline_payload",
    "load_dynamic_spec",
    "load_previous_comparisons_from_csv",
]
