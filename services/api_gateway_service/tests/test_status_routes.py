from __future__ import annotations

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

USER_ID = "test-user-123"
BATCH_ID = "test-batch-abc-123"


@pytest.fixture
async def client():
    """Create test client with pure Dishka container and test providers."""
    # Create test container with all required providers
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id=USER_ID),
        FastapiProvider(),  # Required for Request context
    )

    # Create app manually to have full control over setup
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from huleedu_service_libs.error_handling.fastapi import (
        register_error_handlers as register_fastapi_error_handlers,
    )

    app = FastAPI(title="api_gateway_service_test")
    register_fastapi_error_handlers(app)

    # Add middleware
    from services.api_gateway_service.app.middleware import CorrelationIDMiddleware

    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    from services.api_gateway_service.routers import status_routes

    app.include_router(status_routes.router, prefix="/v1", tags=["Status"])

    # Setup Dishka with test container
    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await container.close()


@pytest.mark.asyncio
async def test_get_batch_status_success(client: AsyncClient, respx_mock: MockRouter):
    """Test successful retrieval of batch status with status mapping."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    mock_route = respx_mock.get(aggregator_url).mock(
        return_value=Response(
            200,
            json={
                "user_id": USER_ID,
                "overall_status": "completed_successfully",
                "batch_id": BATCH_ID,
                "essay_count": 5,
            },
        )
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    response_data = response.json()

    # Verify status mapping: completed_successfully → completed_successfully
    assert response_data["status"] == "completed_successfully"

    # Verify details contain the batch info (minus user_id)
    assert response_data["details"]["batch_id"] == BATCH_ID
    assert response_data["details"]["essay_count"] == 5
    assert "user_id" not in response_data["details"]  # Should be removed

    assert mock_route.called


@pytest.mark.asyncio
async def test_get_batch_status_mapping_pending_content(
    client: AsyncClient, respx_mock: MockRouter
):
    """Test status mapping for content validation states."""
    test_cases = ["awaiting_content_validation", "awaiting_pipeline_configuration"]

    for internal_status in test_cases:
        aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
        respx_mock.get(aggregator_url).mock(
            return_value=Response(
                200,
                json={"user_id": USER_ID, "overall_status": internal_status, "batch_id": BATCH_ID},
            )
        )

        response = await client.get(f"/v1/batches/{BATCH_ID}/status")

        assert response.status_code == 200
        assert response.json()["status"] == "pending_content"


@pytest.mark.asyncio
async def test_get_batch_status_mapping_ready(client: AsyncClient, respx_mock: MockRouter):
    """Test status mapping for ready state."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    respx_mock.get(aggregator_url).mock(
        return_value=Response(
            200,
            json={
                "user_id": USER_ID,
                "overall_status": "ready_for_pipeline_execution",
                "batch_id": BATCH_ID,
            },
        )
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_get_batch_status_mapping_processing(client: AsyncClient, respx_mock: MockRouter):
    """Test status mapping for processing states."""
    test_cases = [
        "processing_pipelines",
        "awaiting_student_validation",
        "student_validation_completed",
        "validation_timeout_processed",
    ]

    for internal_status in test_cases:
        aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
        respx_mock.get(aggregator_url).mock(
            return_value=Response(
                200,
                json={"user_id": USER_ID, "overall_status": internal_status, "batch_id": BATCH_ID},
            )
        )

        response = await client.get(f"/v1/batches/{BATCH_ID}/status")

        assert response.status_code == 200
        assert response.json()["status"] == "processing"


@pytest.mark.asyncio
async def test_get_batch_status_mapping_completed_with_failures(
    client: AsyncClient, respx_mock: MockRouter
):
    """Test status mapping for completed with failures."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    respx_mock.get(aggregator_url).mock(
        return_value=Response(
            200,
            json={
                "user_id": USER_ID,
                "overall_status": "completed_with_failures",
                "batch_id": BATCH_ID,
                "failed_essay_count": 2,
            },
        )
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["status"] == "completed_with_failures"
    assert response_data["details"]["failed_essay_count"] == 2


@pytest.mark.asyncio
async def test_get_batch_status_mapping_failed(client: AsyncClient, respx_mock: MockRouter):
    """Test status mapping for failure states."""
    test_cases = ["content_ingestion_failed", "failed_critically"]

    for internal_status in test_cases:
        aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
        respx_mock.get(aggregator_url).mock(
            return_value=Response(
                200,
                json={"user_id": USER_ID, "overall_status": internal_status, "batch_id": BATCH_ID},
            )
        )

        response = await client.get(f"/v1/batches/{BATCH_ID}/status")

        assert response.status_code == 200
        assert response.json()["status"] == "failed"


@pytest.mark.asyncio
async def test_get_batch_status_mapping_cancelled(client: AsyncClient, respx_mock: MockRouter):
    """Test status mapping for cancelled state."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    respx_mock.get(aggregator_url).mock(
        return_value=Response(
            200, json={"user_id": USER_ID, "overall_status": "cancelled", "batch_id": BATCH_ID}
        )
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_get_batch_status_mapping_missing_status(client: AsyncClient, respx_mock: MockRouter):
    """Test status mapping when overall_status is missing."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    respx_mock.get(aggregator_url).mock(
        return_value=Response(
            200,
            json={
                "user_id": USER_ID,
                "batch_id": BATCH_ID,
                # overall_status intentionally missing
            },
        )
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    # Should default to pending_content when status is missing
    assert response.json()["status"] == "pending_content"


@pytest.mark.asyncio
async def test_get_batch_status_mapping_unknown_status(client: AsyncClient, respx_mock: MockRouter):
    """Test status mapping for unknown internal status."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    respx_mock.get(aggregator_url).mock(
        return_value=Response(
            200,
            json={
                "user_id": USER_ID,
                "overall_status": "unknown_future_status",
                "batch_id": BATCH_ID,
            },
        )
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    # Should default to pending_content for unknown statuses
    assert response.json()["status"] == "pending_content"


@pytest.mark.asyncio
async def test_get_batch_status_ownership_failure(client: AsyncClient, respx_mock: MockRouter):
    """Test for 403 Forbidden when the batch belongs to a different user."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    respx_mock.get(aggregator_url).mock(
        return_value=Response(200, json={"user_id": "another-user-id", "status": "completed"})
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 403
    response_data = response.json()
    assert "error" in response_data
    assert response_data["error"]["code"] == "AUTHORIZATION_ERROR"
    assert "ownership violation" in response_data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_get_batch_status_not_found(client: AsyncClient, respx_mock: MockRouter):
    """Test 404 response when batch is not found."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"

    respx_mock.get(aggregator_url).mock(return_value=Response(404))

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 404
    response_data = response.json()
    assert "error" in response_data
    assert response_data["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert (
        "batch" in response_data["error"]["message"].lower()
        and "not found" in response_data["error"]["message"].lower()
    )
