from __future__ import annotations

import csv
from pathlib import Path
from typing import List, Sequence

from ..d_optimal_optimizer import DesignEntry


def write_design(design: Sequence[DesignEntry], output_path: Path) -> None:
    """Persist a design to CSV using the standard comparison schema."""
    fieldnames = ["pair_id", "essay_a_id", "essay_b_id", "comparison_type"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for idx, entry in enumerate(design, start=1):
            writer.writerow(
                {
                    "pair_id": idx,
                    "essay_a_id": entry.candidate.essay_a,
                    "essay_b_id": entry.candidate.essay_b,
                    "comparison_type": entry.candidate.comparison_type,
                }
            )


def load_students_from_csv(csv_path: Path) -> List[str]:
    """Load student IDs from CSV, trying common column names (case-insensitive)."""
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no headers")

        field_map = {name.lower(): name for name in reader.fieldnames}

        for column in ["essay_id", "student_id", "id"]:
            if column in field_map:
                original = field_map[column]
                handle.seek(0)
                reader = csv.DictReader(handle)
                students = [
                    row[original].strip() for row in reader if row.get(original, "").strip()
                ]
                if not students:
                    raise ValueError(f"CSV column '{original}' is empty")
                return students

        raise ValueError(
            "CSV must have one of: essay_id, student_id, or id column (case-insensitive). "
            f"Found: {', '.join(reader.fieldnames)}"
        )


__all__ = [
    "load_students_from_csv",
    "write_design",
]
