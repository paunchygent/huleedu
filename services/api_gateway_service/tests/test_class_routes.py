from __future__ import annotations

import pytest
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from httpx import ASGITransport, AsyncClient, Response
from respx import MockRouter

from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.config import settings
from services.api_gateway_service.tests.test_provider import (
    AuthTestProvider,
    InfrastructureTestProvider,
)

USER_ID = "test-user-123"
ORG_ID = "test-org-456"


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
    """Create test container with standardized test providers."""
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id=USER_ID),
        FastapiProvider(),  # Required for Request context
    )
    yield container
    await container.close()


@pytest.fixture
async def client(container):
    """Create test client with pure Dishka container."""
    app = create_app()

    # Set up Dishka with test container - this replaces the production container
    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def container_with_org():
    """Create test container with standardized test providers including org_id."""
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id=USER_ID, org_id=ORG_ID),
        FastapiProvider(),  # Required for Request context
    )
    yield container
    await container.close()


@pytest.fixture
async def client_with_org(container_with_org):
    """Create test client with org_id in auth context."""
    app = create_app()

    # Set up Dishka with test container - this replaces the production container
    setup_dishka(container_with_org, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


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


@pytest.mark.asyncio
async def test_proxy_forwards_identity_headers(client: AsyncClient, respx_mock: MockRouter):
    """Test that identity headers are forwarded to the class management service."""
    downstream_url = f"{settings.CMS_API_URL}/v1/classes/test/path"
    mock_route = respx_mock.get(downstream_url).mock(
        return_value=Response(200, json={"status": "ok"})
    )

    response = await client.get("/v1/classes/test/path")

    assert response.status_code == 200
    assert mock_route.called

    # Verify identity headers were forwarded
    request = mock_route.calls.last.request
    assert request.headers.get("X-User-ID") == USER_ID
    assert "X-Correlation-ID" in request.headers
    # No org_id in basic client fixture


@pytest.mark.asyncio
async def test_proxy_forwards_org_id_when_present(client_with_org: AsyncClient, respx_mock: MockRouter):
    """Test that X-Org-ID header is forwarded when org_id is present in DI."""
    downstream_url = f"{settings.CMS_API_URL}/v1/classes/org/path"
    mock_route = respx_mock.post(downstream_url).mock(
        return_value=Response(201, json={"id": 456})
    )

    response = await client_with_org.post("/v1/classes/org/path", json={"data": "test"})

    assert response.status_code == 201
    assert mock_route.called

    # Verify all identity headers were forwarded
    request = mock_route.calls.last.request
    assert request.headers.get("X-User-ID") == USER_ID
    assert request.headers.get("X-Org-ID") == ORG_ID
    assert "X-Correlation-ID" in request.headers
