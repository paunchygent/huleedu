"""
Unit tests for the L2 Correction Filter module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from services.spellchecker_service.spell_logic.l2_filter import (
    L2CorrectionFilter,
    create_filtered_l2_dictionary,
    filter_l2_entries,
)


class TestL2CorrectionFilter:
    """Tests for the L2CorrectionFilter class."""

    @pytest.fixture
    def correction_filter(self) -> L2CorrectionFilter:
        """Fixture to provide an L2CorrectionFilter instance."""
        return L2CorrectionFilter(logger=MagicMock())

    @pytest.mark.parametrize(
        "error, correction, expected",
        [
            ("cat", "cats", True),
            ("box", "boxes", True),
            ("cats", "cat", True),
            ("boxes", "box", True),
            ("city", "cities", True),
            ("cities", "city", True),
            ("apple", "apples", True),
            ("peach", "peaches", True),
            ("fly", "flies", True),
            ("community", "communities", True),
        ],
    )
    def test_is_pluralization_change_true_cases(
        self,
        correction_filter: L2CorrectionFilter,
        error: str,
        correction: str,
        expected: bool,
    ) -> None:
        """Test cases where is_pluralization_change should return True."""
        assert correction_filter.is_pluralization_change(error, correction) == expected

    @pytest.mark.parametrize(
        "error, correction, expected",
        [
            ("ca", "cat", False),  # Too short
            ("apple", "apply", False),
            ("run", "ran", False),
            ("go", "goes", False),  # Technically plural-like but often more grammatical
            ("teacher", "teach", False),
            ("beautiful", "beauty", False),
            ("s", "", False),  # Too short
            ("es", "", False),  # Too short
            ("y", "ies", False),  # Too short
        ],
    )
    def test_is_pluralization_change_false_cases(
        self,
        correction_filter: L2CorrectionFilter,
        error: str,
        correction: str,
        expected: bool,
    ) -> None:
        """Test cases where is_pluralization_change should return False."""
        assert correction_filter.is_pluralization_change(error, correction) == expected

    @pytest.mark.parametrize(
        "error, correction, expected",
        [
            ("aple", "apple", True),
            ("bananna", "banana", True),
            ("accomodate", "accommodate", True),
        ],
    )
    def test_is_valid_correction_true_cases(
        self,
        correction_filter: L2CorrectionFilter,
        error: str,
        correction: str,
        expected: bool,
    ) -> None:
        """Test cases where is_valid_correction should return True."""
        assert correction_filter.is_valid_correction(error, correction) == expected

    @pytest.mark.parametrize(
        "error, correction, expected",
        [
            ("cat", "cats", False),  # Pluralization
            ("bx", "box", False),  # Too short error
            ("apple", "ap", False),  # Too short correction
            (
                "go",
                "goes",
                False,
            ),  # Pluralization-like, handled by is_pluralization_change
        ],
    )
    def test_is_valid_correction_false_cases(
        self,
        correction_filter: L2CorrectionFilter,
        error: str,
        correction: str,
        expected: bool,
    ) -> None:
        """Test cases where is_valid_correction should return False."""
        assert correction_filter.is_valid_correction(error, correction) == expected


def test_filter_l2_entries_empty_input() -> None:
    """Test filter_l2_entries with an empty dictionary."""
    assert filter_l2_entries({}) == {}


def test_filter_l2_entries_invalid_input_type() -> None:
    """Test filter_l2_entries with invalid input type."""
    mock_logger = MagicMock()
    assert filter_l2_entries(None, logger=mock_logger) == {}  # type: ignore
    mock_logger.warning.assert_called_once_with("Invalid input: expected a dictionary")


def test_filter_l2_entries_valid_and_invalid() -> None:
    """Test filter_l2_entries with a mix of valid and invalid corrections."""
    l2_errors = {
        "aple": "apple",  # Valid
        "cat": "cats",  # Invalid (plural)
        "runn": "run",  # Valid
        "go": "goes",  # Invalid (plural-like)
        "bx": "box",  # Invalid (short)
    }
    expected_filtered = {"aple": "apple", "runn": "run"}
    assert filter_l2_entries(l2_errors) == expected_filtered


def test_filter_l2_entries_non_string_input() -> None:
    """Test filter_l2_entries with non-string entries."""
    mock_logger = MagicMock()
    mixed_input = {"good": "correction", 123: "string_value", "another": "valid"}  # type: ignore
    result = filter_l2_entries(mixed_input, logger=mock_logger)  # type: ignore
    assert result == {"good": "correction", "another": "valid"}
    mock_logger.info.assert_any_call("Skipping non-string entry: 123 -> string_value")


def test_filter_l2_entries_all_valid() -> None:
    """Test filter_l2_entries where all entries should pass."""
    l2_errors = {"aple": "apple", "bananna": "banana", "acommodate": "accommodate"}
    assert filter_l2_entries(l2_errors) == l2_errors


def test_filter_l2_entries_all_invalid() -> None:
    """Test filter_l2_entries where all entries should be filtered out."""
    l2_errors = {"cat": "cats", "go": "goes", "bx": "box"}
    assert filter_l2_entries(l2_errors) == {}


def test_create_filtered_l2_dictionary_success(tmp_path: Path) -> None:
    """Test successful creation of the filtered L2 dictionary file."""
    output_file = tmp_path / "filtered_l2_test.txt"
    l2_errors = {"aple": "apple", "bananna": "banana", "cat": "cats"}  # Mix
    expected_content_lines = sorted(["aple:apple\n", "bananna:banana\n"])

    assert create_filtered_l2_dictionary(l2_errors, output_file) is True
    assert output_file.exists()
    with output_file.open("r", encoding="utf-8") as f:
        content = sorted(f.readlines())
    assert content == expected_content_lines


def test_create_filtered_l2_dictionary_empty_input(tmp_path: Path) -> None:
    """Test create_filtered_l2_dictionary with empty input."""
    mock_logger = MagicMock()
    output_file = tmp_path / "test_filtered.txt"
    assert not create_filtered_l2_dictionary({}, output_file, logger=mock_logger)
    assert not output_file.exists()
    mock_logger.warning.assert_called_once_with(
        "No corrections provided to create_filtered_l2_dictionary",
    )


def test_create_filtered_l2_dictionary_no_valid_entries(tmp_path: Path) -> None:
    """Test create_filtered_l2_dictionary when all entries are filtered out."""
    mock_logger = MagicMock()
    output_file = tmp_path / "test_no_valid.txt"
    # These entries will be filtered out (short words, pluralization)
    invalid_entries = {"a": "an", "cats": "cat", "is": "are"}
    assert not create_filtered_l2_dictionary(invalid_entries, output_file, logger=mock_logger)
    assert not output_file.exists()
    mock_logger.warning.assert_called_once_with("No valid corrections after filtering")


def test_create_filtered_l2_dictionary_os_error_parent_dir(tmp_path: Path, mocker: Any) -> None:
    """Test create_filtered_l2_dictionary with OSError during parent directory creation."""
    mock_logger = MagicMock()
    # Create a file where a directory is expected to cause OSError
    non_dir_path = tmp_path / "actually_a_file.txt"
    non_dir_path.touch()
    output_file = non_dir_path / "filtered_l2_test.txt"  # Path a/file/b

    l2_errors = {"aple": "apple"}
    mocker.patch.object(Path, "mkdir", side_effect=OSError("Test OS Error mkdir"))

    # We need to mock Path.parent.mkdir specifically if it's called directly.
    # More robustly, if we expect `output_path.parent.mkdir` to fail:
    mock_parent = mocker.MagicMock(spec=Path)
    mock_parent.mkdir.side_effect = OSError("Cannot create parent dir")

    # To make Path(output_file).parent return our mock
    # This is tricky as Path() is a class. We might need to mock Path.mkdir
    # itself if it's a class method
    # or the instance method if `output_path.parent` is the object calling mkdir.
    # Simpler: Mock the specific `output_path.parent.mkdir` call path if possible
    # or broader `Path.mkdir`

    # For this test, let's assume the mkdir within the function will be hit by
    # the mocker.patch above.

    assert create_filtered_l2_dictionary(l2_errors, output_file, logger=mock_logger) is False
    assert not output_file.exists()
    mock_logger.error.assert_called_once()
    call_args, _ = mock_logger.error.call_args
    assert "Failed to create directory" in call_args[0]


def test_create_filtered_l2_dictionary_os_error_writing_file(tmp_path: Path, mocker: Any) -> None:
    """Test create_filtered_l2_dictionary with OSError during file writing."""
    mock_logger = MagicMock()
    output_file = tmp_path / "filtered_l2_test.txt"
    l2_errors = {"aple": "apple"}

    # Mock open to raise OSError
    mocker.patch("pathlib.Path.open", side_effect=OSError("Test OS Error writing"))

    assert create_filtered_l2_dictionary(l2_errors, output_file, logger=mock_logger) is False
    # The file might be created before open fails, or not, depending on implementation details
    # For this test, we mainly care about the False return and log.
    mock_logger.error.assert_called_once()
    call_args, _ = mock_logger.error.call_args
    assert "Failed to write to" in call_args[0]
