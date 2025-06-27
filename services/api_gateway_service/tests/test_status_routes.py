from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide
from httpx import ASGITransport, AsyncClient, Response
from respx import MockRouter

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.redis_client import RedisClient
from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.auth import get_current_user_id
from services.api_gateway_service.config import settings

USER_ID = "test-user-123"
BATCH_ID = "test-batch-abc-123"


class MockApiGatewayProvider(Provider):
    scope = Scope.APP

    @provide
    async def get_http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient() as client:
            yield client

    @provide
    async def get_redis_client(self) -> AsyncIterator[RedisClient]:
        client = AsyncMock(spec=RedisClient)
        yield client

    @provide
    async def get_kafka_bus(self) -> AsyncIterator[KafkaBus]:
        bus = AsyncMock(spec=KafkaBus)
        yield bus


@pytest.fixture
async def container():
    container = make_async_container(MockApiGatewayProvider())
    yield container
    await container.close()


@pytest.fixture
def mock_auth():
    def get_test_user():
        return USER_ID

    return get_test_user


@pytest.fixture
async def client(container, mock_auth):
    app = create_app()
    app.dependency_overrides[get_current_user_id] = mock_auth
    from dishka.integrations.fastapi import setup_dishka

    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


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
    assert response.json() == {"detail": "Access denied"}


@pytest.mark.asyncio
async def test_get_batch_status_not_found_fallback_success(
    client: AsyncClient, respx_mock: MockRouter
):
    """Test fallback to BOS when batch is not in the aggregator."""
    settings.HANDLE_MISSING_BATCHES = "query_bos"
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    bos_url = f"{settings.BOS_URL}/internal/v1/batches/{BATCH_ID}/pipeline-state"

    respx_mock.get(aggregator_url).mock(return_value=Response(404))
    bos_mock = respx_mock.get(bos_url).mock(
        return_value=Response(200, json={"user_id": USER_ID, "pipeline_status": "running"})
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "processing",
        "details": {"user_id": USER_ID, "pipeline_status": "running"},
    }
    assert bos_mock.called
