"""
Unit tests for the spell checker core logic.

These tests focus on testing the core logic functions related to spell checking,
content fetching, and content storing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ..core_logic import (
    default_fetch_content_impl,
    default_perform_spell_check_algorithm,
    default_store_content_impl,
)


@asynccontextmanager
async def mock_http_context_manager(mock_response: AsyncMock) -> Any:
    """A mock async context manager that yields the provided mock_response."""
    yield mock_response


class TestDefaultImplementations:
    """Test the default implementation functions."""

    @pytest.mark.asyncio
    async def test_default_perform_spell_check(self, sample_essay_id: str) -> None:
        """Test the default spell check implementation."""
        # Arrange
        text_with_errors = "This is a tset with teh word recieve."

        # Act
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text_with_errors, sample_essay_id,
        )

        # Assert - The real L2 + pyspellchecker implementation corrects multiple errors
        assert "the" in corrected_text  # "teh" should be corrected to "the"
        assert "receive" in corrected_text  # "recieve" should be corrected to "receive"
        assert (
            "set" in corrected_text
        )  # "tset" should be corrected to "set" (pyspellchecker behavior)
        assert (
            corrections_count >= 2
        )  # Should count at least the corrections made by real implementation
        # Note: Exact count may vary based on pyspellchecker behavior and L2 dictionary availability

    @pytest.mark.asyncio
    async def test_default_fetch_content_success(
        self, sample_essay_id: str, sample_storage_id: str,
    ) -> None:
        """Test successful content fetching."""
        # Arrange - Mock the actual HTTP response properly using custom async context manager
        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = AsyncMock(return_value="Sample content")

        mock_session = AsyncMock()
        # Use MagicMock for get() since it's not async, but returns an async context manager
        mock_session.get = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        result = await default_fetch_content_impl(
            mock_session, sample_storage_id, "http://test-service", sample_essay_id,
        )

        # Assert
        assert result == "Sample content"
        mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_fetch_content_http_error(
        self, sample_essay_id: str, sample_storage_id: str,
    ) -> None:
        """Test content fetching with HTTP error."""
        # Arrange
        mock_response = AsyncMock()
        # Make raise_for_status a regular MagicMock that raises an exception when called
        mock_response.raise_for_status = MagicMock(side_effect=Exception("HTTP 404"))

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        with pytest.raises(Exception, match="HTTP 404"):
            await default_fetch_content_impl(
                mock_session, sample_storage_id, "http://test-service", sample_essay_id,
            )

        # Assert
        mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_store_content_success(self, sample_essay_id: str) -> None:
        """Test successful content storing."""
        # Arrange
        content_to_store = "Corrected content"
        expected_storage_id = "new-storage-id"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"storage_id": expected_storage_id})

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        result = await default_store_content_impl(
            mock_session, content_to_store, "http://test-service", sample_essay_id,
        )

        # Assert
        assert result == expected_storage_id
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_store_content_http_error(self, sample_essay_id: str) -> None:
        """Test content storing with HTTP error."""
        # Arrange
        content_to_store = "Corrected content"

        mock_response = AsyncMock()
        # Make raise_for_status a regular MagicMock that raises an exception when called
        mock_response.raise_for_status = MagicMock(side_effect=Exception("HTTP 500"))

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        with pytest.raises(Exception, match="HTTP 500"):
            await default_store_content_impl(
                mock_session, content_to_store, "http://test-service", sample_essay_id,
            )

        # Assert
        mock_session.post.assert_called_once()
