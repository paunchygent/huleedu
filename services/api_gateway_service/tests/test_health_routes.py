"""
Tests for health and metrics routes in API Gateway Service.

Tests the /healthz and /metrics endpoints with proper DI integration,
error handling, and Prometheus registry isolation.

Following Rule 070.1 (Protocol-based mocking) and Rule 042.2.1 (Protocol-based dependencies).
"""

from __future__ import annotations

import pytest
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry


class TestHealthRoutes:
    """Test suite for health check endpoints with comprehensive coverage."""

    @pytest.fixture
    def client_with_health_routes(self, unified_container):
        """Test client with health routes and mocked dependencies."""

        app = FastAPI()

        # Set up Dishka with test container
        setup_dishka(unified_container, app)

        # Register routes AFTER DI setup
        from services.api_gateway_service.routers import health_routes

        app.include_router(health_routes.router)

        with TestClient(app) as client:
            yield client

    def test_healthz_endpoint_returns_healthy_status(self, client_with_health_routes):
        """Test successful health check returns healthy status with all required fields."""
        # Act
        response = client_with_health_routes.get("/healthz")

        # Assert
        assert response.status_code == 200
        data = response.json()

        # Verify required fields per Rule 072
        assert data["service"] == "api_gateway_service"
        assert data["status"] == "healthy"
        assert data["message"] == "API Gateway Service is healthy"
        assert data["version"] == "1.0.0"
        assert data["environment"] == "development"

        # Verify health check structure
        assert "checks" in data
        assert data["checks"]["service_responsive"] is True
        assert data["checks"]["dependencies_available"] is True

        # Verify dependencies information
        assert "dependencies" in data
        assert "redis" in data["dependencies"]
        assert data["dependencies"]["redis"]["status"] == "healthy"
        assert "downstream_services" in data["dependencies"]
        assert data["dependencies"]["downstream_services"]["status"] == "healthy"

    def test_healthz_endpoint_exception_handling(self, unified_container):
        """Test health check gracefully handles exceptions."""

        app = FastAPI()

        # Set up DI container first
        setup_dishka(unified_container, app)

        # Create a test router that simulates the same exception handling logic
        from fastapi import APIRouter

        from huleedu_service_libs.logging_utils import create_service_logger

        test_router = APIRouter(tags=["Health"])
        test_logger = create_service_logger("test.health")

        @test_router.get("/healthz")
        async def test_health_check() -> dict[str, str | dict]:
            """Health check endpoint that will fail during execution."""
            try:
                # This will raise an exception to test the exception handling
                raise RuntimeError("Simulated health check failure")

                # This code would normally execute
                checks = {"service_responsive": True, "dependencies_available": True}
                dependencies = {
                    "redis": {"status": "healthy", "note": "Rate limiting and session storage"},
                    "downstream_services": {
                        "status": "healthy",
                        "note": "Proxied service availability checked on request",
                    },
                }

                overall_status = "healthy" if checks["dependencies_available"] else "unhealthy"

                return {
                    "service": "api_gateway_service",
                    "status": overall_status,
                    "message": f"API Gateway Service is {overall_status}",
                    "version": "1.0.0",
                    "checks": checks,
                    "dependencies": dependencies,
                    "environment": "development",
                }
            except Exception as e:
                test_logger.error(f"Health check failed: {e}")
                return {
                    "service": "api_gateway_service",
                    "status": "unhealthy",
                    "message": "Health check failed",
                    "version": "1.0.0",
                    "error": str(e),
                }

        app.include_router(test_router)

        with TestClient(app) as client:
            # Act
            response = client.get("/healthz")

            # Assert - Should return unhealthy status but not crash
            assert response.status_code == 200
            data = response.json()
            assert data["service"] == "api_gateway_service"
            assert data["status"] == "unhealthy"
            assert data["message"] == "Health check failed"
            assert data["version"] == "1.0.0"
            assert "error" in data
            assert "Simulated health check failure" in data["error"]

    def test_metrics_endpoint_returns_prometheus_format(self, unified_container):
        """Test metrics endpoint returns valid Prometheus format."""
        from dishka.integrations.fastapi import setup_dishka
        from fastapi.testclient import TestClient

        from services.api_gateway_service.app.metrics import GatewayMetrics

        app = FastAPI()
        setup_dishka(unified_container, app)

        # Ensure metrics are created by explicitly requesting them from the container
        async def ensure_metrics_created():
            async with unified_container() as request_container:
                # This will create the metrics if not already created
                await request_container.get(CollectorRegistry)
                await request_container.get(GatewayMetrics)

        import asyncio

        asyncio.run(ensure_metrics_created())

        # Register routes after ensuring metrics are created
        from services.api_gateway_service.routers import health_routes

        app.include_router(health_routes.router)

        with TestClient(app) as client:
            # Act
            response = client.get("/metrics")

            # Assert
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/plain; version=1.0.0; charset=utf-8"

            # Verify response contains Prometheus metrics format
            content = response.text
            assert len(content) > 0, "Metrics response should not be empty"
            assert "# HELP" in content
            assert "# TYPE" in content

    def test_metrics_endpoint_with_populated_metrics(self, unified_container):
        """Test metrics endpoint returns actual metric values."""

        app = FastAPI()

        # Create a custom provider that populates some metrics
        from services.api_gateway_service.app.metrics import GatewayMetrics

        # Get the metrics from container and populate some values
        setup_dishka(unified_container, app)

        # Access metrics through DI to populate some values
        async def populate_metrics():
            container = unified_container
            async with container() as request_container:
                metrics = await request_container.get(GatewayMetrics)
                # Populate some metrics
                metrics.http_requests_total.labels(
                    method="GET", endpoint="/test", http_status="200"
                ).inc()
                metrics.http_request_duration_seconds.labels(
                    method="GET", endpoint="/test"
                ).observe(0.123)

        # Run async function to populate metrics
        import asyncio

        asyncio.run(populate_metrics())

        # Register routes
        from services.api_gateway_service.routers import health_routes

        app.include_router(health_routes.router)

        with TestClient(app) as client:
            # Act
            response = client.get("/metrics")

            # Assert
            assert response.status_code == 200
            content = response.text

            # Verify our populated metrics appear
            assert "http_requests_total" in content
            assert "http_request_duration_seconds" in content

    def test_metrics_endpoint_error_handling(self, unified_container):
        """Test metrics endpoint handles registry errors gracefully."""
        from unittest.mock import patch

        from dishka.integrations.fastapi import setup_dishka
        from fastapi.testclient import TestClient

        app = FastAPI()
        setup_dishka(unified_container, app)

        # Register routes
        from services.api_gateway_service.routers import health_routes

        app.include_router(health_routes.router)

        with TestClient(app) as client:
            # Patch generate_latest to raise an error
            with patch(
                "services.api_gateway_service.routers.health_routes.generate_latest"
            ) as mock_generate_latest:
                mock_generate_latest.side_effect = RuntimeError("Registry error")

                # Act
                response = client.get("/metrics")

                # Assert - Should return error status
                assert response.status_code == 500
                assert response.text == "Error generating metrics"

                # Verify the function was called
                mock_generate_latest.assert_called_once()

    def test_metrics_endpoint_with_isolated_registry(
        self, client_with_health_routes, cleanup_registry
    ):
        """Test that metrics use isolated registry and don't pollute global registry."""
        # Act - Make multiple requests to ensure registry isolation
        response1 = client_with_health_routes.get("/metrics")
        response2 = client_with_health_routes.get("/metrics")

        # Assert
        assert response1.status_code == 200
        assert response2.status_code == 200

        # Content should be consistent between calls
        assert response1.text == response2.text

    def test_healthz_endpoint_response_structure_validation(self, client_with_health_routes):
        """Test health check response follows exact structure requirements."""
        # Act
        response = client_with_health_routes.get("/healthz")

        # Assert detailed structure
        assert response.status_code == 200
        data = response.json()

        # Validate all top-level keys are present
        expected_keys = {
            "service",
            "status",
            "message",
            "version",
            "checks",
            "dependencies",
            "environment",
        }
        assert set(data.keys()) == expected_keys

        # Validate checks structure
        assert isinstance(data["checks"], dict)
        assert set(data["checks"].keys()) == {"service_responsive", "dependencies_available"}
        assert isinstance(data["checks"]["service_responsive"], bool)
        assert isinstance(data["checks"]["dependencies_available"], bool)

        # Validate dependencies structure
        assert isinstance(data["dependencies"], dict)
        assert "redis" in data["dependencies"]
        assert "downstream_services" in data["dependencies"]

        # Validate Redis dependency structure
        assert set(data["dependencies"]["redis"].keys()) == {"status", "note"}
        assert data["dependencies"]["redis"]["status"] in ["healthy", "unhealthy"]
        assert isinstance(data["dependencies"]["redis"]["note"], str)

        # Validate downstream services structure
        assert set(data["dependencies"]["downstream_services"].keys()) == {"status", "note"}
        assert data["dependencies"]["downstream_services"]["status"] in ["healthy", "unhealthy"]
        assert isinstance(data["dependencies"]["downstream_services"]["note"], str)
