"""
Behavior tests for HTTP operations.

These tests verify the behavior of HTTP operations without testing implementation details.
We use aioresponses to simulate HTTP responses and test actual error handling behavior.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
from uuid import uuid4

import aiohttp
import pytest
from aioresponses import aioresponses
from huleedu_service_libs.error_handling import HuleEduError

from services.spellchecker_service.http_operations import (
    default_fetch_content_impl,
    default_store_content_impl,
)


class TestHTTPOperationsBehavior:
    """Test the behavior of HTTP operations, not implementation details."""

    @pytest.fixture
    async def client_session(self) -> AsyncIterator[aiohttp.ClientSession]:
        """Create a real aiohttp session for testing."""
        async with aiohttp.ClientSession() as session:
            yield session

    @pytest.mark.asyncio
    async def test_fetch_content_success_returns_content(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test that successful fetch returns the expected content."""
        # Arrange
        storage_id = "test-storage-123"
        content_service_url = "http://content-service"
        expected_content = "This is the essay content to be spell checked."
        correlation_id = uuid4()

        with aioresponses() as m:
            m.get(
                f"{content_service_url}/{storage_id}",
                status=200,
                body=expected_content,
            )

            # Act
            result = await default_fetch_content_impl(
                session=client_session,
                storage_id=storage_id,
                content_service_url=content_service_url,
                correlation_id=correlation_id,
                essay_id="test-essay",
            )

            # Assert - Test behavior, not implementation
            assert result == expected_content
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_fetch_content_404_raises_content_service_error(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test that 404 response raises appropriate error."""
        # Arrange
        storage_id = "non-existent"
        content_service_url = "http://content-service"
        correlation_id = uuid4()

        with aioresponses() as m:
            m.get(
                f"{content_service_url}/{storage_id}",
                status=404,
                body="Content not found",
            )

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await default_fetch_content_impl(
                    session=client_session,
                    storage_id=storage_id,
                    content_service_url=content_service_url,
                    correlation_id=correlation_id,
                )

            # Verify error contains useful information
            error = exc_info.value
            assert "404" in str(error) or "not found" in str(error).lower()
            assert str(error.correlation_id) == str(correlation_id)

    @pytest.mark.asyncio
    async def test_fetch_content_500_raises_content_service_error(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test that 500 response raises appropriate error."""
        # Arrange
        storage_id = "test-storage"
        content_service_url = "http://content-service"
        correlation_id = uuid4()

        with aioresponses() as m:
            m.get(
                f"{content_service_url}/{storage_id}",
                status=500,
                body="Internal server error",
            )

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await default_fetch_content_impl(
                    session=client_session,
                    storage_id=storage_id,
                    content_service_url=content_service_url,
                    correlation_id=correlation_id,
                )

            # Verify error behavior
            error = exc_info.value
            assert "500" in str(error) or "server error" in str(error).lower()

    @pytest.mark.asyncio
    async def test_fetch_content_timeout_behavior(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test behavior when fetch times out."""
        # Arrange
        storage_id = "test-storage"
        content_service_url = "http://content-service"
        correlation_id = uuid4()

        with aioresponses() as m:
            # Simulate timeout with exception
            m.get(
                f"{content_service_url}/{storage_id}",
                exception=asyncio.TimeoutError("Request timeout"),
            )

            # Act & Assert
            with pytest.raises((HuleEduError, asyncio.TimeoutError)):
                await default_fetch_content_impl(
                    session=client_session,
                    storage_id=storage_id,
                    content_service_url=content_service_url,
                    correlation_id=correlation_id,
                )

    @pytest.mark.asyncio
    async def test_fetch_content_network_error_behavior(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test behavior when network error occurs."""
        # Arrange
        storage_id = "test-storage"
        content_service_url = "http://content-service"
        correlation_id = uuid4()

        with aioresponses() as m:
            # Simulate network error with a simpler exception
            m.get(
                f"{content_service_url}/{storage_id}",
                exception=aiohttp.ClientError("Network error"),
            )

            # Act & Assert
            with pytest.raises((HuleEduError, aiohttp.ClientError)):
                await default_fetch_content_impl(
                    session=client_session,
                    storage_id=storage_id,
                    content_service_url=content_service_url,
                    correlation_id=correlation_id,
                )

    @pytest.mark.asyncio
    async def test_store_content_success_returns_storage_id(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test that successful store returns new storage ID."""
        # Arrange
        content_service_url = "http://content-service"
        original_storage_id = "original-123"
        content = "Corrected essay content"
        expected_storage_id = "new-storage-456"
        correlation_id = uuid4()

        with aioresponses() as m:
            m.post(
                content_service_url,
                status=200,
                payload={"storage_id": expected_storage_id},
            )

            # Act
            result = await default_store_content_impl(
                session=client_session,
                content_service_url=content_service_url,
                original_storage_id=original_storage_id,
                content_type="corrected_text",
                content=content,
                correlation_id=correlation_id,
                essay_id="test-essay",
            )

            # Assert - Test behavior
            assert result == expected_storage_id
            assert isinstance(result, str)
            assert result != original_storage_id  # Should be a new ID

    @pytest.mark.asyncio
    async def test_store_content_conflict_behavior(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test behavior when store encounters a conflict."""
        # Arrange
        content_service_url = "http://content-service"
        original_storage_id = "original-123"
        content = "Corrected essay content"
        correlation_id = uuid4()

        with aioresponses() as m:
            m.post(
                content_service_url,
                status=409,
                body="Conflict: Content already exists",
            )

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await default_store_content_impl(
                    session=client_session,
                    content_service_url=content_service_url,
                    original_storage_id=original_storage_id,
                    content_type="corrected_text",
                    content=content,
                    correlation_id=correlation_id,
                )

            # Verify error behavior
            error = exc_info.value
            assert "409" in str(error) or "conflict" in str(error).lower()

    @pytest.mark.asyncio
    async def test_store_content_malformed_response_behavior(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test behavior when store response is malformed."""
        # Arrange
        content_service_url = "http://content-service"
        original_storage_id = "original-123"
        content = "Corrected essay content"
        correlation_id = uuid4()

        with aioresponses() as m:
            # Return success but with malformed JSON
            m.post(
                content_service_url,
                status=200,
                body="Not valid JSON",
            )

            # Act & Assert
            with pytest.raises((HuleEduError, ValueError)):
                await default_store_content_impl(
                    session=client_session,
                    content_service_url=content_service_url,
                    original_storage_id=original_storage_id,
                    content_type="corrected_text",
                    content=content,
                    correlation_id=correlation_id,
                )

    @pytest.mark.asyncio
    async def test_store_content_missing_storage_id_in_response(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test behavior when response doesn't contain storage_id."""
        # Arrange
        content_service_url = "http://content-service"
        original_storage_id = "original-123"
        content = "Corrected essay content"
        correlation_id = uuid4()

        with aioresponses() as m:
            # Return success but without storage_id
            m.post(
                content_service_url,
                status=200,
                payload={"message": "Success", "other_field": "value"},
            )

            # Act & Assert
            with pytest.raises((HuleEduError, KeyError)):
                await default_store_content_impl(
                    session=client_session,
                    content_service_url=content_service_url,
                    original_storage_id=original_storage_id,
                    content_type="corrected_text",
                    content=content,
                    correlation_id=correlation_id,
                )

    @pytest.mark.asyncio
    async def test_fetch_handles_empty_content_gracefully(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test that empty content is handled appropriately."""
        # Arrange
        storage_id = "empty-content"
        content_service_url = "http://content-service"
        correlation_id = uuid4()

        with aioresponses() as m:
            m.get(
                f"{content_service_url}/{storage_id}",
                status=200,
                body="",  # Empty content
            )

            # Act
            result = await default_fetch_content_impl(
                session=client_session,
                storage_id=storage_id,
                content_service_url=content_service_url,
                correlation_id=correlation_id,
            )

            # Assert - Empty content should be returned as-is
            assert result == ""
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_store_handles_large_content(self, client_session: aiohttp.ClientSession) -> None:
        """Test that large content can be stored successfully."""
        # Arrange
        content_service_url = "http://content-service"
        original_storage_id = "original-123"
        # Create large content (1MB)
        large_content = "x" * (1024 * 1024)
        expected_storage_id = "large-content-stored"
        correlation_id = uuid4()

        with aioresponses() as m:
            m.post(
                content_service_url,
                status=200,
                payload={"storage_id": expected_storage_id},
            )

            # Act
            result = await default_store_content_impl(
                session=client_session,
                content_service_url=content_service_url,
                original_storage_id=original_storage_id,
                content_type="corrected_text",
                content=large_content,
                correlation_id=correlation_id,
            )

            # Assert
            assert result == expected_storage_id

    @pytest.mark.asyncio
    async def test_operations_preserve_correlation_id(
        self, client_session: aiohttp.ClientSession
    ) -> None:
        """Test that correlation ID is preserved through operations."""
        # Arrange
        storage_id = "test-storage"
        content_service_url = "http://content-service"
        correlation_id = uuid4()

        with aioresponses() as m:
            m.get(
                f"{content_service_url}/{storage_id}",
                status=404,
            )

            # Act & Assert
            with pytest.raises(HuleEduError) as exc_info:
                await default_fetch_content_impl(
                    session=client_session,
                    storage_id=storage_id,
                    content_service_url=content_service_url,
                    correlation_id=correlation_id,
                )

            # Verify correlation ID is preserved in error
            assert str(exc_info.value.correlation_id) == str(correlation_id)
