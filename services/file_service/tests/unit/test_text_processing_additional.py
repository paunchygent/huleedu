"""
Additional unit tests for text processing to cover remaining scenarios.

Focuses on exception handling and parse_student_info function
to achieve 90%+ coverage.
"""

from __future__ import annotations

from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.file_service.text_processing import extract_text_from_file, parse_student_info


class TestTextProcessingAdditionalCoverage:
    """Additional tests for text processing edge cases."""

    async def test_decode_exception_handling(self) -> None:
        """Test that decode exceptions are properly handled and wrapped."""
        # Given - Mock bytes that can't be decoded
        file_content: Mock = Mock(spec=bytes)
        file_content.decode.side_effect = UnicodeDecodeError(
            "utf-8", b"", 0, 1, "invalid start byte"
        )
        file_name: str = "corrupt.txt"
        correlation_id: UUID = uuid4()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extract_text_from_file(file_content, file_name, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text_from_file"
        assert "Failed to decode file content" in error_detail.message
        assert error_detail.correlation_id == correlation_id
        assert error_detail.details["file_name"] == file_name

    async def test_generic_exception_handling(self) -> None:
        """Test that unexpected exceptions during decode are handled."""
        # Given - Mock bytes that raise unexpected exception
        file_content: Mock = Mock(spec=bytes)
        file_content.decode.side_effect = RuntimeError("Unexpected error during decode")
        file_name: str = "error.txt"
        correlation_id: UUID = uuid4()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extract_text_from_file(file_content, file_name, correlation_id)

        # Verify error wrapped properly
        error_detail = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text_from_file"
        assert "Failed to decode file content" in error_detail.message
        assert "Unexpected error during decode" in error_detail.message

    async def test_parse_student_info_stub(self) -> None:
        """Test parse_student_info stub implementation."""
        # Given
        text_content: str = """
        Student Name: John Doe
        Email: john.doe@example.com
        
        Essay content here...
        """

        # When
        name, email = await parse_student_info(text_content)

        # Then - Verify stub returns None, None
        assert name is None
        assert email is None

    async def test_parse_student_info_empty_content(self) -> None:
        """Test parse_student_info with empty content."""
        # Given
        text_content: str = ""

        # When
        name, email = await parse_student_info(text_content)

        # Then - Verify stub returns None, None
        assert name is None
        assert email is None

    async def test_parse_student_info_various_formats(self) -> None:
        """Test parse_student_info with various text formats (still returns None)."""
        # Given - Various text formats
        test_cases = [
            "Name: Jane Smith\nEmail: jane@university.edu",
            "STUDENT: Bob Johnson (bob.j@school.org)",
            "Essay by Alice Brown <alice.brown@college.edu>",
            "No student information in this text",
        ]

        # When/Then - All should return None, None (stub implementation)
        for text_content in test_cases:
            name, email = await parse_student_info(text_content)
            assert name is None
            assert email is None