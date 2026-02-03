"""Tests for dataset loaders."""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.ml_training.essay_scoring.dataset import load_ielts_dataset


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_load_ielts_dataset_preserves_exact_duplicates_and_assigns_unique_record_ids(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "dataset.csv"
    rows = [
        {"Task_Type": "1", "Question": "Q1", "Essay": "Same essay.", "Overall": "6.0"},
        {"Task_Type": "1", "Question": "Q1", "Essay": "Same essay.", "Overall": "6.0"},
    ]
    _write_rows(dataset_path, rows)

    dataset = load_ielts_dataset(dataset_path)
    assert len(dataset.records) == 2
    assert dataset.records[0].essay == dataset.records[1].essay
    assert dataset.records[0].record_id != dataset.records[1].record_id

    dataset_again = load_ielts_dataset(dataset_path)
    assert [record.record_id for record in dataset_again.records] == [
        record.record_id for record in dataset.records
    ]
