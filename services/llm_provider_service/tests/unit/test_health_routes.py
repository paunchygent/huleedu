"""Unit tests for LLM Provider Service health routes.

Tests the /healthz and /metrics endpoints with Dishka DI mocking.
Follows Rule 075 test creation methodology and Rule 070 testing standards.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from common_core import Environment
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.protocols import RedisClientProtocol
from prometheus_client import CONTENT_TYPE_LATEST
from pydantic import SecretStr
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.llm_provider_service.api.health_routes import health_bp
from services.llm_provider_service.config import Settings


def create_test_settings(
    *,
    anthropic_enabled: bool = True,
    anthropic_api_key: str = "sk-test-anthropic",
    openai_enabled: bool = True,
    openai_api_key: str = "sk-test-openai",
    google_enabled: bool = False,
    google_api_key: str = "",
    openrouter_enabled: bool = False,
    openrouter_api_key: str = "",
    use_mock_llm: bool = False,
    allow_mock_provider: bool = True,
    mock_provider_seed: int = 42,
) -> Settings:
    """Create Settings instance with controlled test values.

    Overrides only the fields used by health_routes.py:
    - SERVICE_NAME, ENVIRONMENT (used in response)
    - Provider enabled flags and API keys (used in provider status)
    - Mock provider settings (used in mock_provider status)
    """
    return Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.DEVELOPMENT,
        ANTHROPIC_ENABLED=anthropic_enabled,
        ANTHROPIC_API_KEY=SecretStr(anthropic_api_key),
        OPENAI_ENABLED=openai_enabled,
        OPENAI_API_KEY=SecretStr(openai_api_key),
        GOOGLE_ENABLED=google_enabled,
        GOOGLE_API_KEY=SecretStr(google_api_key),
        OPENROUTER_ENABLED=openrouter_enabled,
        OPENROUTER_API_KEY=SecretStr(openrouter_api_key),
        USE_MOCK_LLM=use_mock_llm,
        ALLOW_MOCK_PROVIDER=allow_mock_provider,
        MOCK_PROVIDER_SEED=mock_provider_seed,
        # Minimal valid values for required Settings fields
        REDIS_URL="redis://localhost:6379",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
    )


class TestHealthRoutes:
    """Tests for /healthz endpoint covering all response scenarios."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock RedisClientProtocol that successfully pings."""
        mock = AsyncMock(spec=RedisClientProtocol)
        mock.ping.return_value = True
        return mock

    @pytest.fixture
    def mock_redis_client_failing(self) -> AsyncMock:
        """Create mock RedisClientProtocol that fails ping."""
        mock = AsyncMock(spec=RedisClientProtocol)
        mock.ping.side_effect = ConnectionError("Redis connection failed")
        return mock

    @pytest.fixture
    async def app_client_healthy(
        self,
        mock_redis_client: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client with healthy Redis and configured providers."""
        test_settings = create_test_settings(
            anthropic_enabled=True,
            anthropic_api_key="sk-test-anthropic",
            openai_enabled=True,
            openai_api_key="sk-test-openai",
        )

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

            @provide(scope=Scope.APP)
            def provide_redis_client(self) -> RedisClientProtocol:
                return mock_redis_client

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(health_bp)

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            yield client

        await container.close()

    @pytest.fixture
    async def app_client_redis_down(
        self,
        mock_redis_client_failing: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client with failing Redis."""
        test_settings = create_test_settings()

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

            @provide(scope=Scope.APP)
            def provide_redis_client(self) -> RedisClientProtocol:
                return mock_redis_client_failing

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(health_bp)

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            yield client

        await container.close()

    @pytest.fixture
    async def app_client_no_providers(
        self,
        mock_redis_client: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client with no LLM providers configured."""
        test_settings = create_test_settings(
            anthropic_enabled=False,
            anthropic_api_key="",
            openai_enabled=False,
            openai_api_key="",
            google_enabled=False,
            google_api_key="",
            openrouter_enabled=False,
            openrouter_api_key="",
        )

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

            @provide(scope=Scope.APP)
            def provide_redis_client(self) -> RedisClientProtocol:
                return mock_redis_client

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(health_bp)

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            yield client

        await container.close()

    @pytest.fixture
    async def app_client_mock_mode(
        self,
        mock_redis_client: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client with mock LLM mode enabled."""
        test_settings = create_test_settings(
            use_mock_llm=True,
            allow_mock_provider=True,
            mock_provider_seed=123,
        )

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

            @provide(scope=Scope.APP)
            def provide_redis_client(self) -> RedisClientProtocol:
                return mock_redis_client

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(health_bp)

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            yield client

        await container.close()

    @pytest.mark.asyncio
    async def test_healthz_returns_healthy_with_redis_and_provider(
        self,
        app_client_healthy: QuartTestClient,
    ) -> None:
        """Test /healthz returns 200 when Redis is up and providers are configured."""
        response = await app_client_healthy.get("/healthz")

        assert response.status_code == 200

        data: dict[str, Any] = await response.get_json()
        assert data["status"] == "healthy"
        assert data["message"] == "LLM Provider Service is healthy"
        assert data["service"] == "llm_provider_service"
        assert data["version"] == "1.0.0"
        assert data["environment"] == "development"

        # Verify checks structure
        assert data["checks"]["service_responsive"] is True
        assert data["checks"]["dependencies_available"] is True

        # Verify dependencies structure
        assert data["dependencies"]["redis"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_healthz_returns_unhealthy_when_redis_down(
        self,
        app_client_redis_down: QuartTestClient,
    ) -> None:
        """Test /healthz returns 503 when Redis connection fails."""
        response = await app_client_redis_down.get("/healthz")

        assert response.status_code == 503

        data: dict[str, Any] = await response.get_json()
        assert data["status"] == "unhealthy"
        assert data["message"] == "LLM Provider Service is unhealthy"
        assert data["checks"]["dependencies_available"] is False

        # Verify Redis error is captured
        assert data["dependencies"]["redis"]["status"] == "unhealthy"
        assert "error" in data["dependencies"]["redis"]
        assert "Redis connection failed" in data["dependencies"]["redis"]["error"]

    @pytest.mark.asyncio
    async def test_healthz_returns_unhealthy_when_no_providers_configured(
        self,
        app_client_no_providers: QuartTestClient,
    ) -> None:
        """Test /healthz returns 503 when no LLM providers are configured."""
        response = await app_client_no_providers.get("/healthz")

        assert response.status_code == 503

        data: dict[str, Any] = await response.get_json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["dependencies_available"] is False
        assert "warnings" in data
        assert "No LLM providers configured" in data["warnings"]

    @pytest.mark.asyncio
    async def test_healthz_includes_provider_status_flags(
        self,
        app_client_healthy: QuartTestClient,
    ) -> None:
        """Test /healthz includes enabled/configured flags for all providers."""
        response = await app_client_healthy.get("/healthz")

        assert response.status_code == 200

        data: dict[str, Any] = await response.get_json()
        providers = data["providers"]

        # Anthropic: enabled=True, configured=True (has API key)
        assert providers["anthropic"]["enabled"] is True
        assert providers["anthropic"]["configured"] is True

        # OpenAI: enabled=True, configured=True (has API key)
        assert providers["openai"]["enabled"] is True
        assert providers["openai"]["configured"] is True

        # Google: enabled=False in test settings
        assert providers["google"]["enabled"] is False
        assert providers["google"]["configured"] is False

        # OpenRouter: enabled=False in test settings
        assert providers["openrouter"]["enabled"] is False
        assert providers["openrouter"]["configured"] is False

    @pytest.mark.asyncio
    async def test_healthz_includes_mock_provider_status(
        self,
        app_client_mock_mode: QuartTestClient,
    ) -> None:
        """Test /healthz includes mock_mode and mock_provider status."""
        response = await app_client_mock_mode.get("/healthz")

        assert response.status_code == 200

        data: dict[str, Any] = await response.get_json()

        # Verify mock_mode is True
        assert data["mock_mode"] is True

        # Verify mock_provider structure
        mock_provider = data["mock_provider"]
        assert mock_provider["allowed"] is True
        assert mock_provider["registered"] is True
        assert mock_provider["seed"] == 123


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock RedisClientProtocol."""
        mock = AsyncMock(spec=RedisClientProtocol)
        mock.ping.return_value = True
        return mock

    @pytest.fixture
    async def app_client(
        self,
        mock_redis_client: AsyncMock,
    ) -> AsyncGenerator[QuartTestClient, None]:
        """Create test client for metrics endpoint."""
        test_settings = create_test_settings()

        class TestProvider(Provider):
            @provide(scope=Scope.APP)
            def provide_settings(self) -> Settings:
                return test_settings

            @provide(scope=Scope.APP)
            def provide_redis_client(self) -> RedisClientProtocol:
                return mock_redis_client

        test_app = Quart(__name__)
        test_app.config.update({"TESTING": True})
        test_app.register_blueprint(health_bp)

        container = make_async_container(TestProvider())
        QuartDishka(app=test_app, container=container)

        async with test_app.test_client() as client:
            yield client

        await container.close()

    @pytest.mark.asyncio
    async def test_metrics_endpoint_returns_prometheus_format(
        self,
        app_client: QuartTestClient,
    ) -> None:
        """Test /metrics returns Prometheus-formatted metrics."""
        response = await app_client.get("/metrics")

        assert response.status_code == 200

        # Verify Content-Type is Prometheus format
        content_type = response.headers.get("Content-Type")
        assert content_type == CONTENT_TYPE_LATEST

        # Verify response is text (may be empty in test environment)
        content = await response.get_data(as_text=True)
        assert content is not None
