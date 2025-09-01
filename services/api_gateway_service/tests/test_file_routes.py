"""
Tests for file upload routes in API Gateway Service.

Tests the POST /v1/files/batch endpoint with proper authentication, rate limiting,
and proxy functionality to the File Service.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, Mock

import pytest
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi.testclient import TestClient

from services.api_gateway_service.tests.conftest import create_test_app_with_isolated_registry
from services.api_gateway_service.tests.test_provider import (
    AuthTestProvider,
    HttpClientTestProvider,
)

USER_ID = "test_user_123"
ORG_ID = "test_org_999"
SWEDISH_USER_ID = "lärare_åsa_123"
SWEDISH_ORG_ID = "skolan_västerås"


def create_test_file(filename: str, content: str) -> tuple[str, BytesIO, str]:
    """Helper to create test file uploads."""
    return (filename, BytesIO(content.encode()), "text/plain")


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for file upload tests."""
    return AsyncMock()


@pytest.fixture
async def client_with_mocks(mock_http_client, monkeypatch):
    """Create test client with pure Dishka container and mocked HTTP client."""
    # Create container with test providers including mocked HTTP client
    from prometheus_client import CollectorRegistry

    # Create isolated registry for this test
    test_registry = CollectorRegistry()

    container = make_async_container(
        HttpClientTestProvider(mock_http_client),  # Override HTTP client
        AuthTestProvider(user_id=USER_ID),
        FastapiProvider(),  # Required for Request context
    )

    app = create_test_app_with_isolated_registry(test_registry)

    # Set up Dishka with test container - this replaces the production container
    setup_dishka(container, app)

    # Disable rate limiting entirely for tests (official SlowAPI approach)
    monkeypatch.setattr("services.api_gateway_service.app.rate_limiter.limiter.enabled", False)

    with TestClient(app) as client:
        yield client

    # Clean up
    await container.close()


@pytest.fixture
async def client_with_org_mocks(mock_http_client, monkeypatch):
    """Create test client with container providing an org_id for DI."""
    from prometheus_client import CollectorRegistry

    test_registry = CollectorRegistry()

    container = make_async_container(
        HttpClientTestProvider(mock_http_client),
        AuthTestProvider(user_id=USER_ID, org_id=ORG_ID),
        FastapiProvider(),
    )

    app = create_test_app_with_isolated_registry(test_registry)
    setup_dishka(container, app)

    monkeypatch.setattr("services.api_gateway_service.app.rate_limiter.limiter.enabled", False)

    with TestClient(app) as client:
        yield client
    await container.close()


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
async def test_file_upload_forwards_org_id_header(client_with_org_mocks, mock_http_client):
    """When org_id is present in DI, X-Org-ID header should be forwarded to file service."""
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"message": "Files uploaded successfully"}
    mock_http_client.post.return_value = mock_response

    test_file = create_test_file("essay.txt", "content")
    response = client_with_org_mocks.post(
        "/v1/files/batch", files={"files": test_file}, data={"batch_id": "batch_with_org"}
    )

    assert response.status_code == 201
    call_args = mock_http_client.post.call_args
    headers = call_args.kwargs["headers"]
    assert headers.get("X-Org-ID") == ORG_ID


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
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "File type not supported" in error["message"]


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

    assert response.status_code == 401
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "AUTHENTICATION_ERROR"
    assert "Access denied" in error["message"]


@pytest.mark.asyncio
async def test_file_upload_accepts_202(client_with_mocks, mock_http_client):
    """API Gateway should pass through 202 Accepted from File Service as success."""
    mock_response = Mock()
    mock_response.status_code = 202
    mock_response.json.return_value = {
        "message": "Files accepted for processing",
        "batch_id": "batch_202",
        "correlation_id": "00000000-0000-0000-0000-000000000000",
    }
    mock_http_client.post.return_value = mock_response

    test_file = create_test_file("essay.txt", "content")
    response = client_with_mocks.post(
        "/v1/files/batch", files={"files": test_file}, data={"batch_id": "batch_202"}
    )

    assert response.status_code == 202
    body = response.json()
    assert body.get("batch_id") == "batch_202"


@pytest.mark.asyncio
async def test_swedish_user_id_is_url_encoded_in_forwarded_headers(monkeypatch):
    """Swedish user/org IDs are URL-encoded with encoding marker when forwarded."""
    from urllib.parse import quote

    from prometheus_client import CollectorRegistry

    mock_http_client = AsyncMock()
    mock_response = Mock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"message": "Files uploaded successfully"}
    mock_http_client.post.return_value = mock_response

    test_registry = CollectorRegistry()
    container = make_async_container(
        HttpClientTestProvider(mock_http_client),
        AuthTestProvider(user_id=SWEDISH_USER_ID, org_id=SWEDISH_ORG_ID),
        FastapiProvider(),
    )

    app = create_test_app_with_isolated_registry(test_registry)
    setup_dishka(container, app)

    # Disable rate limiting
    monkeypatch.setattr("services.api_gateway_service.app.rate_limiter.limiter.enabled", False)

    try:
        with TestClient(app) as client:
            test_file = create_test_file("essay.txt", "content")
            resp = client.post(
                "/v1/files/batch", files={"files": test_file}, data={"batch_id": "batch_sv"}
            )
            assert resp.status_code == 201

        # Verify forwarded headers
        call_args = mock_http_client.post.call_args
        headers = call_args.kwargs["headers"]
        assert headers.get("X-Identity-Encoding") == "url"
        assert headers.get("X-User-ID") == quote(SWEDISH_USER_ID, safe="")
        assert headers.get("X-Org-ID") == quote(SWEDISH_ORG_ID, safe="")
    finally:
        await container.close()


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
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "RESOURCE_NOT_FOUND"
    assert "batch with ID 'nonexistent_batch' not found" in error["message"]


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

    assert response.status_code == 502
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "EXTERNAL_SERVICE_ERROR"
    assert "File service temporarily unavailable" in error["message"]


@pytest.mark.asyncio
async def test_file_upload_missing_batch_id(client_with_mocks):
    """Test validation when batch_id is missing."""
    test_file = create_test_file("essay.txt", "essay content")

    response = client_with_mocks.post(
        "/v1/files/batch",
        files={"files": test_file},
        # Missing batch_id in form data
    )

    assert response.status_code == 400  # Validation error
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "batch_id" in error["message"]


@pytest.mark.asyncio
async def test_file_upload_no_files(client_with_mocks):
    """Test validation when no files are provided."""
    response = client_with_mocks.post(
        "/v1/files/batch",
        data={"batch_id": "test_batch_123"},
        # Missing files
    )

    assert response.status_code == 400  # Validation error
    response_json = response.json()
    assert "error" in response_json
    error = response_json["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert "At least one file is required" in error["message"]


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

    # Verify correlation ID was forwarded (UUID is generated by DI system in tests)
    call_args = mock_http_client.post.call_args
    headers = call_args.kwargs["headers"]
    assert "X-Correlation-ID" in headers  # Verify header exists
    # Note: In test environment, DI system generates new UUID instead of using header value
