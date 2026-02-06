"""Dataset loading utilities for IELTS essay scoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class EssayRecord:
    """Single IELTS essay record."""

    record_id: str
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


@dataclass(frozen=True)
class PreSplitDataset:
    """Dataset loaded with a predefined train/test split."""

    dataset: EssayDataset
    train_records: list[EssayRecord]
    test_records: list[EssayRecord]


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
    for row_index, (_, row) in enumerate(frame.iterrows()):
        component_scores = {
            name: _coerce_float(row.get(name))
            for name in OPTIONAL_COMPONENTS
            if name in frame.columns
        }
        task_type = str(row.get("Task_Type", ""))
        question = str(row.get("Question", ""))
        essay = str(row.get("Essay", ""))
        overall = _require_float(row.get("Overall"), field_name="Overall")
        record_id = _make_record_id(
            source_key="ielts",
            row_index=row_index,
            task_type=task_type,
            question=question,
            essay=essay,
            overall=overall,
        )
        records.append(
            EssayRecord(
                record_id=record_id,
                task_type=task_type,
                question=question,
                essay=essay,
                overall=overall,
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
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _require_float(value: object, *, field_name: str) -> float:
    """Convert required numeric values and fail fast on invalid input."""

    coerced = _coerce_float(value)
    if coerced is None:
        raise ValueError(f"Dataset contains invalid numeric value for {field_name!r}: {value!r}")
    return coerced


ELLIPSE_REQUIRED_COLUMNS = {"full_text", "prompt", "Overall"}
ELLIPSE_SCORE_COLUMNS = [
    "Overall",
    "Cohesion",
    "Syntax",
    "Vocabulary",
    "Phraseology",
    "Grammar",
    "Conventions",
]


def load_ellipse_train_test_dataset(
    train_path: Path,
    test_path: Path,
    *,
    excluded_prompts: set[str] | None = None,
) -> PreSplitDataset:
    """Load the ELLIPSE dataset from pre-split train/test CSVs.

    Args:
        train_path: CSV file path for the train split.
        test_path: CSV file path for the test split.
        excluded_prompts: Optional set of prompt names to drop entirely from both splits.

    Returns:
        PreSplitDataset containing the combined dataset and split-specific record lists.

    Raises:
        FileNotFoundError: If either split path does not exist.
        ValueError: If required columns are missing or split leakage is detected.
    """

    if not train_path.exists():
        raise FileNotFoundError(f"Train dataset not found at {train_path}")
    if not test_path.exists():
        raise FileNotFoundError(f"Test dataset not found at {test_path}")

    train_frame = pd.read_csv(train_path, dtype=str, keep_default_na=False)
    test_frame = pd.read_csv(test_path, dtype=str, keep_default_na=False)

    missing_train = ELLIPSE_REQUIRED_COLUMNS - set(train_frame.columns)
    missing_test = ELLIPSE_REQUIRED_COLUMNS - set(test_frame.columns)
    if missing_train:
        raise ValueError(f"ELLIPSE train dataset missing required columns: {sorted(missing_train)}")
    if missing_test:
        raise ValueError(f"ELLIPSE test dataset missing required columns: {sorted(missing_test)}")

    excluded_prompts = excluded_prompts or set()
    if excluded_prompts:
        train_frame = train_frame[~train_frame["prompt"].isin(excluded_prompts)]
        test_frame = test_frame[~test_frame["prompt"].isin(excluded_prompts)]

    train_records = _load_ellipse_records(train_frame, source_key="ellipse_train")
    test_records = _load_ellipse_records(test_frame, source_key="ellipse_test")

    train_essays = {record.essay for record in train_records}
    overlap = [record for record in test_records if record.essay in train_essays]
    if overlap:
        raise ValueError(
            "ELLIPSE train/test split leakage detected: "
            f"{len(overlap)} test records share identical essay text with train."
        )

    dataset = EssayDataset(records=train_records + test_records)
    return PreSplitDataset(
        dataset=dataset,
        train_records=train_records,
        test_records=test_records,
    )


def _load_ellipse_records(frame: pd.DataFrame, *, source_key: str) -> list[EssayRecord]:
    frame = frame.dropna(subset=["full_text", "Overall", "prompt"])
    if frame.empty:
        raise ValueError("ELLIPSE dataset contains no valid rows after filtering.")

    records: list[EssayRecord] = []
    for row_index, (_, row) in enumerate(frame.iterrows()):
        component_scores: dict[str, float | None] = {}
        for name in ELLIPSE_SCORE_COLUMNS:
            if name not in frame.columns:
                continue
            component_scores[name] = _coerce_float(row.get(name))

        overall_value = component_scores.get("Overall")
        if overall_value is None:
            raise ValueError("ELLIPSE dataset contains rows with missing Overall score.")

        task_type = str(row.get("task", ""))
        question = str(row.get("prompt", ""))
        essay = str(row.get("full_text", ""))
        overall = _require_float(overall_value, field_name="Overall")
        record_id = _make_record_id(
            source_key=source_key,
            row_index=row_index,
            task_type=task_type,
            question=question,
            essay=essay,
            overall=overall,
        )
        records.append(
            EssayRecord(
                record_id=record_id,
                task_type=task_type,
                question=question,
                essay=essay,
                overall=overall,
                component_scores=component_scores,
            )
        )

    return records


def _make_record_id(
    *,
    source_key: str,
    row_index: int,
    task_type: str,
    question: str,
    essay: str,
    overall: float,
) -> str:
    """Return a stable per-row record identifier.

    Requirements:
    - Must be unique even when content is duplicated (e.g., copied essays).
    - Must be stable for the same dataset file (feature store reuse uses dataset SHA256).
    """

    import hashlib

    hasher = hashlib.sha256()
    hasher.update(source_key.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(str(row_index).encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(task_type.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(question.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(essay.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(f"{overall:.3f}".encode("utf-8"))
    return hasher.hexdigest()
