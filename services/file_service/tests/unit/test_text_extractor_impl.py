"""
Unit tests for TextExtractorImpl.

Tests the DefaultTextExtractor implementation to ensure proper delegation
to text processing functionality.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from services.file_service.implementations.text_extractor_impl import DefaultTextExtractor


class TestDefaultTextExtractor:
    """Test DefaultTextExtractor implementation."""

    async def test_extract_text_delegates_to_text_processing(self) -> None:
        """Test that extract_text properly delegates to extract_text_from_file."""
        # Given
        file_content: bytes = b"Test file content"
        file_name: str = "test.txt"
        correlation_id: UUID = uuid4()
        expected_text: str = "Test file content"

        # Mock the text processing function
        with patch(
            "services.file_service.implementations.text_extractor_impl.extract_text_from_file",
            new_callable=AsyncMock,
        ) as mock_extract:
            mock_extract.return_value = expected_text

            # Create extractor instance
            extractor = DefaultTextExtractor()

            # When
            result: str = await extractor.extract_text(file_content, file_name, correlation_id)

            # Then
            assert result == expected_text
            mock_extract.assert_called_once_with(file_content, file_name, correlation_id)

    async def test_extract_text_propagates_exceptions(self) -> None:
        """Test that exceptions from extract_text_from_file are propagated."""
        # Given
        file_content: bytes = b"Test file content"
        file_name: str = "test.pdf"
        correlation_id: UUID = uuid4()
        
        # Mock to raise an exception
        with patch(
            "services.file_service.implementations.text_extractor_impl.extract_text_from_file",
            new_callable=AsyncMock,
        ) as mock_extract:
            mock_extract.side_effect = ValueError("Unsupported file type")

            # Create extractor instance
            extractor = DefaultTextExtractor()

            # When/Then
            with pytest.raises(ValueError) as exc_info:
                await extractor.extract_text(file_content, file_name, correlation_id)
            
            assert str(exc_info.value) == "Unsupported file type"
            mock_extract.assert_called_once_with(file_content, file_name, correlation_id)