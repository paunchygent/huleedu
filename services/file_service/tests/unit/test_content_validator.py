"""
Unit tests for File Service content validator.

Tests the FileContentValidator business logic to ensure proper validation
of file content according to business rules and requirements.
"""

from __future__ import annotations

import uuid

import pytest
from common_core.error_enums import FileValidationErrorCode
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError

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
        # Arrange
        correlation_id = uuid.uuid4()
        valid_text = (
            "This is a well-structured essay with "
            "sufficient content and meaningful structure for processing "
            "that meets all validation requirements."
        )

        # Act & Assert - Should not raise any exception for valid content
        await validator.validate_content(valid_text, "valid_essay.txt", correlation_id)

    async def test_validate_empty_string(self, validator: FileContentValidator) -> None:
        """Test rejection of completely empty content."""
        # Arrange
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_content("", "empty.txt", correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.EMPTY_CONTENT
        assert "empty.txt" in error_detail.message
        assert error_detail.correlation_id == correlation_id

    async def test_validate_none_content(self, validator: FileContentValidator) -> None:
        """Test handling of None content (defensive programming)."""
        # Arrange
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_content(None, "none.txt", correlation_id)  # type: ignore[arg-type]

        # Verify error details
        assert exc_info.value.error_detail.error_code == FileValidationErrorCode.EMPTY_CONTENT

    async def test_validate_whitespace_only(self, validator: FileContentValidator) -> None:
        """Test rejection of content containing only whitespace."""
        # Arrange
        whitespace_content = "   \n\t   \r\n   "
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_content(whitespace_content, "whitespace.txt", correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.EMPTY_CONTENT
        assert "whitespace.txt" in error_detail.message
        assert error_detail.correlation_id == correlation_id

    async def test_validate_content_too_short(self, validator: FileContentValidator) -> None:
        """Test rejection of content below minimum length."""
        # Arrange
        short_content = "Too short"  # Less than 50 characters
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_content(short_content, "short.txt", correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert "short.txt" in error_detail.message
        assert "actual: 9" in error_detail.message
        assert "minimum: 50" in error_detail.message
        assert error_detail.correlation_id == correlation_id

    async def test_validate_content_too_long(self, validator: FileContentValidator) -> None:
        """Test rejection of content exceeding maximum length."""
        # Arrange
        long_content = "A" * 50001  # Exceeds 50000 character limit (default max_length)
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_content(long_content, "long.txt", correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.CONTENT_TOO_LONG
        assert "long.txt" in error_detail.message
        assert "50001 characters" in error_detail.message
        assert "not exceed 50000 characters" in error_detail.message
        assert error_detail.correlation_id == correlation_id

    async def test_validate_exact_minimum_length(self, validator: FileContentValidator) -> None:
        """Test validation of content at exact minimum length boundary."""
        # Arrange
        exact_min_content = "A" * 50  # Exactly 50 characters
        correlation_id = uuid.uuid4()

        # Act - should not raise exception
        await validator.validate_content(exact_min_content, "exact_min.txt", correlation_id)

    async def test_validate_exact_maximum_length(self, validator: FileContentValidator) -> None:
        """Test validation of content at exact maximum length boundary."""
        # Arrange
        exact_max_content = "A" * 50000  # Exactly 50000 characters (default max_length)
        correlation_id = uuid.uuid4()

        # Act - should not raise exception
        await validator.validate_content(exact_max_content, "exact_max.txt", correlation_id)

    async def test_validate_one_below_minimum(self, validator: FileContentValidator) -> None:
        """Test rejection of content one character below minimum."""
        # Arrange
        below_min_content = "A" * 49  # One less than 50
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_content(below_min_content, "below_min.txt", correlation_id)

        # Verify error details
        assert exc_info.value.error_detail.error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert exc_info.value.error_detail.correlation_id == correlation_id

    async def test_validate_one_above_maximum(self, validator: FileContentValidator) -> None:
        """Test rejection of content one character above maximum."""
        # Arrange
        above_max_content = "A" * 50001  # One more than 50000 (default max_length)
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await validator.validate_content(above_max_content, "above_max.txt", correlation_id)

        # Verify error details
        assert exc_info.value.error_detail.error_code == FileValidationErrorCode.CONTENT_TOO_LONG
        assert exc_info.value.error_detail.correlation_id == correlation_id

    async def test_validate_content_with_whitespace_trimming(
        self,
        validator: FileContentValidator,
    ) -> None:
        """Test that content length is calculated after trimming whitespace."""
        # Arrange - 50 characters plus surrounding whitespace
        content_with_whitespace = "   " + "A" * 50 + "   \n\t"
        correlation_id = uuid.uuid4()

        # Act - should not raise exception (trimmed length is exactly 50)
        await validator.validate_content(content_with_whitespace, "trimmed.txt", correlation_id)

    async def test_custom_length_limits(self, custom_validator: FileContentValidator) -> None:
        """Test validator with custom minimum and maximum length limits."""
        # Arrange - Test content that passes custom limits but would fail standard limits
        content = (
            "Short valid"  # 11 characters - valid for custom (10-100)
            # but invalid for standard (50-50000)
        )
        correlation_id = uuid.uuid4()

        # Act - should not raise exception for custom validator
        await custom_validator.validate_content(content, "custom.txt", correlation_id)

    async def test_custom_limits_too_short(self, custom_validator: FileContentValidator) -> None:
        """Test custom validator rejects content below its minimum."""
        # Arrange
        content = "Too short"  # 9 characters - below custom minimum of 10
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await custom_validator.validate_content(content, "custom_short.txt", correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.CONTENT_TOO_SHORT
        assert "at least 10 characters" in error_detail.message
        assert error_detail.correlation_id == correlation_id

    async def test_custom_limits_too_long(self, custom_validator: FileContentValidator) -> None:
        """Test custom validator rejects content above its maximum."""
        # Arrange
        content = "A" * 101  # 101 characters - above custom maximum of 100
        correlation_id = uuid.uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await custom_validator.validate_content(content, "custom_long.txt", correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.CONTENT_TOO_LONG
        assert "not exceed 100 characters" in error_detail.message
        assert error_detail.correlation_id == correlation_id

    async def test_real_world_essay_content(self, validator: FileContentValidator) -> None:
        """Test validation with realistic essay content."""
        # Arrange
        essay_content = """
        The Impact of Technology on Modern Education

        Technology has fundamentally transformed the landscape of education in the 21st century.
        From online learning platforms to interactive whiteboards, digital tools have revolutionized
        how students learn and teachers instruct. This transformation brings both opportunities
        and challenges that educators must navigate carefully.

        The advantages of educational technology are numerous and significant...
        """
        correlation_id = uuid.uuid4()

        # Act - should not raise exception
        await validator.validate_content(essay_content, "essay.txt", correlation_id)

    async def test_filename_inclusion_in_error_messages(
        self,
        validator: FileContentValidator,
    ) -> None:
        """Test that filenames are properly included in error messages for debugging."""
        test_cases = [
            ("", "empty_file.docx", FileValidationErrorCode.EMPTY_CONTENT),
            ("Short", "brief_essay.pdf", FileValidationErrorCode.CONTENT_TOO_SHORT),
            ("A" * 50001, "massive_essay.txt", FileValidationErrorCode.CONTENT_TOO_LONG),
        ]

        for content, filename, expected_error in test_cases:
            # Arrange
            correlation_id = uuid.uuid4()

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await validator.validate_content(content, filename, correlation_id)

            # Verify error details
            error_detail = exc_info.value.error_detail
            assert error_detail.error_code == expected_error
            assert filename in error_detail.message
            assert error_detail.correlation_id == correlation_id

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
