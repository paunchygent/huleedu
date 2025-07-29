"""
Unit tests for individual extraction strategies.

Tests each strategy implementation in isolation with proper mocking
of external dependencies and comprehensive error scenario coverage.
"""

from __future__ import annotations

from typing import Callable
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from common_core.error_enums import FileValidationErrorCode
from huleedu_service_libs.error_handling import HuleEduError

from services.file_service.implementations.extraction_strategies import (
    DocxExtractionStrategy,
    PdfExtractionStrategy,
    TxtExtractionStrategy,
)


class TestTxtExtractionStrategy:
    """Test TxtExtractionStrategy implementation."""

    async def test_extract_valid_utf8_content(self) -> None:
        """Test successful extraction of valid UTF-8 text content."""
        # Given
        strategy = TxtExtractionStrategy()
        file_content: bytes = b"This is a test essay with valid UTF-8 content."
        file_name: str = "essay.txt"
        correlation_id: UUID = uuid4()

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == "This is a test essay with valid UTF-8 content."

    async def test_extract_empty_content(self) -> None:
        """Test extraction of empty file content."""
        # Given
        strategy = TxtExtractionStrategy()
        file_content: bytes = b""
        file_name: str = "empty.txt"
        correlation_id: UUID = uuid4()

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == ""

    async def test_extract_invalid_utf8_with_error_handling(self) -> None:
        """Test extraction with invalid UTF-8 bytes uses error handling."""
        # Given
        strategy = TxtExtractionStrategy()
        file_content: bytes = b"Valid text \xff\xfe invalid bytes more text"
        file_name: str = "mixed.txt"
        correlation_id: UUID = uuid4()

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert "Valid text" in result
        assert "more text" in result
        # Invalid bytes should be ignored due to errors="ignore"

    async def test_extract_with_special_characters(self) -> None:
        """Test extraction with Unicode special characters."""
        # Given
        strategy = TxtExtractionStrategy()
        file_content: bytes = "Essay with émoji 🎓 and ñañá".encode("utf-8")
        file_name: str = "unicode.txt"
        correlation_id: UUID = uuid4()

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == "Essay with émoji 🎓 and ñañá"

    async def test_extract_large_content(self) -> None:
        """Test extraction of large text content."""
        # Given
        strategy = TxtExtractionStrategy()
        large_content = "A" * 10000  # 10KB of text
        file_content: bytes = large_content.encode("utf-8")
        file_name: str = "large.txt"
        correlation_id: UUID = uuid4()

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == large_content
        assert len(result) == 10000


class TestDocxExtractionStrategy:
    """Test DocxExtractionStrategy implementation."""

    @patch("services.file_service.implementations.extraction_strategies.docx")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_successful_docx(
        self, mock_to_thread: AsyncMock, mock_docx: Mock
    ) -> None:
        """Test successful DOCX text extraction."""
        # Given
        strategy = DocxExtractionStrategy()
        file_content: bytes = b"DOCX binary content"
        file_name: str = "essay.docx"
        correlation_id: UUID = uuid4()

        # Mock document structure
        mock_paragraph1 = Mock()
        mock_paragraph1.text = "First paragraph content"
        mock_paragraph2 = Mock()
        mock_paragraph2.text = "Second paragraph content"
        mock_paragraph3 = Mock()
        mock_paragraph3.text = ""  # Empty paragraph should be filtered

        mock_document = Mock()
        mock_document.paragraphs = [mock_paragraph1, mock_paragraph2, mock_paragraph3]
        mock_docx.Document.return_value = mock_document

        # Mock asyncio.to_thread to call the sync function directly
        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == "First paragraph content\nSecond paragraph content"
        mock_docx.Document.assert_called_once()
        mock_to_thread.assert_called_once()

    @patch("services.file_service.implementations.extraction_strategies.docx")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_empty_docx(self, mock_to_thread: AsyncMock, mock_docx: Mock) -> None:
        """Test extraction from DOCX with no content."""
        # Given
        strategy = DocxExtractionStrategy()
        file_content: bytes = b"Empty DOCX"
        file_name: str = "empty.docx"
        correlation_id: UUID = uuid4()

        # Mock empty document
        mock_document = Mock()
        mock_document.paragraphs = []
        mock_docx.Document.return_value = mock_document

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == ""

    @patch("services.file_service.implementations.extraction_strategies.docx")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_docx_parsing_error(
        self, mock_to_thread: AsyncMock, mock_docx: Mock
    ) -> None:
        """Test error handling when DOCX parsing fails."""
        # Given
        strategy = DocxExtractionStrategy()
        file_content: bytes = b"Corrupt DOCX"
        file_name: str = "corrupt.docx"
        correlation_id: UUID = uuid4()

        # Mock document parsing error
        mock_docx.Document.side_effect = Exception("Invalid DOCX format")

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When/Then
        with pytest.raises(Exception, match="Invalid DOCX format"):
            await strategy.extract(file_content, file_name, correlation_id)

    @patch("services.file_service.implementations.extraction_strategies.docx")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_docx_whitespace_filtering(
        self, mock_to_thread: AsyncMock, mock_docx: Mock
    ) -> None:
        """Test that paragraphs with only whitespace are filtered out."""
        # Given
        strategy = DocxExtractionStrategy()
        file_content: bytes = b"DOCX with whitespace"
        file_name: str = "whitespace.docx"
        correlation_id: UUID = uuid4()

        # Mock document with mixed content
        paragraphs = [
            Mock(text="Valid content"),
            Mock(text="   "),  # Only spaces - should be filtered
            Mock(text="Another valid line"),
            Mock(text=""),  # Empty - should be filtered
        ]

        mock_document = Mock()
        mock_document.paragraphs = paragraphs
        mock_docx.Document.return_value = mock_document

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == "Valid content\nAnother valid line"


class TestPdfExtractionStrategy:
    """Test PdfExtractionStrategy implementation."""

    @patch("services.file_service.implementations.extraction_strategies.PdfReader")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_successful_pdf(
        self, mock_to_thread: AsyncMock, mock_pdf_reader: Mock
    ) -> None:
        """Test successful PDF text extraction."""
        # Given
        strategy = PdfExtractionStrategy()
        file_content: bytes = b"PDF binary content"
        file_name: str = "document.pdf"
        correlation_id: UUID = uuid4()

        # Mock PDF reader and pages
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "First page content"
        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Second page content"
        mock_page3 = Mock()
        mock_page3.extract_text.return_value = "   "  # Empty page should be filtered

        mock_reader = Mock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [mock_page1, mock_page2, mock_page3]
        mock_pdf_reader.return_value = mock_reader

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == "First page content\nSecond page content"
        mock_pdf_reader.assert_called_once()

    @patch("services.file_service.implementations.extraction_strategies.PdfReader")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_encrypted_pdf_error(
        self, mock_to_thread: AsyncMock, mock_pdf_reader: Mock
    ) -> None:
        """Test error handling for encrypted PDF files."""
        # Given
        strategy = PdfExtractionStrategy()
        file_content: bytes = b"Encrypted PDF"
        file_name: str = "encrypted.pdf"
        correlation_id: UUID = uuid4()

        # Mock encrypted PDF reader
        mock_reader = Mock()
        mock_reader.is_encrypted = True
        mock_pdf_reader.return_value = mock_reader

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await strategy.extract(file_content, file_name, correlation_id)

        # Verify it's the encrypted file error
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == FileValidationErrorCode.ENCRYPTED_FILE_UNSUPPORTED
        assert error_detail.service == "file_service"
        assert error_detail.operation == "extract_text"
        assert error_detail.correlation_id == correlation_id

    @patch("services.file_service.implementations.extraction_strategies.PdfReader")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_empty_pdf(
        self, mock_to_thread: AsyncMock, mock_pdf_reader: Mock
    ) -> None:
        """Test extraction from PDF with no text content."""
        # Given
        strategy = PdfExtractionStrategy()
        file_content: bytes = b"Empty PDF"
        file_name: str = "empty.pdf"
        correlation_id: UUID = uuid4()

        # Mock PDF with no content
        mock_reader = Mock()
        mock_reader.is_encrypted = False
        mock_reader.pages = []
        mock_pdf_reader.return_value = mock_reader

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == ""

    @patch("services.file_service.implementations.extraction_strategies.PdfReader")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_pdf_parsing_error(
        self, mock_to_thread: AsyncMock, mock_pdf_reader: Mock
    ) -> None:
        """Test error handling when PDF parsing fails."""
        # Given
        strategy = PdfExtractionStrategy()
        file_content: bytes = b"Corrupt PDF"
        file_name: str = "corrupt.pdf"
        correlation_id: UUID = uuid4()

        # Mock PDF parsing error
        mock_pdf_reader.side_effect = Exception("Invalid PDF format")

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When/Then
        with pytest.raises(Exception, match="Invalid PDF format"):
            await strategy.extract(file_content, file_name, correlation_id)

    @patch("services.file_service.implementations.extraction_strategies.PdfReader")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_pdf_with_empty_pages_filtered(
        self, mock_to_thread: AsyncMock, mock_pdf_reader: Mock
    ) -> None:
        """Test that empty PDF pages are properly filtered out."""
        # Given
        strategy = PdfExtractionStrategy()
        file_content: bytes = b"PDF with empty pages"
        file_name: str = "mixed.pdf"
        correlation_id: UUID = uuid4()

        # Mock PDF with mixed content pages
        pages = [
            Mock(extract_text=Mock(return_value="Valid page content")),
            Mock(extract_text=Mock(return_value="")),  # Empty page
            Mock(extract_text=Mock(return_value="Another valid page")),
            Mock(extract_text=Mock(return_value="   \n\t  ")),  # Only whitespace
        ]

        mock_reader = Mock()
        mock_reader.is_encrypted = False
        mock_reader.pages = pages
        mock_pdf_reader.return_value = mock_reader

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == "Valid page content\nAnother valid page"

    @patch("services.file_service.implementations.extraction_strategies.PdfReader")
    @patch("services.file_service.implementations.extraction_strategies.asyncio.to_thread")
    async def test_extract_pdf_page_enumeration_logging(
        self, mock_to_thread: AsyncMock, mock_pdf_reader: Mock
    ) -> None:
        """Test that PDF page enumeration works correctly for logging."""
        # Given
        strategy = PdfExtractionStrategy()
        file_content: bytes = b"Multi-page PDF"
        file_name: str = "multi.pdf"
        correlation_id: UUID = uuid4()

        # Mock multi-page PDF
        pages = [
            Mock(extract_text=Mock(return_value="Page 1")),
            Mock(extract_text=Mock(return_value="Page 2")),
            Mock(extract_text=Mock(return_value="Page 3")),
        ]

        mock_reader = Mock()
        mock_reader.is_encrypted = False
        mock_reader.pages = pages
        mock_pdf_reader.return_value = mock_reader

        async def mock_sync_call(func: Callable[[], str]) -> str:
            return func()

        mock_to_thread.side_effect = mock_sync_call

        # When
        result: str = await strategy.extract(file_content, file_name, correlation_id)

        # Then
        assert result == "Page 1\nPage 2\nPage 3"
        # Verify all pages were processed
        for page in pages:
            page.extract_text.assert_called_once()
