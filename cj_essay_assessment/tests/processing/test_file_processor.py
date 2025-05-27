"""Tests for the File Processor module (file_processor.py).

Covers filename sanitization, text extraction from different formats,
error handling, and metadata generation.
"""

from pathlib import Path
from unittest.mock import MagicMock  # mock_open, patch removed as unused

import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

# Module Functions/Classes to test
from src.cj_essay_assessment.file_processor import (FileReadError,
                                                    UnsupportedFormatError,
                                                    extract_text_from_file,
                                                    generate_base_metadata,
                                                    sanitize_filename)

# --- Tests for sanitize_filename ---


def test_sanitize_filename_basic() -> None:
    """Test basic sanitization."""
    assert (
        sanitize_filename("My Essay Final (Version 2).docx")
        == "My_Essay_Final__Version_2_.docx"
    )
    assert sanitize_filename("a_b-c.d.txt") == "a_b-c.d.txt"
    assert sanitize_filename("!@#$%^&*().pdf") == "__________.pdf"
    assert sanitize_filename("") == ""
    assert sanitize_filename(None) == ""  # type: ignore[arg-type]
    assert sanitize_filename("../path/to/file.txt") == "file.txt"


def test_sanitize_filename_long_name() -> None:
    """Test filename truncation when the name part is too long."""
    long_name = "a" * 300
    extension = ".txt"
    original_filename = long_name + extension
    max_len = 255

    sanitized = sanitize_filename(original_filename)

    assert len(sanitized) <= max_len
    assert sanitized.endswith(extension)
    # Check that the name part was truncated
    expected_name_len = max_len - len(extension)
    assert len(sanitized.split(".")[0]) == expected_name_len
    assert sanitized.startswith("a" * expected_name_len)


def test_sanitize_filename_long_extension() -> None:
    """Test filename truncation when the extension is too long."""
    name = "short_name"
    long_extension = "." + "a" * 300
    original_filename = name + long_extension
    max_len = 255

    # Test Case 1: Long Extension
    expected_sanitized_long_ext = "." + "a" * (max_len - 1)
    assert sanitize_filename(name + long_extension) == expected_sanitized_long_ext

    # Test Case 2: Long Name, Normal Extension
    long_name = "a" * 300
    normal_extension = ".docx"
    expected_sanitized_long_name = (
        "a" * (max_len - len(normal_extension)) + normal_extension
    )
    assert sanitize_filename(long_name + normal_extension) == expected_sanitized_long_name


def test_sanitize_filename_preserves_multiple_dots() -> None:
    """Test that multiple dots before the final extension are handled."""
    assert sanitize_filename("archive.tar.gz") == "archive.tar.gz"
    assert sanitize_filename("my.document.v1.docx") == "my.document.v1.docx"


# --- Tests for extract_text_from_file ---


def test_extract_text_file_not_found(tmp_path: Path) -> None:
    """Test FileReadError is raised when the file doesn't exist."""
    non_existent_path = tmp_path / "nonexistent.txt"
    # original_filename is used in the exception message, keep it
    original_filename = "nonexistent.txt"

    with pytest.raises(FileReadError) as excinfo:
        extract_text_from_file(non_existent_path, original_filename)

    assert "File not found" in str(excinfo.value)
    assert str(non_existent_path) in str(excinfo.value)


def test_extract_text_from_txt_success(tmp_path: Path) -> None:
    """Test successful text extraction from a .txt file."""
    file_content = "This is the content\nof the text file."
    file_path = tmp_path / "test.txt"
    file_path.write_text(file_content, encoding="utf-8")
    original_filename = "test.txt"

    extracted_text = extract_text_from_file(file_path, original_filename)
    assert extracted_text == file_content


def test_extract_text_from_docx_success(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test successful text extraction from a .docx file using mocks."""
    mock_doc = MagicMock()
    mock_para1 = MagicMock()
    mock_para1.text = "Paragraph 1 text."
    mock_para2 = MagicMock()
    mock_para2.text = "Paragraph 2 text."
    mock_para3 = MagicMock()
    mock_para3.text = "  \n  "
    mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]

    mock_docx_document = mocker.patch("src.cj_essay_assessment.file_processor.Document")
    mock_docx_document.return_value = mock_doc

    dummy_docx_path = tmp_path / "test.docx"
    dummy_docx_path.touch()
    original_filename = "test.docx"

    extracted_text = extract_text_from_file(dummy_docx_path, original_filename)

    mock_docx_document.assert_called_once_with(str(dummy_docx_path))
    assert extracted_text == "Paragraph 1 text.\nParagraph 2 text."


# --- NEW TESTS ---


def test_extract_text_pdf_not_implemented(tmp_path: Path) -> None:
    """Test that PDF extraction raises NotImplementedError."""
    pdf_path = tmp_path / "document.pdf"
    pdf_path.touch()
    original_filename = "document.pdf"

    with pytest.raises(NotImplementedError) as excinfo:
        extract_text_from_file(pdf_path, original_filename)
    assert "PDF text extraction not yet implemented" in str(excinfo.value)


def test_extract_text_unsupported_format(tmp_path: Path) -> None:
    """Test that unsupported formats raise FileReadError (wrapping UnsupportedFormatError)."""
    unsupported_path = tmp_path / "image.jpeg"
    unsupported_path.touch()
    original_filename = "image.jpeg"

    with pytest.raises(FileReadError) as excinfo:
        extract_text_from_file(unsupported_path, original_filename)

    assert f"Unable to read JPEG file: {original_filename}" in str(excinfo.value)
    assert isinstance(excinfo.value.original_error, UnsupportedFormatError)


def test_extract_text_docx_read_error(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test FileReadError when docx library raises an exception."""
    docx_path = tmp_path / "corrupted.docx"
    docx_path.touch()
    original_filename = "corrupted.docx"
    simulated_error = ValueError("Invalid DOCX file structure")

    mocker.patch(
        "src.cj_essay_assessment.file_processor.Document",
        side_effect=simulated_error,
    )

    with pytest.raises(FileReadError) as excinfo:
        extract_text_from_file(docx_path, original_filename)

    assert f"Unable to read DOCX file: {original_filename}" in str(excinfo.value)
    assert excinfo.value.original_error == simulated_error


def test_extract_text_txt_read_error(tmp_path: Path, mocker: MockerFixture) -> None:
    """Test FileReadError when reading a txt file raises an exception."""
    txt_path = tmp_path / "unreadable.txt"
    txt_path.touch()
    original_filename = "unreadable.txt"
    simulated_error = OSError("Permission denied")

    mocker.patch("builtins.open", side_effect=simulated_error)

    with pytest.raises(FileReadError) as excinfo:
        extract_text_from_file(txt_path, original_filename)

    assert f"Unable to read TXT file: {original_filename}" in str(excinfo.value)
    assert excinfo.value.original_error == simulated_error


# --- Tests for generate_base_metadata ---


@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        ("Hello world", {"word_count": 2, "character_count": 11}),
        (" SingleWord ", {"word_count": 1, "character_count": 12}),
        ("", {"word_count": 0, "character_count": 0}),
        ("  Multiple   spaces  ", {"word_count": 2, "character_count": 21}),
    ],
)
def test_generate_base_metadata_success(
    input_text: str,
    expected_output: dict[str, int],
) -> None:
    """Test generate_base_metadata with valid string inputs."""
    metadata = generate_base_metadata(input_text)
    assert metadata == expected_output


def test_generate_base_metadata_non_string(caplog: LogCaptureFixture) -> None:
    """Test generate_base_metadata with non-string inputs."""
    assert generate_base_metadata(None) == {"word_count": 0, "character_count": 0}  # type: ignore
    assert generate_base_metadata(123) == {"word_count": 0, "character_count": 0}  # type: ignore
    assert generate_base_metadata([]) == {"word_count": 0, "character_count": 0}  # type: ignore
    assert "generate_base_metadata received non-string input" in caplog.text
