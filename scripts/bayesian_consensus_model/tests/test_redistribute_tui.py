"""Tests for TUI-specific functionality in redistribute_tui.py."""

from __future__ import annotations

from pathlib import Path

from scripts.bayesian_consensus_model.tui.file_drop_handler import extract_paths_from_paste


# ============================================================================
# Path Extraction Tests (Drag-and-Drop / Paste Handling)
# ============================================================================


def test_extract_paths_from_paste_single_quoted_path(tmp_path: Path) -> None:
    """Test extraction of single-quoted path (macOS Terminal drag-drop)."""
    test_file = tmp_path / "test.csv"
    test_file.write_text("dummy")

    # Simulate macOS Terminal drag-drop: '/path/to/file'
    payload = f"'{test_file}'"
    result = extract_paths_from_paste(payload)

    assert len(result) == 1
    assert result[0] == str(test_file)
    # Ensure no quotes remain
    assert not result[0].startswith("'")
    assert not result[0].endswith("'")


def test_extract_paths_from_paste_double_quoted_path(tmp_path: Path) -> None:
    """Test extraction of double-quoted path."""
    test_file = tmp_path / "test.csv"
    test_file.write_text("dummy")

    payload = f'"{test_file}"'
    result = extract_paths_from_paste(payload)

    assert len(result) == 1
    assert result[0] == str(test_file)
    assert not result[0].startswith('"')
    assert not result[0].endswith('"')


def test_extract_paths_from_paste_null_delimited_paths(tmp_path: Path) -> None:
    """Test extraction of null-delimited paths (macOS multi-file drag-drop)."""
    file1 = tmp_path / "file1.csv"
    file2 = tmp_path / "file2.csv"
    file1.write_text("dummy1")
    file2.write_text("dummy2")

    # macOS sends multiple files as: 'file1'\x00'file2'\x00
    payload = f"'{file1}'\x00'{file2}'\x00"
    result = extract_paths_from_paste(payload)

    assert len(result) == 2
    assert str(file1) in result
    assert str(file2) in result
    # Verify no quotes
    for path in result:
        assert not path.startswith("'")
        assert not path.endswith("'")


def test_extract_paths_from_paste_with_spaces(tmp_path: Path) -> None:
    """Test extraction of path with embedded spaces."""
    subdir = tmp_path / "folder with spaces"
    subdir.mkdir()
    test_file = subdir / "file with spaces.csv"
    test_file.write_text("dummy")

    payload = f"'{test_file}'"
    result = extract_paths_from_paste(payload)

    assert len(result) == 1
    assert result[0] == str(test_file)
    assert " " in result[0]  # Path contains spaces
    assert not result[0].startswith("'")


def test_extract_paths_from_paste_mixed_quoting(tmp_path: Path) -> None:
    """Test extraction with mixed quote styles."""
    file1 = tmp_path / "file1.csv"
    file2 = tmp_path / "file2.csv"
    file1.write_text("dummy1")
    file2.write_text("dummy2")

    # Mix single and double quotes
    payload = f'"{file1}" \'{file2}\''
    result = extract_paths_from_paste(payload)

    assert len(result) == 2
    assert str(file1) in result
    assert str(file2) in result


def test_extract_paths_from_paste_nonexistent_path() -> None:
    """Test that nonexistent paths are filtered out."""
    payload = "'/nonexistent/path/to/file.csv'"
    result = extract_paths_from_paste(payload)

    assert len(result) == 0


def test_extract_paths_from_paste_empty_payload() -> None:
    """Test handling of empty paste payload."""
    result = extract_paths_from_paste("")
    assert result == []


def test_extract_paths_from_paste_whitespace_only() -> None:
    """Test handling of whitespace-only payload."""
    result = extract_paths_from_paste("   \t\n  ")
    assert result == []


def test_extract_paths_from_paste_file_uri_prefix(tmp_path: Path) -> None:
    """Test handling of file:// URI prefix (some terminals add this)."""
    test_file = tmp_path / "test.csv"
    test_file.write_text("dummy")

    payload = f"file://{test_file}"
    result = extract_paths_from_paste(payload)

    assert len(result) == 1
    assert result[0] == str(test_file)


def test_extract_paths_from_paste_embedded_null_bytes(tmp_path: Path) -> None:
    """Test handling of embedded null bytes within path segments."""
    test_file = tmp_path / "test.csv"
    test_file.write_text("dummy")

    # Simulate null bytes at beginning/end and within path
    payload = f"\x00'{test_file}'\x00"
    result = extract_paths_from_paste(payload)

    assert len(result) == 1
    assert result[0] == str(test_file)
    # Ensure no null bytes in result
    assert "\x00" not in result[0]


def test_extract_paths_from_paste_complex_macos_payload(tmp_path: Path) -> None:
    """Test realistic macOS drag-drop payload with all quirks."""
    file1 = tmp_path / "session data"
    file1.mkdir()
    actual_file = file1 / "test file.csv"
    actual_file.write_text("dummy")

    # Realistic macOS payload: null-delimited, quoted, with spaces
    payload = f"\x00'{actual_file}'\x00"
    result = extract_paths_from_paste(payload)

    assert len(result) == 1
    assert result[0] == str(actual_file)
    assert not result[0].startswith("'")
    assert not result[0].endswith("'")
    assert "\x00" not in result[0]
