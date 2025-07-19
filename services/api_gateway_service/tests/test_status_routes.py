from __future__ import annotations

import pytest
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from httpx import ASGITransport, AsyncClient, Response
from respx import MockRouter

from services.api_gateway_service.config import settings
from services.api_gateway_service.tests.test_provider import (
    TestApiGatewayProvider,
    TestAuthProvider,
)

USER_ID = "test-user-123"
BATCH_ID = "test-batch-abc-123"


@pytest.fixture
async def client():
    """Create test client with pure Dishka container and test providers."""
    # Create test container with all required providers
    container = make_async_container(
        TestApiGatewayProvider(),
        TestAuthProvider(user_id=USER_ID),
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
    """Test successful retrieval of batch status with correct ownership."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    mock_route = respx_mock.get(aggregator_url).mock(
        return_value=Response(200, json={"user_id": USER_ID, "status": "completed"})
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "available",
        "details": {"status": "completed"},
    }
    assert mock_route.called


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
