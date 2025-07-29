"""
Unit tests for text processing error handling scenarios.

Focuses on file type validation and encoding error handling
to improve coverage for defensive error paths.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.error_handling import HuleEduError

from services.file_service.text_processing import extract_text_from_file


class TestTextProcessingErrorHandling:
    """Test text processing error handling scenarios."""

    async def test_non_txt_file_rejection_pdf(self) -> None:
        """Test that PDF files are properly rejected with HuleEduError."""
        # Given
        file_content: bytes = b"PDF file content"
        file_name: str = "document.pdf"
        correlation_id: UUID = uuid4()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extract_text_from_file(file_content, file_name, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text_from_file"
        assert "Unsupported file type" in error_detail.message
        assert "Walking skeleton only supports .txt files" in error_detail.message
        assert error_detail.correlation_id == correlation_id
        assert error_detail.details["file_name"] == file_name

    async def test_non_txt_file_rejection_docx(self) -> None:
        """Test that DOCX files are properly rejected with HuleEduError."""
        # Given
        file_content: bytes = b"DOCX file content"
        file_name: str = "essay.docx"
        correlation_id: UUID = uuid4()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extract_text_from_file(file_content, file_name, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text_from_file"
        assert "Unsupported file type" in error_detail.message
        assert error_detail.correlation_id == correlation_id
        assert error_detail.details["file_name"] == file_name

    async def test_non_txt_file_rejection_jpg(self) -> None:
        """Test that JPG files are properly rejected with HuleEduError."""
        # Given
        file_content: bytes = b"JPEG image data"
        file_name: str = "image.jpg"
        correlation_id: UUID = uuid4()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extract_text_from_file(file_content, file_name, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text_from_file"
        assert "Unsupported file type" in error_detail.message
        assert error_detail.correlation_id == correlation_id

    async def test_case_insensitive_file_extension_rejection(self) -> None:
        """Test that file extensions are checked case-insensitively."""
        # Given
        file_content: bytes = b"PDF content"
        file_name: str = "document.PDF"  # Uppercase extension
        correlation_id: UUID = uuid4()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extract_text_from_file(file_content, file_name, correlation_id)

        # Verify error is raised for uppercase extension
        error_detail = exc_info.value.error_detail
        assert "Unsupported file type" in error_detail.message

    async def test_utf8_decoding_with_invalid_bytes_ignored(self) -> None:
        """Test that invalid UTF-8 bytes are ignored per implementation."""
        # Given
        # Create invalid UTF-8 byte sequence mixed with valid text
        invalid_utf8_content: bytes = b"Valid text \xff\xfe\x00\x00 more valid text"
        file_name: str = "test.txt"
        correlation_id: UUID = uuid4()

        # When
        extracted_text: str = await extract_text_from_file(
            invalid_utf8_content, file_name, correlation_id
        )

        # Then - Invalid bytes are ignored, valid text is extracted
        # The implementation uses errors="ignore" so invalid bytes are silently dropped
        assert "Valid text" in extracted_text
        assert "more valid text" in extracted_text
        # Verify the invalid bytes were ignored (no exception raised)

    async def test_successful_txt_file_extraction(self) -> None:
        """Test successful text extraction from valid .txt file."""
        # Given
        file_content: bytes = b"This is a valid UTF-8 text file content."
        file_name: str = "essay.txt"
        correlation_id: UUID = uuid4()

        # When
        extracted_text: str = await extract_text_from_file(
            file_content, file_name, correlation_id
        )

        # Then
        assert extracted_text == "This is a valid UTF-8 text file content."

    async def test_successful_txt_file_extraction_case_insensitive(self) -> None:
        """Test successful extraction with case-insensitive .txt extension."""
        # Given
        file_content: bytes = b"Content from TXT file."
        file_name: str = "document.TXT"  # Uppercase extension should work
        correlation_id: UUID = uuid4()

        # When
        extracted_text: str = await extract_text_from_file(
            file_content, file_name, correlation_id
        )

        # Then
        assert extracted_text == "Content from TXT file."

    async def test_empty_txt_file_extraction(self) -> None:
        """Test extraction from empty .txt file."""
        # Given
        file_content: bytes = b""
        file_name: str = "empty.txt"
        correlation_id: UUID = uuid4()

        # When
        extracted_text: str = await extract_text_from_file(
            file_content, file_name, correlation_id
        )

        # Then
        assert extracted_text == ""

    async def test_utf8_with_special_characters(self) -> None:
        """Test extraction of UTF-8 content with special characters."""
        # Given
        file_content: bytes = "Héllö Wörld! 你好世界 🌍".encode("utf-8")
        file_name: str = "special_chars.txt"
        correlation_id: UUID = uuid4()

        # When
        extracted_text: str = await extract_text_from_file(
            file_content, file_name, correlation_id
        )

        # Then
        assert extracted_text == "Héllö Wörld! 你好世界 🌍"

    async def test_multiline_txt_content(self) -> None:
        """Test extraction of multiline text content."""
        # Given
        content: str = "Line 1\nLine 2\nLine 3\n"
        file_content: bytes = content.encode("utf-8")
        file_name: str = "multiline.txt"
        correlation_id: UUID = uuid4()

        # When
        extracted_text: str = await extract_text_from_file(
            file_content, file_name, correlation_id
        )

        # Then
        assert extracted_text == content