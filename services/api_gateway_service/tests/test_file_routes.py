"""
Tests for file upload routes in API Gateway Service.

Tests the POST /v1/files/batch endpoint with proper authentication, rate limiting,
and proxy functionality to the File Service.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from io import BytesIO
from typing import cast
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.auth import get_current_user_id
from services.api_gateway_service.config import Settings, settings


def create_test_file(filename: str, content: str) -> tuple[str, BytesIO, str]:
    """Helper to create test file uploads."""
    return (filename, BytesIO(content.encode()), "text/plain")


class MockHttpClientProvider(Provider):
    """Provider that offers a mocked HTTP client for file upload tests."""

    scope = Scope.APP

    def __init__(self, mock_http_client: AsyncMock):
        super().__init__()
        self.mock_http_client = mock_http_client

    @provide
    def get_config(self) -> Settings:
        """Provide real settings for test consistency."""
        return settings

    @provide
    async def get_http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        """Provide mocked HTTP client for testing file uploads."""
        yield cast(httpx.AsyncClient, self.mock_http_client)

    @provide
    async def get_redis_client(self) -> AsyncIterator[AtomicRedisClientProtocol]:
        """Provide mocked Redis client."""
        client = AsyncMock()
        yield cast(AtomicRedisClientProtocol, client)

    @provide
    async def get_kafka_bus(self) -> AsyncIterator[KafkaBus]:
        """Provide mocked Kafka bus."""
        bus = AsyncMock(spec=KafkaBus)
        yield bus

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        """Provide isolated Prometheus registry for test independence."""
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    def provide_metrics(self, registry: CollectorRegistry) -> GatewayMetrics:
        """Provide GatewayMetrics with isolated registry."""
        return GatewayMetrics(registry=registry)


@pytest.fixture
def mock_auth():
    """Mock authentication to return test user."""

    def get_test_user():
        return "test_user_123"

    return get_test_user


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for file upload tests."""
    return AsyncMock()


@pytest.fixture
async def client_with_mocks(mock_auth, mock_http_client, monkeypatch):
    """Create test client with mocked dependencies."""
    # Create container with mock HTTP client
    test_container = make_async_container(MockHttpClientProvider(mock_http_client))
    
    app = create_app()

    # Override authentication
    app.dependency_overrides[get_current_user_id] = mock_auth

    # Set up Dishka with test container
    setup_dishka(test_container, app)

    # Disable rate limiting entirely for tests (official SlowAPI approach)
    monkeypatch.setattr("services.api_gateway_service.app.rate_limiter.limiter.enabled", False)

    with TestClient(app) as client:
        yield client

    # Clean up
    app.dependency_overrides.clear()
    await test_container.close()


@pytest.mark.asyncio
async def test_successful_file_upload(client_with_mocks, mock_http_client):
    """Test successful file upload proxy to file service."""
    # Mock successful file service response
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "message": "Files uploaded successfully",
        "batch_id": "test_batch_123",
        "uploaded_files": ["test.txt"],
    }
    mock_http_client.post.return_value = mock_response

    # Prepare test data
    test_file = create_test_file("essay1.txt", "This is a test essay.")

    response = client_with_mocks.post(
        "/v1/files/batch", files={"files": test_file}, data={"batch_id": "test_batch_123"}
    )

    # Verify response
    assert response.status_code == 201
    response_json = response.json()
    assert response_json["message"] == "Files uploaded successfully"
    assert response_json["batch_id"] == "test_batch_123"

    # Verify file service was called with correct parameters
    mock_http_client.post.assert_called_once()
    call_args = mock_http_client.post.call_args

    # Verify URL
    assert call_args[0][0] == "http://file_service:8000/v1/files/batch"

    # Verify headers include authentication
    headers = call_args.kwargs["headers"]
    assert headers["X-User-ID"] == "test_user_123"
    assert "X-Correlation-ID" in headers


@pytest.mark.asyncio
async def test_file_upload_with_multiple_files(client_with_mocks, mock_http_client):
    """Test file upload with multiple files."""
    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {
        "message": "Files uploaded successfully",
        "batch_id": "test_batch_456",
        "uploaded_files": ["essay1.txt", "essay2.txt"],
    }
    mock_http_client.post.return_value = mock_response

    # Prepare multiple test files
    files = [
        ("files", create_test_file("essay1.txt", "Essay 1 content")),
        ("files", create_test_file("essay2.txt", "Essay 2 content")),
    ]

    response = client_with_mocks.post(
        "/v1/files/batch", files=files, data={"batch_id": "test_batch_456"}
    )

    assert response.status_code == 201
    assert len(response.json()["uploaded_files"]) == 2


@pytest.mark.asyncio
async def test_file_upload_validation_error(client_with_mocks, mock_http_client):
    """Test handling of file service validation errors."""
    # Mock validation error response
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"detail": "File type not supported"}
    mock_http_client.post.return_value = mock_response

    test_file = create_test_file("invalid.exe", "invalid content")

    response = client_with_mocks.post(
        "/v1/files/batch", files={"files": test_file}, data={"batch_id": "test_batch_789"}
    )

    assert response.status_code == 400
    assert "File type not supported" in response.json()["detail"]


@pytest.mark.asyncio
async def test_file_upload_access_denied(client_with_mocks, mock_http_client):
    """Test handling of access denied from file service."""
    # Mock access denied response
    mock_response = Mock()
    mock_response.status_code = 403
    mock_response.json.return_value = {"detail": "Access denied to this batch"}
    mock_http_client.post.return_value = mock_response

    test_file = create_test_file("essay.txt", "essay content")

    response = client_with_mocks.post(
        "/v1/files/batch", files={"files": test_file}, data={"batch_id": "unauthorized_batch"}
    )

    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


@pytest.mark.asyncio
async def test_file_upload_batch_not_found(client_with_mocks, mock_http_client):
    """Test handling when batch is not found."""
    # Mock not found response
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"detail": "Batch not found"}
    mock_http_client.post.return_value = mock_response

    test_file = create_test_file("essay.txt", "essay content")

    response = client_with_mocks.post(
        "/v1/files/batch", files={"files": test_file}, data={"batch_id": "nonexistent_batch"}
    )

    assert response.status_code == 404
    assert "Batch not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_file_service_unavailable(client_with_mocks, mock_http_client):
    """Test handling when file service is unavailable."""
    # Mock service error response
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"detail": "Internal server error"}
    mock_http_client.post.return_value = mock_response

    test_file = create_test_file("essay.txt", "essay content")

    response = client_with_mocks.post(
        "/v1/files/batch", files={"files": test_file}, data={"batch_id": "test_batch_error"}
    )

    assert response.status_code == 503
    assert "File service temporarily unavailable" in response.json()["detail"]


@pytest.mark.asyncio
async def test_file_upload_missing_batch_id(client_with_mocks):
    """Test validation when batch_id is missing."""
    test_file = create_test_file("essay.txt", "essay content")

    response = client_with_mocks.post(
        "/v1/files/batch",
        files={"files": test_file},
        # Missing batch_id in form data
    )

    assert response.status_code == 422  # Validation error
    assert "batch_id" in str(response.json())


@pytest.mark.asyncio
async def test_file_upload_no_files(client_with_mocks):
    """Test validation when no files are provided."""
    response = client_with_mocks.post(
        "/v1/files/batch",
        data={"batch_id": "test_batch_123"},
        # Missing files
    )

    assert response.status_code == 422  # Validation error
    assert "files" in str(response.json())


@pytest.mark.asyncio
async def test_file_upload_correlation_id_forwarding(client_with_mocks, mock_http_client):
    """Test that correlation IDs are properly forwarded to file service."""
    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"message": "Success"}
    mock_http_client.post.return_value = mock_response

    test_file = create_test_file("essay.txt", "content")
    correlation_id = "test-correlation-123"

    response = client_with_mocks.post(
        "/v1/files/batch",
        files={"files": test_file},
        data={"batch_id": "test_batch_123"},
        headers={"X-Correlation-ID": correlation_id},
    )

    assert response.status_code == 201

    # Verify correlation ID was forwarded
    call_args = mock_http_client.post.call_args
    headers = call_args.kwargs["headers"]
    assert headers["X-Correlation-ID"] == correlation_id
