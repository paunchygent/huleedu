"""
Unit tests for StrategyBasedTextExtractor.

Tests the Strategy pattern implementation for multi-format text extraction.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from common_core.error_enums import FileValidationErrorCode
from huleedu_service_libs.error_handling import HuleEduError

from services.file_service.implementations.extraction_strategies import (
    DocxExtractionStrategy,
    ExtractionStrategy,
    PdfExtractionStrategy, 
    TxtExtractionStrategy,
)
from services.file_service.implementations.text_extractor_impl import StrategyBasedTextExtractor


class TestStrategyBasedTextExtractor:
    """Test StrategyBasedTextExtractor implementation."""

    def _create_extractor_with_mock_strategies(self) -> tuple[StrategyBasedTextExtractor, dict[str, Any]]:
        """Helper to create extractor with mocked strategies."""
        mock_txt_strategy = AsyncMock(spec=TxtExtractionStrategy)
        mock_docx_strategy = AsyncMock(spec=DocxExtractionStrategy)
        mock_pdf_strategy = AsyncMock(spec=PdfExtractionStrategy)
        
        # Store mocks separately for test access
        mocks = {
            ".txt": mock_txt_strategy,
            ".docx": mock_docx_strategy,
            ".pdf": mock_pdf_strategy,
        }
        
        # Type-annotated dict for the extractor
        strategies: dict[str, ExtractionStrategy] = {
            ".txt": mock_txt_strategy,
            ".docx": mock_docx_strategy,
            ".pdf": mock_pdf_strategy,
        }
        
        extractor = StrategyBasedTextExtractor(validators=[], strategies=strategies)
        return extractor, mocks

    async def test_txt_extraction_success(self) -> None:
        """Test successful text extraction from .txt files."""
        # Given
        file_content: bytes = b"Test file content"
        file_name: str = "test.txt"
        correlation_id: UUID = uuid4()
        expected_text: str = "Test file content"

        # Create extractor with mocked strategies
        extractor, mocks = self._create_extractor_with_mock_strategies()
        mocks[".txt"].extract.return_value = expected_text

        # When
        result: str = await extractor.extract_text(file_content, file_name, correlation_id)

        # Then
        assert result == expected_text
        mocks[".txt"].extract.assert_called_once_with(file_content, file_name, correlation_id)

    async def test_docx_extraction_success(self) -> None:
        """Test successful text extraction from .docx files."""
        # Given
        file_content: bytes = b"DOCX binary content"
        file_name: str = "essay.docx"
        correlation_id: UUID = uuid4()
        expected_text: str = "Extracted Word document text"

        # Create extractor with mocked strategies
        extractor, mocks = self._create_extractor_with_mock_strategies()
        mocks[".docx"].extract.return_value = expected_text

        # When
        result: str = await extractor.extract_text(file_content, file_name, correlation_id)

        # Then
        assert result == expected_text
        mocks[".docx"].extract.assert_called_once_with(file_content, file_name, correlation_id)

    async def test_pdf_extraction_success(self) -> None:
        """Test successful text extraction from .pdf files."""
        # Given
        file_content: bytes = b"PDF binary content"
        file_name: str = "document.pdf"
        correlation_id: UUID = uuid4()
        expected_text: str = "Extracted PDF text"

        # Create extractor with mocked strategies
        extractor, mocks = self._create_extractor_with_mock_strategies()
        mocks[".pdf"].extract.return_value = expected_text

        # When
        result: str = await extractor.extract_text(file_content, file_name, correlation_id)

        # Then
        assert result == expected_text
        mocks[".pdf"].extract.assert_called_once_with(file_content, file_name, correlation_id)

    async def test_unsupported_file_type_error(self) -> None:
        """Test error handling for unsupported file types."""
        # Given
        file_content: bytes = b"Excel content"
        file_name: str = "spreadsheet.xlsx"
        correlation_id: UUID = uuid4()

        # Create extractor with limited strategies
        extractor = StrategyBasedTextExtractor(validators=[], strategies={})

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extractor.extract_text(file_content, file_name, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.TEXT_EXTRACTION_FAILED
        assert "No extraction strategy found for file type '.xlsx'" in error_detail.message
        assert error_detail.service == "file_service"
        assert error_detail.operation == "select_strategy"
        assert error_detail.correlation_id == correlation_id

    async def test_file_without_extension_error(self) -> None:
        """Test error handling for files without extensions."""
        # Given
        file_content: bytes = b"No extension content"
        file_name: str = "README"
        correlation_id: UUID = uuid4()

        # Create extractor
        extractor = StrategyBasedTextExtractor(validators=[], strategies={})

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extractor.extract_text(file_content, file_name, correlation_id)

        # Verify error details
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.TEXT_EXTRACTION_FAILED
        assert "No extraction strategy found for file type ''" in error_detail.message
        assert error_detail.service == "file_service"
        assert error_detail.operation == "select_strategy"
        assert error_detail.correlation_id == correlation_id

    async def test_encrypted_pdf_error_propagation(self) -> None:
        """Test that encrypted PDF errors are propagated correctly."""
        # Given
        file_content: bytes = b"Encrypted PDF"
        file_name: str = "encrypted.pdf"
        correlation_id: UUID = uuid4()

        # Create extractor with mocked strategy that raises encrypted error
        mock_strategy = AsyncMock()
        
        # Create a mock HuleEduError for encrypted file
        mock_error_detail = MagicMock()
        mock_error_detail.error_code = FileValidationErrorCode.ENCRYPTED_FILE_UNSUPPORTED
        mock_error = HuleEduError(mock_error_detail)
        
        mock_strategy.extract.side_effect = mock_error
        
        extractor = StrategyBasedTextExtractor(
            validators=[],
            strategies={".pdf": mock_strategy}
        )

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
        mock_strategy = AsyncMock()
        mock_strategy.extract.side_effect = RuntimeError("Unexpected parsing error")
        
        extractor = StrategyBasedTextExtractor(
            validators=[],
            strategies={".docx": mock_strategy}
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await extractor.extract_text(file_content, file_name, correlation_id)

        # Verify error is wrapped properly
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.TEXT_EXTRACTION_FAILED
        assert "Unexpected parsing error" in error_detail.message
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
        mock_strategy = AsyncMock()
        mock_strategy.extract.return_value = expected_text
        
        extractor = StrategyBasedTextExtractor(
            validators=[],
            strategies={".pdf": mock_strategy}
        )

        # When
        result: str = await extractor.extract_text(file_content, file_name, correlation_id)

        # Then
        assert result == expected_text
        mock_strategy.extract.assert_called_once_with(file_content, file_name, correlation_id)

    async def test_validators_are_called_before_extraction(self) -> None:
        """Test that all validators are called before extraction."""
        # Given
        file_content: bytes = b"Test content"
        file_name: str = "test.txt"
        correlation_id: UUID = uuid4()
        
        # Create mock validators
        mock_validator1 = AsyncMock()
        mock_validator2 = AsyncMock()
        
        # Create mock strategy
        mock_strategy = AsyncMock()
        mock_strategy.extract.return_value = "Extracted text"
        
        extractor = StrategyBasedTextExtractor(
            validators=[mock_validator1, mock_validator2],
            strategies={".txt": mock_strategy}
        )
        
        # When
        await extractor.extract_text(file_content, file_name, correlation_id)
        
        # Then
        mock_validator1.validate.assert_called_once_with(file_name, file_content, correlation_id)
        mock_validator2.validate.assert_called_once_with(file_name, file_content, correlation_id)
        mock_strategy.extract.assert_called_once()

    async def test_extraction_stops_if_validator_fails(self) -> None:
        """Test that extraction doesn't proceed if validation fails."""
        # Given
        file_content: bytes = b"Test content"
        file_name: str = "~$test.txt"  # Temporary file
        correlation_id: UUID = uuid4()
        
        # Create mock validator that raises error
        mock_validator = AsyncMock()
        mock_error = HuleEduError(MagicMock())
        mock_validator.validate.side_effect = mock_error
        
        # Create mock strategy that should not be called
        mock_strategy = AsyncMock()
        
        extractor = StrategyBasedTextExtractor(
            validators=[mock_validator],
            strategies={".txt": mock_strategy}
        )
        
        # When/Then
        with pytest.raises(HuleEduError):
            await extractor.extract_text(file_content, file_name, correlation_id)
        
        # Strategy should not have been called
        mock_strategy.extract.assert_not_called()