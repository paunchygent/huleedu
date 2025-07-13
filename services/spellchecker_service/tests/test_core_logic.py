"""
Unit tests for the spell checker core logic.

These tests focus on testing the core logic functions related to spell checking,
content fetching, and content storing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from aiohttp.client_reqrep import RequestInfo
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

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
            text_with_errors,
            sample_essay_id,
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
        self,
        sample_essay_id: str,
        sample_storage_id: str,
    ) -> None:
        """Test successful content fetching."""
        # Arrange - Mock the actual HTTP response properly using custom async context manager
        mock_response = AsyncMock()
        mock_response.status = 200  # Mock status attribute
        mock_response.text = AsyncMock(return_value="Sample content")
        mock_response.raise_for_status = MagicMock()  # Success case - no exception

        mock_session = AsyncMock()
        # Use MagicMock for get() since it's not async, but returns an async context manager
        mock_session.get = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        result = await default_fetch_content_impl(
            mock_session,
            sample_storage_id,
            "http://test-service",
            uuid4(),  # correlation_id
            sample_essay_id,  # essay_id
        )

        # Assert
        assert result == "Sample content"
        mock_session.get.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_fetch_content_http_error(
        self,
        sample_essay_id: str,
        sample_storage_id: str,
    ) -> None:
        """Test content fetching with HTTP error."""
        # Arrange
        mock_response = AsyncMock()
        mock_response.status = 404  # Mock status attribute for error case
        mock_response.text = AsyncMock(return_value="Not found")
        # Mock raise_for_status to raise ClientResponseError for 404
        url = URL("http://test-content-service.com/api/v1/content/test-storage-id")
        headers = CIMultiDictProxy(CIMultiDict({"Content-Type": "application/json"}))
        request_info = RequestInfo(url, "get", headers, url)
        error = aiohttp.ClientResponseError(request_info, (), status=404, message="Not Found")
        mock_response.raise_for_status = MagicMock(side_effect=error)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        with pytest.raises(Exception):
            await default_fetch_content_impl(
                mock_session,
                sample_storage_id,
                "http://test-service",
                uuid4(),  # correlation_id
                sample_essay_id,  # essay_id
            )

        # Assert
        mock_session.get.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_store_content_success(self, sample_essay_id: str) -> None:
        """Test successful content storing."""
        # Arrange
        content_to_store = "Corrected content"
        expected_storage_id = "new-storage-id"

        mock_response = AsyncMock()
        mock_response.status = 200  # Mock status attribute
        mock_response.json = AsyncMock(return_value={"storage_id": expected_storage_id})
        mock_response.raise_for_status = MagicMock()  # Success case - no exception

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        result = await default_store_content_impl(
            mock_session,
            content_to_store,
            "http://test-service",
            uuid4(),  # correlation_id
            sample_essay_id,  # essay_id
        )

        # Assert
        assert result == expected_storage_id
        mock_session.post.assert_called_once()
        mock_response.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_store_content_http_error(self, sample_essay_id: str) -> None:
        """Test content storing with HTTP error."""
        # Arrange
        content_to_store = "Corrected content"

        mock_response = AsyncMock()
        mock_response.status = 500  # Mock status attribute for error case
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        # Mock raise_for_status to raise ClientResponseError for 500
        url = URL("http://test-content-service.com/api/v1/content")
        headers = CIMultiDictProxy(CIMultiDict({"Content-Type": "application/json"}))
        request_info = RequestInfo(url, "post", headers, url)
        error = aiohttp.ClientResponseError(
            request_info, (), status=500, message="Internal Server Error"
        )
        mock_response.raise_for_status = MagicMock(side_effect=error)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_http_context_manager(mock_response))

        # Act
        with pytest.raises(Exception):
            await default_store_content_impl(
                mock_session,
                content_to_store,
                "http://test-service",
                uuid4(),  # correlation_id
                sample_essay_id,  # essay_id
            )

        # Assert
        mock_session.post.assert_called_once()
        mock_response.raise_for_status.assert_called_once()
