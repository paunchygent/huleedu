from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import httpx
from dishka import Provider, Scope, make_async_container, provide
from httpx import ASGITransport, AsyncClient, Response
from prometheus_client import CollectorRegistry
from respx import MockRouter

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.redis_client import RedisClient
from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.auth import get_current_user_id
from services.api_gateway_service.config import settings

USER_ID = "test-user-123"


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

    @provide
    def provide_metrics(self) -> GatewayMetrics:
        return GatewayMetrics()

    @provide
    def provide_registry(self) -> CollectorRegistry:
        from prometheus_client import REGISTRY

        return REGISTRY


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    """Clear Prometheus registry before each test to avoid collisions."""
    from prometheus_client import REGISTRY
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield


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
async def test_proxy_class_requests_get(client: AsyncClient, respx_mock: MockRouter):
    """Test that GET requests are correctly proxied to the class management service."""
    downstream_url = f"{settings.CMS_API_URL}/v1/classes/some/path?param=value"
    mock_route = respx_mock.get(downstream_url).mock(
        return_value=Response(200, json={"status": "ok"})
    )

    response = await client.get("/v1/classes/some/path?param=value")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    assert mock_route.called
    assert len(mock_route.calls) == 1
    request = mock_route.calls.last.request
    assert str(request.url) == downstream_url


@pytest.mark.asyncio
async def test_proxy_class_requests_post(client: AsyncClient, respx_mock: MockRouter):
    """Test that POST requests are correctly proxied with their body."""
    downstream_url = f"{settings.CMS_API_URL}/v1/classes/another/path"
    mock_route = respx_mock.post(downstream_url).mock(return_value=Response(201, json={"id": 123}))
    request_body = {"name": "new class"}

    response = await client.post("/v1/classes/another/path", json=request_body)

    assert response.status_code == 201
    assert response.json() == {"id": 123}
    assert mock_route.called
    assert mock_route.calls.last.request.content == b'{"name":"new class"}'


@pytest.mark.asyncio
async def test_proxy_class_requests_error_handling(client: AsyncClient, respx_mock: MockRouter):
    """Test that errors from downstream service are properly handled."""
    downstream_url = f"{settings.CMS_API_URL}/v1/classes/error/path"
    mock_route = respx_mock.get(downstream_url).mock(
        return_value=Response(404, json={"detail": "Class not found"})
    )

    response = await client.get("/v1/classes/error/path")

    assert response.status_code == 404
    assert response.json() == {"detail": "Class not found"}
    assert mock_route.called
