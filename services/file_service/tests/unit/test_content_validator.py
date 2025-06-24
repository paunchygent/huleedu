"""
Unit tests for File Service content validator.

Tests the FileContentValidator business logic to ensure proper validation
of file content according to business rules and requirements.
"""

from __future__ import annotations

import pytest

from common_core.error_enums import FileValidationErrorCode
from services.file_service.content_validator import FileContentValidator


class TestFileContentValidator:
    """Test suite for FileContentValidator business logic."""

    @pytest.fixture
    def validator(self) -> FileContentValidator:
        """Create a standard validator instance for testing."""
        return FileContentValidator(min_length=50, max_length=1000)

    @pytest.fixture
    def custom_validator(self) -> FileContentValidator:
        """Create a validator with custom limits for testing edge cases."""
        return FileContentValidator(min_length=10, max_length=100)

    async def test_validate_valid_content(self, validator: FileContentValidator) -> None:
        """Test validation of content that meets all requirements."""
        valid_text = (
            "This is a well-structured essay with "
            "sufficient content and meaningful structure for processing "
            "that meets all validation requirements."
        )

        result = await validator.validate_content(valid_text, "valid_essay.txt")

        assert result.is_valid is True
        assert result.error_code is None
        assert result.error_message is None

    async def test_validate_empty_string(self, validator: FileContentValidator) -> None:
        """Test rejection of completely empty content."""
        result = await validator.validate_content("", "empty.txt")

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.EMPTY_CONTENT
        assert result.error_message is not None
        assert "empty.txt" in result.error_message
        assert "no readable text content" in result.error_message

    async def test_validate_none_content(self, validator: FileContentValidator) -> None:
        """Test handling of None content (defensive programming)."""
        result = await validator.validate_content(None, "none.txt")  # type: ignore[arg-type]

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.EMPTY_CONTENT

    async def test_validate_whitespace_only(self, validator: FileContentValidator) -> None:
        """Test rejection of content containing only whitespace."""
        whitespace_content = "   \n\t   \r\n   "

        result = await validator.validate_content(whitespace_content, "whitespace.txt")

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.EMPTY_CONTENT
        assert result.error_message is not None
        assert "whitespace.txt" in result.error_message

    async def test_validate_content_too_short(self, validator: FileContentValidator) -> None:
        """Test rejection of content below minimum length."""
        short_content = "Too short"  # Less than 50 characters

        result = await validator.validate_content(short_content, "short.txt")

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert result.error_message is not None
        assert "short.txt" in result.error_message
        assert "9 characters" in result.error_message
        assert "at least 50 characters" in result.error_message

    async def test_validate_content_too_long(self, validator: FileContentValidator) -> None:
        """Test rejection of content exceeding maximum length."""
        long_content = "A" * 1001  # Exceeds 1000 character limit

        result = await validator.validate_content(long_content, "long.txt")

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.CONTENT_TOO_LONG
        assert result.error_message is not None
        assert "long.txt" in result.error_message
        assert "1001 characters" in result.error_message
        assert "not exceed 1000 characters" in result.error_message

    async def test_validate_exact_minimum_length(self, validator: FileContentValidator) -> None:
        """Test validation of content at exact minimum length boundary."""
        exact_min_content = "A" * 50  # Exactly 50 characters

        result = await validator.validate_content(exact_min_content, "exact_min.txt")

        assert result.is_valid is True

    async def test_validate_exact_maximum_length(self, validator: FileContentValidator) -> None:
        """Test validation of content at exact maximum length boundary."""
        exact_max_content = "A" * 1000  # Exactly 1000 characters

        result = await validator.validate_content(exact_max_content, "exact_max.txt")

        assert result.is_valid is True

    async def test_validate_one_below_minimum(self, validator: FileContentValidator) -> None:
        """Test rejection of content one character below minimum."""
        below_min_content = "A" * 49  # One less than 50

        result = await validator.validate_content(below_min_content, "below_min.txt")

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.CONTENT_TOO_SHORT

    async def test_validate_one_above_maximum(self, validator: FileContentValidator) -> None:
        """Test rejection of content one character above maximum."""
        above_max_content = "A" * 1001  # One more than 1000

        result = await validator.validate_content(above_max_content, "above_max.txt")

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.CONTENT_TOO_LONG

    async def test_validate_content_with_whitespace_trimming(
        self,
        validator: FileContentValidator,
    ) -> None:
        """Test that content length is calculated after trimming whitespace."""
        # 50 characters plus surrounding whitespace
        content_with_whitespace = "   " + "A" * 50 + "   \n\t"

        result = await validator.validate_content(content_with_whitespace, "trimmed.txt")

        assert result.is_valid is True  # Should pass because trimmed length is exactly 50

    async def test_custom_length_limits(self, custom_validator: FileContentValidator) -> None:
        """Test validator with custom minimum and maximum length limits."""
        # Test content that passes custom limits but would fail standard limits
        content = (
            "Short valid"  # 11 characters - valid for custom (10-100)
            # but invalid for standard (50-1000)
        )

        result = await custom_validator.validate_content(content, "custom.txt")

        assert result.is_valid is True

    async def test_custom_limits_too_short(self, custom_validator: FileContentValidator) -> None:
        """Test custom validator rejects content below its minimum."""
        content = "Too short"  # 9 characters - below custom minimum of 10

        result = await custom_validator.validate_content(content, "custom_short.txt")

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert result.error_message is not None
        assert "at least 10 characters" in result.error_message

    async def test_custom_limits_too_long(self, custom_validator: FileContentValidator) -> None:
        """Test custom validator rejects content above its maximum."""
        content = "A" * 101  # 101 characters - above custom maximum of 100

        result = await custom_validator.validate_content(content, "custom_long.txt")

        assert result.is_valid is False
        assert result.error_code == FileValidationErrorCode.CONTENT_TOO_LONG
        assert result.error_message is not None
        assert "not exceed 100 characters" in result.error_message

    async def test_real_world_essay_content(self, validator: FileContentValidator) -> None:
        """Test validation with realistic essay content."""
        essay_content = """
        The Impact of Technology on Modern Education

        Technology has fundamentally transformed the landscape of education in the 21st century.
        From online learning platforms to interactive whiteboards, digital tools have revolutionized
        how students learn and teachers instruct. This transformation brings both opportunities
        and challenges that educators must navigate carefully.

        The advantages of educational technology are numerous and significant...
        """

        result = await validator.validate_content(essay_content, "essay.txt")

        assert result.is_valid is True

    async def test_filename_inclusion_in_error_messages(
        self,
        validator: FileContentValidator,
    ) -> None:
        """Test that filenames are properly included in error messages for debugging."""
        test_cases = [
            ("", "empty_file.docx", FileValidationErrorCode.EMPTY_CONTENT),
            ("Short", "brief_essay.pdf", FileValidationErrorCode.CONTENT_TOO_SHORT),
            ("A" * 1001, "massive_essay.txt", FileValidationErrorCode.CONTENT_TOO_LONG),
        ]

        for content, filename, expected_error in test_cases:
            result = await validator.validate_content(content, filename)

            assert result.is_valid is False
            assert result.error_code == expected_error
            assert result.error_message is not None
            assert filename in result.error_message

    async def test_validator_initialization_defaults(self) -> None:
        """Test that validator initializes with correct default values."""
        validator = FileContentValidator()

        assert validator.min_length == 50
        assert validator.max_length == 50000

    async def test_validator_initialization_custom_values(self) -> None:
        """Test that validator accepts custom initialization values."""
        validator = FileContentValidator(min_length=25, max_length=2000)

        assert validator.min_length == 25
        assert validator.max_length == 2000
