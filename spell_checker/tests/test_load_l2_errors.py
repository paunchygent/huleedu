"""
Tests for the load_l2_errors function in the l2_dictionary_loader module.
"""
import os
import pytest # For tmp_path
from src.cj_essay_assessment.spell_checker.l2_dictionary_loader import load_l2_errors

class TestLoadL2Errors:
    """Test suite for the load_l2_errors function."""

    def test_load_l2_errors_successful_absolute_path(self, tmp_path):
        """Test loading L2 errors from a file with an absolute path."""
        # Arrange
        l2_file_content = (
            "errror:error\n"
            "anothr:another\n"
            "teh:the\n"
        )
        l2_file = tmp_path / "test_l2_errors.txt"
        l2_file.write_text(l2_file_content)

        expected_errors = {
            "errror": "error",
            "anothr": "another",
            "teh": "the",
        }

        # Act
        # Test without filtering to isolate loading logic.
        loaded_errors = load_l2_errors(str(l2_file), filter_entries=False)

        # Assert
        assert loaded_errors == expected_errors

    def test_load_l2_errors_file_not_found(self, caplog):
        """Test loading from a non-existent file."""
        # Arrange
        non_existent_file = "path/to/non_existent_l2_errors.txt"

        # Act
        loaded_errors = load_l2_errors(non_existent_file, filter_entries=False)

        # Assert
        assert loaded_errors == {}
        assert f"Error loading L2 errors file: [Errno 2] No such file or directory: '{non_existent_file}'" in caplog.text # Check for specific error log

    def test_load_l2_errors_empty_file(self, tmp_path):
        """Test loading from an empty L2 errors file."""
        # Arrange
        l2_empty_file = tmp_path / "empty_l2.txt"
        l2_empty_file.write_text("")

        # Act
        loaded_errors = load_l2_errors(str(l2_empty_file), filter_entries=False)

        # Assert
        assert loaded_errors == {}

    def test_load_l2_errors_malformed_lines(self, tmp_path):
        """Test loading from a file with malformed lines."""
        # Arrange
        l2_file_content = (
            "good:correction\n"
            "   \n"  # Whitespace only
            "nocolonhere\n"
            ":onlycorrect\n"
            "onlywrong:\n"
            ":\n" # Just a colon
            "s:c\n"  # Single char wrong, should be skipped by load_l2_errors
            "  anothergood:anothercorrection  \n" # With leading/trailing spaces
        )
        l2_file = tmp_path / "malformed_l2.txt"
        l2_file.write_text(l2_file_content)

        expected_errors = {
            "good": "correction",
            "anothergood": "anothercorrection",
            "onlywrong": "", # Added this entry
            # "s": "c" is skipped by the len(wrong) <= 1 check in load_l2_errors
        }

        # Act
        loaded_errors = load_l2_errors(str(l2_file), filter_entries=False)

        # Assert
        assert loaded_errors == expected_errors

    def test_load_l2_errors_relative_path_in_data_subdir(self, tmp_path, monkeypatch, mocker):
        """Test loading with a relative path expected in a 'data' subdirectory."""
        # Arrange
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        l2_file_content = "relative:path\n"
        l2_file = data_dir / "my_l2.txt"
        l2_file.write_text(l2_file_content)

        monkeypatch.chdir(tmp_path)

        def mock_exists_logic_data_subdir(path_being_checked):
            if path_being_checked == "my_l2.txt":
                return False
            expected_data_path = os.path.join("data", "my_l2.txt")
            if path_being_checked == expected_data_path:
                return True
            if os.path.isdir(path_being_checked):
                return True # Allow actual directories to exist for path joining
            return False # Default to False for anything else
        mocker.patch("os.path.exists", side_effect=mock_exists_logic_data_subdir)

        expected_errors = {"relative": "path"}

        # Act
        loaded_errors = load_l2_errors("my_l2.txt", filter_entries=False)

        # Assert
        assert loaded_errors == expected_errors

    def test_load_l2_errors_relative_path_direct_exists(self, tmp_path, monkeypatch, mocker):
        """Test loading with a relative path that exists directly (not in 'data' subdir)."""
        # Arrange
        l2_file_content = "direct:hit\n"
        l2_file = tmp_path / "direct_l2.txt"
        l2_file.write_text(l2_file_content)

        monkeypatch.chdir(tmp_path)

        def mock_exists_logic_direct(path_being_checked):
            if path_being_checked == "direct_l2.txt":
                return True
            if os.path.isdir(path_being_checked):
                return True # Allow actual directories to exist
            return False
        mocker.patch("os.path.exists", side_effect=mock_exists_logic_direct)

        expected_errors = {"direct": "hit"}

        # Act
        loaded_errors = load_l2_errors("direct_l2.txt", filter_entries=False)

        # Assert
        assert loaded_errors == expected_errors

    def test_load_l2_errors_with_filtering_enabled_and_available(self, tmp_path, mocker):
        """Test load_l2_errors when filter_entries is True and filter is available."""
        # Arrange
        l2_file_content = "raw:data\nfilterme:please\n"
        l2_file = tmp_path / "l2_to_filter.txt"
        l2_file.write_text(l2_file_content)

        original_errors = {"raw": "data", "filterme": "please"}
        mock_filtered_errors = {"raw": "data"}

        mocker.patch("src.cj_essay_assessment.spell_checker.l2_dictionary_loader.FILTER_AVAILABLE", True)
        mock_filter_func = mocker.patch("src.cj_essay_assessment.spell_checker.l2_dictionary_loader.filter_l2_entries", return_value=mock_filtered_errors)

        # Act
        loaded_errors = load_l2_errors(str(l2_file), filter_entries=True)

        # Assert
        mock_filter_func.assert_called_once_with(original_errors)
        assert loaded_errors == mock_filtered_errors

    def test_load_l2_errors_with_filtering_explicitly_disabled(self, tmp_path, mocker):
        """Test load_l2_errors when filter_entries is explicitly False."""
        # Arrange
        l2_file_content = "raw:data\nfilterme:please\n"
        l2_file = tmp_path / "l2_not_filtered.txt"
        l2_file.write_text(l2_file_content)

        expected_raw_errors = {"raw": "data", "filterme": "please"}
        mock_filter_func = mocker.patch("src.cj_essay_assessment.spell_checker.l2_dictionary_loader.filter_l2_entries")

        # Act
        loaded_errors = load_l2_errors(str(l2_file), filter_entries=False)

        # Assert
        mock_filter_func.assert_not_called()
        assert loaded_errors == expected_raw_errors

    def test_load_l2_errors_filter_module_not_available(self, tmp_path, mocker, caplog):
        """Test load_l2_errors when FILTER_AVAILABLE is False."""
        # Arrange
        l2_file_content = "raw:data\nfilterme:please\n"
        l2_file = tmp_path / "l2_filter_unavailable.txt"
        l2_file.write_text(l2_file_content)

        expected_raw_errors = {"raw": "data", "filterme": "please"}

        mocker.patch("src.cj_essay_assessment.spell_checker.l2_dictionary_loader.FILTER_AVAILABLE", False)
        # Need to import the module to spy on its attribute that gets reassigned
        from src.cj_essay_assessment.spell_checker import l2_dictionary_loader
        spy_filter_func = mocker.spy(l2_dictionary_loader, "filter_l2_entries")

        # Act
        loaded_errors = load_l2_errors(str(l2_file), filter_entries=True)

        # Assert
        assert spy_filter_func.call_count == 0 # The no-op lambda is not called due to FILTER_AVAILABLE being False
        assert loaded_errors == expected_raw_errors
        assert "After filtering:" not in caplog.text

    # ... more tests will be added here
