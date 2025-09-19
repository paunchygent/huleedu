"""Tests for health check routes with dependency injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from common_core.config_enums import Environment
from dishka import Provider, Scope, make_async_container
from huleedu_service_libs.quart_app import HuleEduApp
from prometheus_client import CollectorRegistry
from quart_dishka import QuartDishka

from services.spellchecker_service.api.health_routes import health_bp
from services.spellchecker_service.config import Settings


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    return Settings(
        SERVICE_NAME="test-spellchecker",
        ENVIRONMENT=Environment.TESTING,
        VERSION="2.0.0",
    )


@pytest.fixture
async def test_app(mock_settings: Settings) -> HuleEduApp:
    """Create test Quart app with DI configured."""
    app = HuleEduApp(__name__)
    app.register_blueprint(health_bp)

    # Create mock database engine
    mock_engine = Mock(spec=["begin", "dispose", "pool"])
    mock_connection = AsyncMock()
    mock_connection.execute.return_value = Mock(fetchone=Mock(return_value=(1,)))

    # Create an async context manager for begin()
    mock_begin_cm = AsyncMock()
    mock_begin_cm.__aenter__.return_value = mock_connection
    mock_engine.begin.return_value = mock_begin_cm

    mock_engine.pool = Mock(num_overflow=1, size=10, checked_in_connections=5)
    app.database_engine = mock_engine

    # Create a custom provider for testing
    provider = Provider()
    provider.provide(lambda: mock_settings, scope=Scope.APP, provides=Settings)
    provider.provide(lambda: CollectorRegistry(), scope=Scope.APP, provides=CollectorRegistry)

    # Create container and setup Dishka
    container = make_async_container(provider)
    QuartDishka(app=app, container=container)

    return app


@pytest.fixture
async def test_app_with_db_failure(mock_settings: Settings) -> HuleEduApp:
    """Create test Quart app with database that fails."""
    app = HuleEduApp(__name__)
    app.register_blueprint(health_bp)

    # Create mock database engine that fails
    mock_engine = Mock(spec=["begin", "dispose", "pool"])
    mock_engine.begin.side_effect = Exception("Database connection failed")
    app.database_engine = mock_engine

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

    async def test_health_check_with_injected_settings(self, test_app: HuleEduApp) -> None:
        """Test health check endpoint returns service info from injected settings."""
        async with test_app.test_client() as client:
            response = await client.get("/healthz")
            data = await response.get_json()

            assert response.status_code == 200
            assert data["service"] == "test-spellchecker"
            assert data["environment"] == "testing"
            assert data["version"] == "2.0.0"
            assert data["status"] == "healthy"
            assert data["checks"]["service_responsive"] is True
            assert data["checks"]["dependencies_available"] is True
            assert "database" in data["dependencies"]
            assert "kafka" in data["dependencies"]

    async def test_health_check_database_failure(
        self, test_app_with_db_failure: HuleEduApp
    ) -> None:
        """Test health check when database is unavailable."""
        async with test_app_with_db_failure.test_client() as client:
            response = await client.get("/healthz")
            data = await response.get_json()

            assert response.status_code == 503
            assert data["service"] == "test-spellchecker"
            assert data["status"] == "unhealthy"
            assert data["checks"]["dependencies_available"] is False
            assert data["dependencies"]["database"]["status"] == "unhealthy"

    async def test_metrics_endpoint(self, test_app: HuleEduApp) -> None:
        """Test metrics endpoint returns prometheus metrics."""
        async with test_app.test_client() as client:
            response = await client.get("/metrics")

            assert response.status_code == 200
            expected_media = "text/plain"
            assert response.content_type.startswith(expected_media)
            assert "charset=utf-8" in response.content_type
