"""
Unit tests for StrategyBasedTextExtractor.

Tests the Strategy pattern implementation for multi-format text extraction.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from common_core.error_enums import FileValidationErrorCode
from huleedu_service_libs.error_handling import HuleEduError

from services.file_service.implementations.text_extractor_impl import StrategyBasedTextExtractor


class TestStrategyBasedTextExtractor:
    """Test StrategyBasedTextExtractor implementation."""

    async def test_txt_extraction_success(self) -> None:
        """Test successful text extraction from .txt files."""
        # Given
        file_content: bytes = b"Test file content"
        file_name: str = "test.txt"
        correlation_id: UUID = uuid4()
        expected_text: str = "Test file content"

        # Create extractor with mocked strategy
        extractor = StrategyBasedTextExtractor()
        mock_strategy = AsyncMock()
        mock_strategy.extract.return_value = expected_text
        extractor._strategies[".txt"] = mock_strategy

        # When
        result: str = await extractor.extract_text(file_content, file_name, correlation_id)

        # Then
        assert result == expected_text
        mock_strategy.extract.assert_called_once_with(file_content, file_name, correlation_id)

    async def test_docx_extraction_success(self) -> None:
        """Test successful text extraction from .docx files."""
        # Given
        file_content: bytes = b"DOCX binary content"
        file_name: str = "essay.docx"
        correlation_id: UUID = uuid4()
        expected_text: str = "Extracted Word document text"

        # Create extractor with mocked strategy
        extractor = StrategyBasedTextExtractor()
        mock_strategy = AsyncMock()
        mock_strategy.extract.return_value = expected_text
        extractor._strategies[".docx"] = mock_strategy

        # When
        result: str = await extractor.extract_text(file_content, file_name, correlation_id)

        # Then
        assert result == expected_text
        mock_strategy.extract.assert_called_once_with(file_content, file_name, correlation_id)

    async def test_pdf_extraction_success(self) -> None:
        """Test successful text extraction from .pdf files."""
        # Given
        file_content: bytes = b"PDF binary content"
        file_name: str = "document.pdf"
        correlation_id: UUID = uuid4()
        expected_text: str = "Extracted PDF text"

        # Create extractor with mocked strategy
        extractor = StrategyBasedTextExtractor()
        mock_strategy = AsyncMock()
        mock_strategy.extract.return_value = expected_text
        extractor._strategies[".pdf"] = mock_strategy

        # When
        result: str = await extractor.extract_text(file_content, file_name, correlation_id)

        # Then
        assert result == expected_text
        mock_strategy.extract.assert_called_once_with(file_content, file_name, correlation_id)

    async def test_unsupported_file_type_error(self) -> None:
        """Test error handling for unsupported file types."""
        # Given
        file_content: bytes = b"Excel content"
        file_name: str = "spreadsheet.xlsx"
        correlation_id: UUID = uuid4()

        # Create extractor
        extractor = StrategyBasedTextExtractor()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extractor.extract_text(file_content, file_name, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.TEXT_EXTRACTION_FAILED
        assert "Unsupported file type '.xlsx'" in error_detail.message
        assert "Supported types: .txt, .docx, .pdf" in error_detail.message
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text"
        assert error_detail.correlation_id == correlation_id

    async def test_file_without_extension_error(self) -> None:
        """Test error handling for files without extensions."""
        # Given
        file_content: bytes = b"No extension content"
        file_name: str = "README"
        correlation_id: UUID = uuid4()

        # Create extractor
        extractor = StrategyBasedTextExtractor()

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extractor.extract_text(file_content, file_name, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.TEXT_EXTRACTION_FAILED
        assert "File has no extension" in error_detail.message
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text"
        assert error_detail.correlation_id == correlation_id

    async def test_encrypted_pdf_error_propagation(self) -> None:
        """Test that encrypted PDF errors are propagated correctly."""
        # Given
        file_content: bytes = b"Encrypted PDF"
        file_name: str = "encrypted.pdf"
        correlation_id: UUID = uuid4()

        # Create extractor with mocked strategy that raises encrypted error
        extractor = StrategyBasedTextExtractor()
        mock_strategy = AsyncMock()

        # Create a mock HuleEduError for encrypted file
        mock_error_detail = MagicMock()
        mock_error_detail.error_code = FileValidationErrorCode.ENCRYPTED_FILE_UNSUPPORTED
        mock_error = HuleEduError(mock_error_detail)

        mock_strategy.extract.side_effect = mock_error
        extractor._strategies[".pdf"] = mock_strategy

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extractor.extract_text(file_content, file_name, correlation_id)

        # Verify the encrypted error is propagated as-is
        assert (
            exc_info.value.error_detail.error_code
            == FileValidationErrorCode.ENCRYPTED_FILE_UNSUPPORTED
        )

    async def test_generic_extraction_error_handling(self) -> None:
        """Test handling of unexpected errors during extraction."""
        # Given
        file_content: bytes = b"Corrupt file"
        file_name: str = "corrupt.docx"
        correlation_id: UUID = uuid4()

        # Create extractor with mocked strategy that raises generic error
        extractor = StrategyBasedTextExtractor()
        mock_strategy = AsyncMock()
        mock_strategy.extract.side_effect = RuntimeError("Unexpected parsing error")
        extractor._strategies[".docx"] = mock_strategy

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extractor.extract_text(file_content, file_name, correlation_id)

        # Verify error is wrapped properly
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.TEXT_EXTRACTION_FAILED
        assert "Failed to extract text: Unexpected parsing error" in error_detail.message
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text"
        assert error_detail.correlation_id == correlation_id

    async def test_case_insensitive_file_extension(self) -> None:
        """Test that file extensions are handled case-insensitively."""
        # Given
        file_content: bytes = b"PDF content"
        file_name: str = "DOCUMENT.PDF"  # Uppercase extension
        correlation_id: UUID = uuid4()
        expected_text: str = "Extracted text"

        # Create extractor with mocked strategy
        extractor = StrategyBasedTextExtractor()
        mock_strategy = AsyncMock()
        mock_strategy.extract.return_value = expected_text
        extractor._strategies[".pdf"] = mock_strategy

        # When
        result: str = await extractor.extract_text(file_content, file_name, correlation_id)

        # Then
        assert result == expected_text
        mock_strategy.extract.assert_called_once_with(file_content, file_name, correlation_id)
