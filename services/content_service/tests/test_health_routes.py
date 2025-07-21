"""Tests for Content Service health routes with dependency injection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dishka import Provider, Scope, make_async_container
from prometheus_client import CollectorRegistry
from quart import Quart
from quart_dishka import QuartDishka

from services.content_service.api.health_routes import health_bp
from services.content_service.config import Settings


@pytest.fixture
async def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.CONTENT_STORE_ROOT_PATH = Path("/test/content/store")
    return settings


@pytest.fixture
async def test_app(mock_settings: Settings) -> Quart:
    """Create test Quart app with DI configured."""
    app = Quart(__name__)
    app.register_blueprint(health_bp)

    # Create a custom provider for testing
    provider = Provider()
    provider.provide(lambda: mock_settings, scope=Scope.APP, provides=Settings)
    provider.provide(lambda: CollectorRegistry(), scope=Scope.APP, provides=CollectorRegistry)

    # Create container and setup Dishka
    container = make_async_container(provider)
    QuartDishka(app=app, container=container)

    return app


class TestHealthRoutes:
    """Test suite for health check routes with dependency injection."""

    async def test_health_check_healthy_with_injected_settings(self, test_app: Quart) -> None:
        """Test health check returns healthy status with injected settings."""
        # Mock the Path methods
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "is_dir", return_value=True),
        ):
            async with test_app.test_client() as client:
                response = await client.get("/healthz")

                assert response.status_code == 200
                data = await response.get_json()

                assert data["service"] == "content_service"
                assert data["status"] == "healthy"
                assert data["checks"]["service_responsive"] is True
                assert data["checks"]["dependencies_available"] is True
                assert data["dependencies"]["storage"]["status"] == "healthy"
                assert "/test/content/store" in data["dependencies"]["storage"]["path"]

    async def test_health_check_unhealthy_storage_with_injected_settings(
        self, test_app: Quart
    ) -> None:
        """Test health check returns unhealthy when storage path doesn't exist."""
        # Mock the Path methods to simulate missing directory
        with (
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "is_dir", return_value=False),
        ):
            async with test_app.test_client() as client:
                response = await client.get("/healthz")

                assert response.status_code == 503
                data = await response.get_json()

                assert data["service"] == "content_service"
                assert data["status"] == "unhealthy"
                assert data["checks"]["dependencies_available"] is False
                assert data["dependencies"]["storage"]["status"] == "unhealthy"
                assert "not accessible" in data["dependencies"]["storage"]["error"]

    async def test_health_check_storage_exception_with_injected_settings(
        self, test_app: Quart
    ) -> None:
        """Test health check handles storage check exceptions gracefully."""
        # Mock Path.exists to raise an exception
        with patch.object(Path, "exists", side_effect=Exception("Storage access error")):
            async with test_app.test_client() as client:
                response = await client.get("/healthz")

                assert response.status_code == 503
                data = await response.get_json()

                assert data["service"] == "content_service"
                assert data["status"] == "unhealthy"
                assert data["checks"]["dependencies_available"] is False
                assert data["dependencies"]["storage"]["status"] == "unhealthy"
                assert "Storage access error" in data["dependencies"]["storage"]["error"]

    async def test_metrics_endpoint_with_injected_registry(self, test_app: Quart) -> None:
        """Test metrics endpoint works with injected registry."""
        async with test_app.test_client() as client:
            response = await client.get("/metrics")

            assert response.status_code == 200
            assert response.content_type == "text/plain; version=0.0.4; charset=utf-8"

            # Check that response contains Prometheus metrics format
            metrics_text = await response.get_data(as_text=True)
            assert "# HELP" in metrics_text or metrics_text == ""  # Empty registry is valid
