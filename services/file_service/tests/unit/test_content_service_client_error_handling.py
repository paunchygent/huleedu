"""
Unit tests for ContentServiceClient error handling scenarios.

Focuses on HTTP client error paths, response validation, and 
structured error handling following architectural principles.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from aiohttp import ClientConnectionError, ClientError, ClientSession, ServerTimeoutError
from common_core.domain_enums import ContentType
from huleedu_service_libs.error_handling import HuleEduError

from services.file_service.config import Settings
from services.file_service.implementations.content_service_client_impl import (
    DefaultContentServiceClient,
)


# Removed AsyncContextManagerMock - will use standard mocking pattern


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with Content Service URL."""
    settings: Mock = Mock(spec=Settings)
    settings.CONTENT_SERVICE_URL = "http://content-service:8001/v1/content"
    return settings


@pytest.fixture
def mock_http_session() -> AsyncMock:
    """Mock aiohttp.ClientSession."""
    return AsyncMock(spec=ClientSession)


@pytest.fixture
def sample_content_data() -> tuple[bytes, ContentType, UUID]:
    """Sample test data for content storage."""
    content_bytes: bytes = b"Sample essay content for testing"
    content_type: ContentType = ContentType.EXTRACTED_PLAINTEXT
    correlation_id: UUID = uuid4()
    return content_bytes, content_type, correlation_id


class TestContentServiceClientErrorHandling:
    """Test error handling scenarios for ContentServiceClient."""

    async def test_connection_error_wrapped_as_huleedu_error(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that ClientConnectionError is wrapped as HuleEduError."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        mock_http_session.post.side_effect = ClientConnectionError("Connection refused")
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Failed to store content" in error_detail.message

    async def test_timeout_error_wrapped_as_huleedu_error(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that ServerTimeoutError is wrapped as HuleEduError."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        mock_http_session.post.side_effect = ServerTimeoutError("Request timeout")
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Failed to store content" in error_detail.message

    async def test_general_client_error_wrapped_as_huleedu_error(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that general ClientError is wrapped as HuleEduError."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        mock_http_session.post.side_effect = ClientError("HTTP client error")
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Failed to store content" in error_detail.message

    async def test_http_400_status_raises_external_service_error(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that HTTP 400 response raises external service error."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        
        mock_response: AsyncMock = AsyncMock()
        mock_response.status = 400
        mock_response.text.return_value = "Bad request - invalid content"
        
        # Set up async context manager mock following established pattern
        mock_http_session.post.return_value.__aenter__.return_value = mock_response
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Content Service returned status 400" in error_detail.message
        assert "Bad request - invalid content" in error_detail.message

    async def test_http_500_status_raises_external_service_error(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that HTTP 500 response raises external service error."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        
        mock_response: AsyncMock = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Internal server error"
        
        # Set up async context manager mock following established pattern
        mock_http_session.post.return_value.__aenter__.return_value = mock_response
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Content Service returned status 500" in error_detail.message

    async def test_missing_storage_id_in_success_response(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that missing storage_id in 201 response raises content service error."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        
        mock_response: AsyncMock = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {"success": True}  # Missing storage_id
        
        # Set up async context manager mock following established pattern
        mock_http_session.post.return_value.__aenter__.return_value = mock_response
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Content Service response missing storage_id" in error_detail.message

    async def test_invalid_storage_id_format_none(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that None storage_id in 201 response raises content service error."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        
        mock_response: AsyncMock = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {"storage_id": None}
        
        # Set up async context manager mock following established pattern
        mock_http_session.post.return_value.__aenter__.return_value = mock_response
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Content Service response missing storage_id" in error_detail.message

    async def test_invalid_storage_id_format_empty_string(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that empty storage_id in 201 response raises content service error."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        
        mock_response: AsyncMock = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {"storage_id": ""}
        
        # Set up async context manager mock following established pattern
        mock_http_session.post.return_value.__aenter__.return_value = mock_response
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Content Service response missing storage_id" in error_detail.message

    async def test_invalid_storage_id_format_non_string(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that non-string storage_id in 201 response raises content service error."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        
        mock_response: AsyncMock = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {"storage_id": 12345}  # Integer instead of string
        
        # Set up async context manager mock following established pattern
        mock_http_session.post.return_value.__aenter__.return_value = mock_response
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Content Service response missing storage_id" in error_detail.message

    async def test_successful_content_storage(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test successful content storage returns storage_id."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        expected_storage_id: str = "test-storage-123"
        
        mock_response: AsyncMock = AsyncMock()
        mock_response.status = 201
        mock_response.json.return_value = {"storage_id": expected_storage_id}
        
        # Set up async context manager mock following established pattern
        mock_http_session.post.return_value.__aenter__.return_value = mock_response
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When
        result: str = await client.store_content(content_bytes, content_type, correlation_id)

        # Then
        assert result == expected_storage_id
        
        # Verify HTTP request was made correctly
        mock_http_session.post.assert_called_once_with(
            test_settings.CONTENT_SERVICE_URL,
            data=content_bytes,
            headers={"X-Correlation-ID": str(correlation_id)},
        )

    async def test_already_huleedu_error_preserved(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that HuleEduError exceptions are re-raised without wrapping."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        
        # Create a mock HuleEduError with error_detail attribute
        class MockHuleEduError(Exception):
            def __init__(self):
                self.error_detail = Mock()
        
        original_error = MockHuleEduError()
        mock_http_session.post.side_effect = original_error
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(MockHuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify the original error was re-raised
        assert exc_info.value is original_error

    async def test_json_decode_error_wrapped(
        self,
        test_settings: Settings,
        mock_http_session: AsyncMock,
        sample_content_data: tuple[bytes, ContentType, UUID],
    ) -> None:
        """Test that JSON decode errors are wrapped as HuleEduError."""
        # Given
        content_bytes, content_type, correlation_id = sample_content_data
        
        mock_response: AsyncMock = AsyncMock()
        mock_response.status = 201
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "doc", 0)
        
        # Set up async context manager mock following established pattern
        mock_http_session.post.return_value.__aenter__.return_value = mock_response
        
        client: DefaultContentServiceClient = DefaultContentServiceClient(
            http_session=mock_http_session, settings=test_settings
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await client.store_content(content_bytes, content_type, correlation_id)

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "file_service"
        assert error_detail.operation == "store_content"
        assert error_detail.correlation_id == correlation_id
        assert "Failed to store content" in error_detail.message