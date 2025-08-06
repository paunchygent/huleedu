"""Unit tests for whitelist implementation."""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from services.spellchecker_service.implementations.whitelist_impl import DefaultWhitelist


class TestDefaultWhitelist:
    """Test cases for DefaultWhitelist implementation."""

    def test_whitelist_protocol_compliance(self) -> None:
        """Test that DefaultWhitelist implements WhitelistProtocol."""
        settings = MagicMock()
        settings.DATA_DIR = "/fake/path"

        with patch("pathlib.Path.exists", return_value=False):
            whitelist = DefaultWhitelist(settings)

        # Check protocol compliance (structural check, not isinstance)
        assert hasattr(whitelist, "is_whitelisted")
        assert callable(whitelist.is_whitelisted)
        # Verify method signature by calling it
        result = whitelist.is_whitelisted("test")
        assert isinstance(result, bool)

    def test_loads_whitelist_from_file(self) -> None:
        """Test whitelist loads entries from file."""
        settings = MagicMock()
        settings.DATA_DIR = "/fake/path"

        # Mock file content
        file_content = "taylor\nswift\nponyboy\nminecraft\n"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=file_content)):
                whitelist = DefaultWhitelist(settings)

        # Verify loaded entries
        assert whitelist.is_whitelisted("Taylor")
        assert whitelist.is_whitelisted("SWIFT")
        assert whitelist.is_whitelisted("ponyboy")
        assert whitelist.is_whitelisted("Minecraft")

    def test_case_insensitive_matching(self) -> None:
        """Test that matching is case-insensitive."""
        settings = MagicMock()
        settings.DATA_DIR = "/fake/path"

        file_content = "Stockholm\n"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=file_content)):
                whitelist = DefaultWhitelist(settings)

        # All case variations should match
        assert whitelist.is_whitelisted("stockholm")
        assert whitelist.is_whitelisted("STOCKHOLM")
        assert whitelist.is_whitelisted("Stockholm")
        assert whitelist.is_whitelisted("StOcKhOlM")

    def test_handles_missing_file_gracefully(self) -> None:
        """Test that missing whitelist file doesn't crash."""
        settings = MagicMock()
        settings.DATA_DIR = "/fake/path"

        with patch("pathlib.Path.exists", return_value=False):
            whitelist = DefaultWhitelist(settings)

        # Should have empty whitelist
        assert not whitelist.is_whitelisted("anything")
        assert len(whitelist.whitelist) == 0

    def test_handles_file_read_error_gracefully(self) -> None:
        """Test that file read errors don't crash the service."""
        settings = MagicMock()
        settings.DATA_DIR = "/fake/path"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", side_effect=IOError("Read error")):
                whitelist = DefaultWhitelist(settings)

        # Should have empty whitelist
        assert not whitelist.is_whitelisted("anything")
        assert len(whitelist.whitelist) == 0

    def test_strips_whitespace_from_entries(self) -> None:
        """Test that whitespace is properly stripped."""
        settings = MagicMock()
        settings.DATA_DIR = "/fake/path"

        # File with various whitespace
        file_content = "  taylor  \n\nswift\n  \n  ponyboy\n"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=file_content)):
                whitelist = DefaultWhitelist(settings)

        # Should match without whitespace
        assert whitelist.is_whitelisted("taylor")
        assert whitelist.is_whitelisted("swift")
        assert whitelist.is_whitelisted("ponyboy")
        # Empty lines should be ignored
        assert len(whitelist.whitelist) == 3

    def test_memory_efficient_storage(self) -> None:
        """Test that whitelist uses set for O(1) lookups."""
        settings = MagicMock()
        settings.DATA_DIR = "/fake/path"

        with patch("pathlib.Path.exists", return_value=False):
            whitelist = DefaultWhitelist(settings)

        # Should use set for storage
        assert isinstance(whitelist.whitelist, set)

    @pytest.mark.parametrize(
        "word,expected",
        [
            ("Taylor", True),
            ("Swift", True),
            ("Ponyboy", True),
            ("Minecraft", True),
            ("misspelled", False),
            ("unknownword", False),
            ("", False),
        ],
    )
    def test_common_names_detection(self, word: str, expected: bool) -> None:
        """Test detection of common proper names."""
        settings = MagicMock()
        settings.DATA_DIR = "/fake/path"

        file_content = "taylor\nswift\nponyboy\nminecraft\n"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=file_content)):
                whitelist = DefaultWhitelist(settings)

        assert whitelist.is_whitelisted(word) == expected
