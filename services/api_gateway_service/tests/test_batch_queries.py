"""Tests for GET /v1/batches endpoint.

Tests batch listing with pagination, status filtering, and status mapping.
Follows test_status_routes.py pattern with Dishka DI and respx mocking.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from httpx import ASGITransport, AsyncClient, Response
from respx import MockRouter

from services.api_gateway_service.config import settings
from services.api_gateway_service.tests.test_provider import (
    AuthTestProvider,
    InfrastructureTestProvider,
)

USER_ID = "test-user-batch-queries"


@pytest.fixture
async def client():
    """Create test client with Dishka container and test providers."""
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id=USER_ID),
        FastapiProvider(),
    )

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from huleedu_service_libs.error_handling.fastapi import (
        register_error_handlers as register_fastapi_error_handlers,
    )

    app = FastAPI(title="api_gateway_service_test")
    register_fastapi_error_handlers(app)

    from services.api_gateway_service.app.middleware import CorrelationIDMiddleware

    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from services.api_gateway_service.routers import batch_queries

    app.include_router(batch_queries.router, prefix="/v1", tags=["Batch Queries"])

    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await container.close()


# --- Success Path Tests ---


@pytest.mark.asyncio
async def test_list_batches_success(client: AsyncClient, respx_mock: MockRouter):
    """Test successful retrieval of user's batches with multiple items."""
    batch_1_id = str(uuid4())
    batch_2_id = str(uuid4())

    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    mock_route = respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [
                    {
                        "batch_id": batch_1_id,
                        "overall_status": "completed_successfully",
                        "essay_count": 10,
                        "user_id": USER_ID,
                    },
                    {
                        "batch_id": batch_2_id,
                        "overall_status": "processing_pipelines",
                        "essay_count": 5,
                        "user_id": USER_ID,
                    },
                ],
                "pagination": {"limit": 20, "offset": 0, "total": 2},
            },
        )
    )

    response = await client.get("/v1/batches")

    assert response.status_code == 200
    data = response.json()

    assert len(data["batches"]) == 2
    assert data["batches"][0]["batch_id"] == batch_1_id
    assert data["batches"][1]["batch_id"] == batch_2_id
    assert data["pagination"]["total"] == 2
    assert mock_route.called


@pytest.mark.asyncio
async def test_list_batches_empty(client: AsyncClient, respx_mock: MockRouter):
    """Test successful response when user has no batches."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [],
                "pagination": {"limit": 20, "offset": 0, "total": 0},
            },
        )
    )

    response = await client.get("/v1/batches")

    assert response.status_code == 200
    data = response.json()
    assert data["batches"] == []
    assert data["pagination"]["total"] == 0


# --- Pagination Tests ---


@pytest.mark.asyncio
async def test_list_batches_pagination_params(client: AsyncClient, respx_mock: MockRouter):
    """Test pagination parameters are forwarded to RAS."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    mock_route = respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [],
                "pagination": {"limit": 50, "offset": 100, "total": 200},
            },
        )
    )

    response = await client.get("/v1/batches?limit=50&offset=100")

    assert response.status_code == 200

    # Verify the URL contains correct pagination params
    called_url = str(mock_route.calls[0].request.url)
    assert "limit=50" in called_url
    assert "offset=100" in called_url


@pytest.mark.asyncio
async def test_list_batches_pagination_metadata(client: AsyncClient, respx_mock: MockRouter):
    """Test pagination metadata is correctly returned in response."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [{"batch_id": "b1", "overall_status": "completed_successfully"}],
                "pagination": {"limit": 10, "offset": 20, "total": 150},
            },
        )
    )

    response = await client.get("/v1/batches?limit=10&offset=20")

    assert response.status_code == 200
    pagination = response.json()["pagination"]
    assert pagination["limit"] == 10
    assert pagination["offset"] == 20
    assert pagination["total"] == 150


# --- Status Filter Tests ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_status,expected_internal",
    [
        ("pending_content", "awaiting_content_validation"),
        ("ready", "ready_for_pipeline_execution"),
        ("processing", "processing_pipelines"),
        ("completed_successfully", "completed_successfully"),
        ("completed_with_failures", "completed_with_failures"),
        ("failed", "content_ingestion_failed"),
        ("cancelled", "cancelled"),
    ],
)
async def test_list_batches_status_filter_valid(
    client: AsyncClient,
    respx_mock: MockRouter,
    client_status: str,
    expected_internal: str,
):
    """Test valid client status filters map to correct internal status."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    mock_route = respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={"batches": [], "pagination": {"limit": 20, "offset": 0, "total": 0}},
        )
    )

    response = await client.get(f"/v1/batches?status={client_status}")

    assert response.status_code == 200

    # Verify internal status was sent to RAS
    called_url = str(mock_route.calls[0].request.url)
    assert f"status={expected_internal}" in called_url


@pytest.mark.asyncio
async def test_list_batches_status_filter_invalid(client: AsyncClient):
    """Test invalid status filter returns 400 validation error."""
    response = await client.get("/v1/batches?status=invalid_status")

    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "invalid status filter" in data["error"]["message"].lower()


# --- Status Mapping Tests ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "internal_status,expected_client_status",
    [
        # All internal statuses should map to their client equivalents
        ("awaiting_content_validation", "pending_content"),
        ("awaiting_pipeline_configuration", "pending_content"),
        ("ready_for_pipeline_execution", "ready"),
        ("processing_pipelines", "processing"),
        ("awaiting_student_validation", "processing"),
        ("student_validation_completed", "processing"),
        ("validation_timeout_processed", "processing"),
        ("completed_successfully", "completed_successfully"),
        ("completed_with_failures", "completed_with_failures"),
        ("content_ingestion_failed", "failed"),
        ("failed_critically", "failed"),
        ("cancelled", "cancelled"),
    ],
)
async def test_list_batches_status_mapping(
    client: AsyncClient,
    respx_mock: MockRouter,
    internal_status: str,
    expected_client_status: str,
):
    """Test internal statuses are correctly mapped to client statuses in response."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [{"batch_id": "test-batch", "overall_status": internal_status}],
                "pagination": {"limit": 20, "offset": 0, "total": 1},
            },
        )
    )

    response = await client.get("/v1/batches")

    assert response.status_code == 200
    batches = response.json()["batches"]
    assert batches[0]["overall_status"] == expected_client_status


@pytest.mark.asyncio
async def test_list_batches_removes_user_id(client: AsyncClient, respx_mock: MockRouter):
    """Test user_id is removed from batch objects in response."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={
                "batches": [
                    {
                        "batch_id": "test-batch",
                        "overall_status": "completed_successfully",
                        "user_id": USER_ID,
                        "essay_count": 5,
                    }
                ],
                "pagination": {"limit": 20, "offset": 0, "total": 1},
            },
        )
    )

    response = await client.get("/v1/batches")

    assert response.status_code == 200
    batch = response.json()["batches"][0]
    assert "user_id" not in batch
    assert batch["batch_id"] == "test-batch"
    assert batch["essay_count"] == 5


# --- Auth Headers Tests ---


@pytest.mark.asyncio
async def test_list_batches_auth_headers(client: AsyncClient, respx_mock: MockRouter):
    """Test internal auth headers are sent to RAS."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    mock_route = respx_mock.get(ras_url_pattern).mock(
        return_value=Response(
            200,
            json={"batches": [], "pagination": {"limit": 20, "offset": 0, "total": 0}},
        )
    )

    await client.get("/v1/batches")

    # Verify auth headers were sent
    request_headers = mock_route.calls[0].request.headers
    assert "x-internal-api-key" in request_headers
    assert "x-service-id" in request_headers
    assert request_headers["x-service-id"] == settings.SERVICE_NAME
    assert "x-correlation-id" in request_headers


# --- Error Handling Tests ---


@pytest.mark.asyncio
async def test_list_batches_ras_error_503(client: AsyncClient, respx_mock: MockRouter):
    """Test RAS 503 error is propagated as external service error."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(return_value=Response(503, text="Service Unavailable"))

    response = await client.get("/v1/batches")

    # Gateway returns 502 Bad Gateway for downstream failures
    assert response.status_code == 502
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "EXTERNAL_SERVICE_ERROR"


@pytest.mark.asyncio
async def test_list_batches_ras_error_500(client: AsyncClient, respx_mock: MockRouter):
    """Test RAS 500 error is propagated as external service error."""
    ras_url_pattern = re.compile(
        rf"{re.escape(settings.RESULT_AGGREGATOR_URL)}/internal/v1/batches/user/{USER_ID}\?.*"
    )
    respx_mock.get(ras_url_pattern).mock(return_value=Response(500, text="Internal Server Error"))

    response = await client.get("/v1/batches")

    # Gateway returns 502 Bad Gateway for downstream failures
    assert response.status_code == 502
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "EXTERNAL_SERVICE_ERROR"
