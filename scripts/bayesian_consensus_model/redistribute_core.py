from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

ANCHOR_DISPLAY = {
    "F+1": "SA1701",
    "F+2": "SA1702",
    "E-": "SA1703",
    "E+": "SA1704",
    "D-": "SA1705",
    "D+": "SA1706",
    "C-": "SA1707",
    "C+": "SA1708",
    "B1": "SA1709",
    "B2": "SA1710",
    "A1": "SA1711",
    "A2": "SA1712",
}


class StatusSelector(str, Enum):
    CORE = "core"
    ALL = "all"


@dataclass(frozen=True)
class Comparison:
    pair_id: int
    essay_a_id: str
    essay_b_id: str
    comparison_type: str
    status: str

    @property
    def display_a(self) -> str:
        return ANCHOR_DISPLAY.get(self.essay_a_id, self.essay_a_id)

    @property
    def display_b(self) -> str:
        return ANCHOR_DISPLAY.get(self.essay_b_id, self.essay_b_id)


def read_pairs(path: Path) -> List[Comparison]:
    if not path.exists():
        raise FileNotFoundError(f"Pairs CSV not found: {path}")

    comparisons: List[Comparison] = []
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"pair_id", "essay_a_id", "essay_b_id", "comparison_type", "status"}
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
                    status=row["status"],
                )
            )

    comparisons.sort(key=lambda item: (0 if item.status == "core" else 1, item.pair_id))
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


def select_comparisons(
    comparisons: Sequence[Comparison],
    include_status: StatusSelector,
    total_needed: int,
) -> List[Comparison]:
    if include_status is StatusSelector.CORE:
        pool = [item for item in comparisons if item.status == "core"]
    else:
        pool = list(comparisons)

    if total_needed > len(pool):
        raise ValueError(
            f"Requested {total_needed} comparisons but only {len(pool)} available "
            f"(include_status={include_status.value})."
        )
    return list(pool[:total_needed])


def assign_pairs(
    comparisons: Sequence[Comparison],
    rater_names: Sequence[str],
    per_rater: int,
) -> List[Tuple[str, Comparison]]:
    assignments: List[Tuple[str, Comparison]] = []
    for idx, rater in enumerate(rater_names):
        start = idx * per_rater
        end = start + per_rater
        chunk = comparisons[start:end]
        if len(chunk) != per_rater:
            raise ValueError(
                f"Insufficient comparisons ({len(chunk)}) to assign {per_rater} pairs to {rater}."
            )
        for comparison in chunk:
            assignments.append((rater, comparison))
    return assignments


def write_assignments(
    output_path: Path,
    assignments: Sequence[Tuple[str, Comparison]],
) -> None:
    fieldnames = [
        "rater_name",
        "pair_id",
        "essay_a_id",
        "essay_b_id",
        "essay_a_display",
        "essay_b_display",
        "comparison_type",
        "status",
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
                    "essay_a_display": comparison.display_a,
                    "essay_b_display": comparison.display_b,
                    "comparison_type": comparison.comparison_type,
                    "status": comparison.status,
                }
            )
