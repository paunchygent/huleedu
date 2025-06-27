"""
Tests for file upload routes in API Gateway Service.

Tests the POST /v1/files/batch endpoint with proper authentication, rate limiting, 
and proxy functionality to the File Service.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide
from fastapi.testclient import TestClient

from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.auth import get_current_user_id


def create_test_file(filename: str, content: str) -> tuple[str, BytesIO, str]:
    """Helper to create test file uploads."""
    return (filename, BytesIO(content.encode()), "text/plain")


class MockProvider(Provider):
    """Test provider with mock dependencies."""

    scope = Scope.APP

    def __init__(self):
        super().__init__()
        self.mock_http_client = AsyncMock()

    @provide
    def get_http_client(self) -> httpx.AsyncClient:
        return self.mock_http_client


@pytest.fixture
def mock_provider():
    """Create mock provider for testing."""
    return MockProvider()


@pytest.fixture
def mock_http_client(mock_provider):
    """Get mock HTTP client from provider."""
    return mock_provider.mock_http_client


@pytest.fixture
async def container(mock_provider):
    """Create test container with mock dependencies."""
    container = make_async_container(mock_provider)
    yield container
    await container.close()


@pytest.fixture
def mock_auth():
    """Mock authentication to return test user."""

    def get_test_user():
        return "test_user_123"

    return get_test_user


@pytest.fixture
def client_with_mocks(container, mock_auth, monkeypatch):
    """Create test client with mocked dependencies."""
    app = create_app()

    # Override authentication
    app.dependency_overrides[get_current_user_id] = mock_auth

    # Set up Dishka with test container
    from dishka.integrations.fastapi import setup_dishka
    setup_dishka(container, app)

    # Disable rate limiting entirely for tests (official SlowAPI approach)
    monkeypatch.setattr("services.api_gateway_service.app.rate_limiter.limiter.enabled", False)

    with TestClient(app) as client:
        yield client

    # Clean up overrides
    app.dependency_overrides.clear()


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
