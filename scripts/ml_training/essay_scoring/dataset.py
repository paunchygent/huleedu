"""Dataset loading utilities for IELTS essay scoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class EssayRecord:
    """Single IELTS essay record."""

    task_type: str
    question: str
    essay: str
    overall: float
    component_scores: dict[str, float | None]


@dataclass(frozen=True)
class EssayDataset:
    """Collection of IELTS essay records."""

    records: list[EssayRecord]

    @property
    def essays(self) -> list[str]:
        """Return essay texts."""

        return [record.essay for record in self.records]

    @property
    def questions(self) -> list[str]:
        """Return essay prompts/questions."""

        return [record.question for record in self.records]

    @property
    def labels(self) -> list[float]:
        """Return overall band labels."""

        return [record.overall for record in self.records]

    @property
    def task_types(self) -> list[str]:
        """Return task type identifiers."""

        return [record.task_type for record in self.records]


REQUIRED_COLUMNS = {
    "Task_Type",
    "Question",
    "Essay",
    "Overall",
}

OPTIONAL_COMPONENTS = [
    "Task_Response",
    "Coherence_Cohesion",
    "Lexical_Resource",
    "Range_Accuracy",
]


def load_ielts_dataset(path: Path) -> EssayDataset:
    """Load the IELTS dataset with validation.

    Args:
        path: CSV file path to the IELTS dataset.

    Returns:
        Parsed EssayDataset instance.

    Raises:
        FileNotFoundError: If the dataset path does not exist.
        ValueError: If required columns are missing or no valid rows remain.
    """

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at {path}")

    frame = pd.read_csv(path)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {sorted(missing)}")

    frame = frame.dropna(subset=["Essay", "Overall", "Question"])
    if frame.empty:
        raise ValueError("Dataset contains no valid rows after filtering.")

    records: list[EssayRecord] = []
    for _, row in frame.iterrows():
        component_scores = {
            name: _coerce_float(row.get(name))
            for name in OPTIONAL_COMPONENTS
            if name in frame.columns
        }
        records.append(
            EssayRecord(
                task_type=str(row.get("Task_Type", "")),
                question=str(row.get("Question", "")),
                essay=str(row.get("Essay", "")),
                overall=float(row.get("Overall")),
                component_scores=component_scores,
            )
        )

    return EssayDataset(records=records)


def _coerce_float(value: object) -> float | None:
    """Convert values to float when possible.

    Args:
        value: Raw value from the dataset.

    Returns:
        Float value or None if missing/invalid.
    """

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
