"""
Tests for health check endpoints in WebSocket Service.

Tests the health endpoints for basic service health, Redis connectivity,
WebSocket manager status, and Prometheus metrics.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from services.websocket_service.tests.conftest import (
        MockJWTValidator,
        MockRedisClient,
        MockWebSocketManager,
    )


class TestHealthRoutes:
    """Test suite for health check endpoints."""

    def test_basic_health_check(self, create_test_app: Callable[[], FastAPI]) -> None:
        """Test basic health check endpoint returns healthy status."""
        app = create_test_app()

        with TestClient(app) as client:
            response = client.get("/healthz")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "websocket_service"
        assert "timestamp" in data
        assert "uptime_seconds" in data

    def test_redis_health_check_success(
        self, create_test_app: Callable[[], FastAPI], mock_redis_client: MockRedisClient
    ) -> None:
        """Test Redis health check when Redis is healthy."""
        app = create_test_app()

        # Redis mock is configured to succeed by default
        with TestClient(app) as client:
            response = client.get("/healthz/redis")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "redis"
        assert "url" in data
        # Verify credentials are masked
        assert "***:***" in data["url"]

    def test_redis_health_check_failure(
        self, create_test_app: Callable[[], FastAPI], mock_redis_client: MockRedisClient
    ) -> None:
        """Test Redis health check when Redis is unhealthy."""
        app = create_test_app()

        # Configure Redis to fail
        mock_redis_client.ping.side_effect = Exception("Connection refused")

        with TestClient(app) as client:
            response = client.get("/healthz/redis")

        assert response.status_code == 503
        data = response.json()
        # HTTPException returns detail as the body
        assert "detail" in data
        detail = data["detail"]
        assert detail["status"] == "unhealthy"
        assert detail["service"] == "redis"
        assert "error" in detail

    def test_websocket_manager_health(
        self, create_test_app: Callable[[], FastAPI], mock_websocket_manager: MockWebSocketManager
    ) -> None:
        """Test WebSocket manager health endpoint."""
        app = create_test_app()

        # Add some test connections
        mock_websocket_manager.connections = {
            "user1": ["conn1", "conn2"],
            "user2": ["conn3"],
        }

        with TestClient(app) as client:
            response = client.get("/healthz/websocket")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "websocket_manager"
        assert data["total_connections"] == 3
        assert data["max_connections_per_user"] == 5

    def test_metrics_endpoint(
        self,
        test_container: Any,
        mock_redis_client: MockRedisClient,
        mock_websocket_manager: MockWebSocketManager,
        mock_jwt_validator: MockJWTValidator,
    ) -> None:
        """Test Prometheus metrics endpoint returns valid Prometheus format."""
        import asyncio

        from dishka.integrations.fastapi import setup_dishka
        from prometheus_client import CollectorRegistry

        from services.websocket_service.metrics import WebSocketMetrics

        app = FastAPI()
        setup_dishka(test_container, app)

        # Ensure metrics are created by explicitly requesting them from the container
        async def ensure_metrics_created() -> None:
            async with test_container() as request_container:
                # This will create the metrics if not already created
                await request_container.get(CollectorRegistry)
                await request_container.get(WebSocketMetrics)

        asyncio.run(ensure_metrics_created())

        # Register routes after ensuring metrics are created
        from services.websocket_service.routers import health_routes, websocket_routes

        app.include_router(health_routes.router, tags=["Health"])
        app.include_router(websocket_routes.router, prefix="/ws", tags=["WebSocket"])

        with TestClient(app) as client:
            response = client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

        # Verify response contains Prometheus metrics format
        content = response.text
        assert len(content) > 0, "Metrics response should not be empty"
        assert "# HELP" in content
        assert "# TYPE" in content

        # Check for WebSocket-specific metrics in the output
        assert "websocket_connections_total" in content
        assert "websocket_active_connections" in content
        assert "websocket_http_request_duration_seconds" in content
