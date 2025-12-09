"""Unit tests for BFF Teacher proxy routes.

Tests the BFF Teacher Service proxy endpoint following established gateway
testing patterns from test_class_routes.py.
"""

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

USER_ID = "test-teacher-123"
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
    """Create test container with standardized test providers (no org_id)."""
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id=USER_ID),
        FastapiProvider(),
    )
    yield container
    await container.close()


@pytest.fixture
async def container_with_org():
    """Create test container with standardized test providers including org_id."""
    container = make_async_container(
        InfrastructureTestProvider(),
        AuthTestProvider(user_id=USER_ID, org_id=ORG_ID),
        FastapiProvider(),
    )
    yield container
    await container.close()


@pytest.fixture
async def client(container):
    """Create test client with pure Dishka container."""
    app = create_app()
    setup_dishka(container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client_with_org(container_with_org):
    """Create test client with org_id in auth context."""
    app = create_app()
    setup_dishka(container_with_org, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestBFFTeacherProxyRoutes:
    """Tests for /bff/v1/teacher/* proxy routes."""

    @pytest.mark.asyncio
    async def test_proxy_dashboard_get_success(self, client: AsyncClient, respx_mock: MockRouter):
        """Test that GET /bff/v1/teacher/dashboard returns 200 with mocked BFF response."""
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/dashboard"
        mock_route = respx_mock.get(downstream_url).mock(
            return_value=Response(200, json={"batches": [], "total_count": 0})
        )

        response = await client.get("/bff/v1/teacher/dashboard")

        assert response.status_code == 200
        assert response.json() == {"batches": [], "total_count": 0}
        assert mock_route.called
        assert len(mock_route.calls) == 1

    @pytest.mark.asyncio
    async def test_proxy_post_success(self, client: AsyncClient, respx_mock: MockRouter):
        """Test that POST requests are correctly proxied with their body."""
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/batches/create"
        mock_route = respx_mock.post(downstream_url).mock(
            return_value=Response(201, json={"id": "batch-123", "status": "created"})
        )
        request_body = {"name": "Test Batch", "class_id": "class-456"}

        response = await client.post("/bff/v1/teacher/batches/create", json=request_body)

        assert response.status_code == 201
        assert response.json() == {"id": "batch-123", "status": "created"}
        assert mock_route.called

    @pytest.mark.asyncio
    async def test_proxy_injects_user_id_header(self, client: AsyncClient, respx_mock: MockRouter):
        """Test that X-User-ID header is forwarded to BFF Teacher Service."""
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/profile"
        mock_route = respx_mock.get(downstream_url).mock(
            return_value=Response(200, json={"user_id": USER_ID})
        )

        response = await client.get("/bff/v1/teacher/profile")

        assert response.status_code == 200
        assert mock_route.called

        request = mock_route.calls.last.request
        assert request.headers.get("X-User-ID") == USER_ID

    @pytest.mark.asyncio
    async def test_proxy_injects_correlation_id_header(
        self, client: AsyncClient, respx_mock: MockRouter
    ):
        """Test that X-Correlation-ID header is forwarded to BFF Teacher Service."""
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/dashboard"
        mock_route = respx_mock.get(downstream_url).mock(
            return_value=Response(200, json={"status": "ok"})
        )

        response = await client.get("/bff/v1/teacher/dashboard")

        assert response.status_code == 200
        assert mock_route.called

        request = mock_route.calls.last.request
        assert "X-Correlation-ID" in request.headers

    @pytest.mark.asyncio
    async def test_proxy_injects_org_id_when_present(
        self, client_with_org: AsyncClient, respx_mock: MockRouter
    ):
        """Test that X-Org-ID header is forwarded when org_id is present in DI."""
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/org/batches"
        mock_route = respx_mock.get(downstream_url).mock(
            return_value=Response(200, json={"batches": []})
        )

        response = await client_with_org.get("/bff/v1/teacher/org/batches")

        assert response.status_code == 200
        assert mock_route.called

        request = mock_route.calls.last.request
        assert request.headers.get("X-User-ID") == USER_ID
        assert request.headers.get("X-Org-ID") == ORG_ID
        assert "X-Correlation-ID" in request.headers

    @pytest.mark.asyncio
    async def test_proxy_omits_org_id_when_none(self, client: AsyncClient, respx_mock: MockRouter):
        """Test that X-Org-ID header is not sent when org_id is None."""
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/dashboard"
        mock_route = respx_mock.get(downstream_url).mock(
            return_value=Response(200, json={"status": "ok"})
        )

        response = await client.get("/bff/v1/teacher/dashboard")

        assert response.status_code == 200
        assert mock_route.called

        request = mock_route.calls.last.request
        assert request.headers.get("X-User-ID") == USER_ID
        assert "X-Correlation-ID" in request.headers
        # X-Org-ID should not be present when org_id is None
        assert "X-Org-ID" not in request.headers

    @pytest.mark.asyncio
    async def test_proxy_service_unavailable(self, client: AsyncClient, respx_mock: MockRouter):
        """Test that 502 is returned when BFF Teacher Service is unavailable.

        EXTERNAL_SERVICE_ERROR maps to HTTP 502 (Bad Gateway) per error handling spec.
        """
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/dashboard"
        # Simulate connection error by raising an exception
        respx_mock.get(downstream_url).mock(side_effect=Exception("Connection refused"))

        response = await client.get("/bff/v1/teacher/dashboard")

        assert response.status_code == 502
        response_json = response.json()
        assert "error" in response_json
        error = response_json["error"]
        assert error["code"] == "EXTERNAL_SERVICE_ERROR"
        assert "bff_teacher" in error["message"].lower() or "BFF Teacher" in error["message"]

    @pytest.mark.asyncio
    async def test_proxy_preserves_status_code(self, client: AsyncClient, respx_mock: MockRouter):
        """Test that status codes from BFF are preserved in proxy response."""
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/batches/nonexistent"
        mock_route = respx_mock.get(downstream_url).mock(
            return_value=Response(404, json={"detail": "Batch not found"})
        )

        response = await client.get("/bff/v1/teacher/batches/nonexistent")

        assert response.status_code == 404
        assert response.json() == {"detail": "Batch not found"}
        assert mock_route.called

    @pytest.mark.asyncio
    async def test_proxy_forwards_query_params(self, client: AsyncClient, respx_mock: MockRouter):
        """Test that query parameters are correctly forwarded to BFF."""
        downstream_url = f"{settings.BFF_TEACHER_URL}/bff/v1/teacher/batches?status=active&limit=10"
        mock_route = respx_mock.get(downstream_url).mock(
            return_value=Response(200, json={"batches": [], "total": 0})
        )

        response = await client.get("/bff/v1/teacher/batches?status=active&limit=10")

        assert response.status_code == 200
        assert mock_route.called

        request = mock_route.calls.last.request
        assert str(request.url) == downstream_url
