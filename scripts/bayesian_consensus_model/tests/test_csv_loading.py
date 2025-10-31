"""Tests for CSV student loading functionality in redistribute_tui.

Tests cover case-insensitive column matching, error handling,
and whitespace normalization for the _load_students_from_csv helper.
"""

import csv
from pathlib import Path

import pytest

from scripts.bayesian_consensus_model.redistribute_tui import _load_students_from_csv


def test_load_csv_with_lowercase_essay_id(tmp_path: Path) -> None:
    """Valid CSV with lowercase 'essay_id' column."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["essay_id", "other_col"])
        writer.writerows([["JA24", "data1"], ["II24", "data2"], ["ES24", "data3"]])

    students = _load_students_from_csv(csv_path)

    assert students == ["JA24", "II24", "ES24"]


def test_load_csv_with_mixed_case_essay_id(tmp_path: Path) -> None:
    """Case-insensitive matching for 'Essay_ID' column."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Essay_ID", "Grade"])
        writer.writerows([["EK24", "A"], ["ER24", "B"]])

    students = _load_students_from_csv(csv_path)

    assert students == ["EK24", "ER24"]


def test_load_csv_with_uppercase_essay_id(tmp_path: Path) -> None:
    """Case-insensitive matching for 'ESSAY_ID' column."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ESSAY_ID"])
        writer.writerows([["TK24"], ["SN24"]])

    students = _load_students_from_csv(csv_path)

    assert students == ["TK24", "SN24"]


def test_load_csv_with_student_id_column(tmp_path: Path) -> None:
    """Fallback to 'student_id' column when 'essay_id' not present."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["student_id", "name"])
        writer.writerows([["HJ17", "Student A"], ["SA24", "Student B"]])

    students = _load_students_from_csv(csv_path)

    assert students == ["HJ17", "SA24"]


def test_load_csv_with_id_column(tmp_path: Path) -> None:
    """Fallback to 'id' column when other columns not present."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "score"])
        writer.writerows([["LW24", "85"], ["JF24", "92"]])

    students = _load_students_from_csv(csv_path)

    assert students == ["LW24", "JF24"]


def test_load_csv_missing_required_columns(tmp_path: Path) -> None:
    """Error when CSV has no matching column, shows available columns."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "grade", "score"])
        writer.writerows([["Alice", "A", "95"]])

    with pytest.raises(ValueError, match=r"CSV must have one of"):
        _load_students_from_csv(csv_path)

    # Verify error message includes available columns
    try:
        _load_students_from_csv(csv_path)
    except ValueError as exc:
        assert "name, grade, score" in str(exc)


def test_load_csv_empty_column_values(tmp_path: Path) -> None:
    """Error when matching column exists but all values are empty."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["essay_id", "other"])
        writer.writerows([["", "data1"], ["  ", "data2"], ["", "data3"]])

    with pytest.raises(ValueError, match=r"CSV column 'essay_id' is empty"):
        _load_students_from_csv(csv_path)


def test_load_csv_missing_file(tmp_path: Path) -> None:
    """FileNotFoundError when CSV file doesn't exist."""
    csv_path = tmp_path / "nonexistent.csv"

    with pytest.raises(FileNotFoundError):
        _load_students_from_csv(csv_path)


def test_load_csv_whitespace_handling(tmp_path: Path) -> None:
    """Values with leading/trailing whitespace are properly stripped."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["essay_id"])
        writer.writerows([["  JP24  "], [" ER24"], ["TK24 "]])

    students = _load_students_from_csv(csv_path)

    assert students == ["JP24", "ER24", "TK24"]


def test_load_csv_empty_file_no_headers(tmp_path: Path) -> None:
    """Error when CSV file is empty or has no headers."""
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("")

    with pytest.raises(ValueError, match=r"CSV file is empty or has no headers"):
        _load_students_from_csv(csv_path)


def test_load_csv_skips_empty_rows(tmp_path: Path) -> None:
    """Empty rows (all whitespace) are skipped, not included in results."""
    csv_path = tmp_path / "students.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["essay_id"])
        writer.writerows([["JA24"], [""], ["II24"], ["  "], ["ES24"]])

    students = _load_students_from_csv(csv_path)

    # Only non-empty values should be included
    assert students == ["JA24", "II24", "ES24"]
