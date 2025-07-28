"""
Unified test configuration for API Gateway Service.

Implements Rule 042.2.1 (Protocol-based dependencies) with consistent
mock provider that mirrors production ApiGatewayProvider interface.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from dishka import Provider, Scope, make_async_container, provide
from prometheus_client import CollectorRegistry

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.config import Settings, settings


class UnifiedMockApiGatewayProvider(Provider):
    """
    Unified mock provider for API Gateway tests.

    Follows Rule 042.3.4 (DI Provider Pattern) by mirroring the production
    ApiGatewayProvider interface exactly, ensuring test/prod consistency.
    """

    scope = Scope.APP

    def __init__(self, redis_client_mock=None, kafka_bus_mock=None):
        super().__init__()
        # Accept mocks via constructor instead of storing internally
        self._redis_client_mock = redis_client_mock
        self._kafka_bus_mock = kafka_bus_mock

    @provide
    def get_config(self) -> Settings:
        """Provide real settings for test consistency."""
        return settings

    @provide
    async def get_http_client(self) -> AsyncIterator[httpx.AsyncClient]:
        """Provide real HTTP client for actual HTTP calls in tests."""
        async with httpx.AsyncClient() as client:
            yield client

    @provide
    async def get_redis_client(self, config: Settings) -> AsyncIterator[AtomicRedisClientProtocol]:
        """Provide mocked Redis client following Rule 070.1 (Protocol-based mocking).

        Matches production provider signature exactly to ensure proper DI resolution.
        """

        if self._redis_client_mock is None:
            # Create default mock if none provided
            class MockRedisClient:
                def __init__(self):
                    self.get_user_channel_calls = []
                    self.subscribe_calls = []
                    self._mock_pubsub = AsyncMock()
                    self._mock_pubsub.get_message = AsyncMock(return_value=None)

                def get_user_channel(self, user_id):
                    self.get_user_channel_calls.append(user_id)
                    return f"user:{user_id}"

                async def subscribe(self, channel_name):
                    self.subscribe_calls.append(channel_name)
                    yield self._mock_pubsub

            self._redis_client_mock = MockRedisClient()

        # Use AsyncIterator pattern to match production
        yield cast(AtomicRedisClientProtocol, self._redis_client_mock)

    @provide
    async def get_kafka_bus(self) -> AsyncIterator[KafkaBus]:
        """Provide mocked Kafka bus following Rule 070.1 (Protocol-based mocking)."""
        if self._kafka_bus_mock is None:
            # Create default mock if none provided
            self._kafka_bus_mock = AsyncMock(spec=KafkaBus)

        yield self._kafka_bus_mock

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        """Provide isolated Prometheus registry for test independence."""
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    def provide_metrics(self, registry: CollectorRegistry) -> GatewayMetrics:
        """Provide GatewayMetrics with isolated registry matching production scope."""
        return GatewayMetrics(registry=registry)


@pytest.fixture
def mock_redis_client():
    """Mock Redis client fixture for tests."""

    # Create a simple mock object that tracks calls manually
    class MockRedisClient:
        def __init__(self):
            self.get_user_channel_calls = []
            self.subscribe_calls = []
            self._mock_pubsub = AsyncMock()
            self._mock_pubsub.get_message = AsyncMock(return_value=None)

        def get_user_channel(self, user_id):
            self.get_user_channel_calls.append(user_id)
            return f"user:{user_id}"

        async def subscribe(self, channel_name):
            self.subscribe_calls.append(channel_name)
            yield self._mock_pubsub

    client = MockRedisClient()
    return client


@pytest.fixture
def mock_kafka_bus():
    """Mock Kafka bus fixture for batch and other tests."""
    return AsyncMock(spec=KafkaBus)


@pytest.fixture
async def unified_container(mock_redis_client, mock_kafka_bus):
    """
    Unified DI container fixture for all API Gateway tests.

    Ensures consistent dependency injection setup across all test files,
    following Rule 042.2.1 (Protocol-based dependencies).
    """
    provider = UnifiedMockApiGatewayProvider(
        redis_client_mock=mock_redis_client, kafka_bus_mock=mock_kafka_bus
    )
    test_container = make_async_container(provider)
    yield test_container
    await test_container.close()


@pytest.fixture
def cleanup_registry():
    """
    Clean up Prometheus registry after tests with metrics.

    Ensures test isolation and prevents metric collision between tests.
    """
    yield
    # Registry cleanup happens automatically with isolated CollectorRegistry


def create_test_app_with_isolated_registry(registry: CollectorRegistry):
    """Create a test FastAPI app with isolated Prometheus registry.

    This function creates an app similar to create_app() but uses
    the provided isolated registry to prevent metric collisions in tests.

    Args:
        registry: Isolated CollectorRegistry for test metrics

    Returns:
        FastAPI app configured for testing with isolated metrics
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    from huleedu_service_libs.error_handling.fastapi import (
        register_error_handlers as register_fastapi_error_handlers,
    )
    from services.api_gateway_service.app.startup_setup import (
        setup_standard_metrics_middleware,
        setup_tracing_and_middleware,
    )
    from services.api_gateway_service.config import settings

    from ..app.middleware import CorrelationIDMiddleware
    from ..app.rate_limiter import limiter
    from ..routers import batch_routes, class_routes, file_routes, status_routes
    from ..routers.health_routes import router as health_router

    app = FastAPI(
        title=settings.SERVICE_NAME,
        version="1.0.0",
    )

    # Register error handlers
    register_fastapi_error_handlers(app)

    # Add Correlation ID Middleware (must be early in chain)
    app.add_middleware(CorrelationIDMiddleware)

    # Setup distributed tracing and tracing middleware (second in chain)
    setup_tracing_and_middleware(app)

    # Setup standard HTTP metrics middleware with isolated registry (third in chain)
    setup_standard_metrics_middleware(app, registry=registry)

    # Add Rate Limiting Middleware
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(_request: Request, exc: RateLimitExceeded):
        return JSONResponse(
            status_code=429,
            content={"detail": f"Rate limit exceeded: {exc.detail}"},
        )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # Include routers
    app.include_router(health_router, tags=["Health"])
    app.include_router(class_routes.router, prefix="/v1", tags=["Classes"])
    app.include_router(status_routes.router, prefix="/v1", tags=["Status"])
    app.include_router(batch_routes.router, prefix="/v1", tags=["Batches"])
    app.include_router(file_routes.router, prefix="/v1", tags=["Files"])

    return app
