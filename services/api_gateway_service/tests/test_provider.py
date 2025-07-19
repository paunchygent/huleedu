"""Test provider for API Gateway Service tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import httpx
from dishka import Provider, Scope, provide
from fastapi import Request
from prometheus_client import CollectorRegistry

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from services.api_gateway_service.app.auth_provider import BearerToken
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.config import Settings
from services.api_gateway_service.protocols import HttpClientProtocol, MetricsProtocol


class TestAuthProvider(Provider):
    """
    Test authentication provider that provides mock user_id and correlation_id.

    This provider replaces the real AuthProvider in tests and provides
    consistent authentication dependencies without requiring real JWT tokens.
    """

    def __init__(self, user_id: str = "test-user-123", correlation_id: UUID | None = None):
        super().__init__()
        self.user_id = user_id
        self.correlation_id = correlation_id or uuid4()

    @provide(scope=Scope.REQUEST)
    def provide_mock_request(self) -> Request:
        """Provide a mock request with correlation_id in state."""
        mock_request = Mock(spec=Request)
        mock_request.state.correlation_id = self.correlation_id
        mock_request.headers = {"Authorization": f"Bearer test-token-{self.user_id}"}
        return mock_request

    @provide(scope=Scope.REQUEST, provides=str)
    def provide_user_id(self) -> str:
        """Provide mock user ID for testing - replaces AuthProvider.provide_user_id."""
        return self.user_id

    @provide(scope=Scope.REQUEST)
    def provide_correlation_id(self) -> UUID:
        """Provide mock correlation ID for testing."""
        return self.correlation_id

    @provide(scope=Scope.REQUEST)
    def extract_bearer_token(self) -> BearerToken:
        """Provide mock bearer token for testing."""
        return BearerToken(f"test-token-{self.user_id}")


class TestApiGatewayProvider(Provider):
    """
    Test provider for API Gateway infrastructure dependencies.

    Provides mocked versions of all infrastructure components (HTTP client,
    Redis, Kafka, metrics) for isolated testing.
    """

    scope = Scope.APP

    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings(
            SERVICE_NAME="api_gateway_service_test",
            REDIS_URL="redis://localhost:6379",
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            RESULT_AGGREGATOR_URL="http://localhost:8084",
            CMS_API_URL="http://localhost:8085",
            FILE_SERVICE_URL="http://localhost:8086",
            JWT_SECRET_KEY="test-secret-key",
            JWT_ALGORITHM="HS256",
        )

    @provide
    def get_config(self) -> Settings:
        """Provide test settings."""
        return self.settings

    @provide
    async def get_http_client(self) -> AsyncIterator[HttpClientProtocol]:
        """Provide real HTTP client for tests that use respx mocking."""
        async with httpx.AsyncClient() as client:
            yield client

    @provide
    async def get_redis_client(self) -> AsyncIterator[AtomicRedisClientProtocol]:
        """Provide mocked Redis client."""
        mock_redis = AsyncMock(spec=AtomicRedisClientProtocol)
        yield mock_redis

    @provide
    async def get_kafka_bus(self) -> AsyncIterator[KafkaBus]:
        """Provide mocked Kafka bus."""
        mock_kafka = AsyncMock(spec=KafkaBus)
        yield mock_kafka

    @provide
    def provide_metrics(self) -> MetricsProtocol:
        """Provide mocked metrics following protocol-based testing patterns."""
        from typing import cast
        from unittest.mock import Mock

        mock_metrics = Mock(spec=GatewayMetrics)

        # Create mock Counter and Histogram objects with labels() method
        def create_mock_counter():
            mock_counter = Mock()
            mock_counter.labels.return_value = mock_counter
            mock_counter.inc.return_value = None
            return mock_counter

        def create_mock_histogram():
            mock_histogram = Mock()
            mock_histogram.labels.return_value = mock_histogram
            mock_histogram.time.return_value.__enter__ = Mock()
            mock_histogram.time.return_value.__exit__ = Mock(return_value=None)
            return mock_histogram

        # Configure all protocol properties
        mock_metrics.http_requests_total = create_mock_counter()
        mock_metrics.http_request_duration_seconds = create_mock_histogram()
        mock_metrics.events_published_total = create_mock_counter()
        mock_metrics.downstream_service_calls_total = create_mock_counter()
        mock_metrics.downstream_service_call_duration_seconds = create_mock_histogram()
        mock_metrics.api_errors_total = create_mock_counter()

        return cast(MetricsProtocol, mock_metrics)

    @provide
    def provide_registry(self) -> CollectorRegistry:
        """Provide isolated Prometheus registry."""
        return CollectorRegistry()


class TestHttpClientProvider(Provider):
    """
    Provider for custom HTTP client mocking when specific HTTP behavior is needed.

    Use this when you need to control HTTP client responses in tests.
    Includes all infrastructure dependencies to work standalone.
    """

    scope = Scope.APP

    def __init__(self, mock_http_client: AsyncMock, settings: Settings | None = None):
        super().__init__()
        self.mock_http_client = mock_http_client
        self.settings = settings or Settings(
            SERVICE_NAME="api_gateway_service_test",
            REDIS_URL="redis://localhost:6379",
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            RESULT_AGGREGATOR_URL="http://localhost:8084",
            CMS_API_URL="http://localhost:8085",
            FILE_SERVICE_URL="http://localhost:8086",
            JWT_SECRET_KEY="test-secret-key",
            JWT_ALGORITHM="HS256",
        )

    @provide
    def get_config(self) -> Settings:
        """Provide test settings."""
        return self.settings

    @provide
    async def get_http_client(self) -> AsyncIterator[HttpClientProtocol]:
        """Provide mocked HTTP client."""
        yield self.mock_http_client

    @provide
    async def get_redis_client(self) -> AsyncIterator[AtomicRedisClientProtocol]:
        """Provide mocked Redis client."""
        mock_redis = AsyncMock(spec=AtomicRedisClientProtocol)
        yield mock_redis

    @provide
    async def get_kafka_bus(self) -> AsyncIterator[KafkaBus]:
        """Provide mocked Kafka bus."""
        mock_kafka = AsyncMock(spec=KafkaBus)
        yield mock_kafka

    @provide
    def provide_metrics(self) -> MetricsProtocol:
        """Provide metrics with isolated registry."""
        return GatewayMetrics(registry=CollectorRegistry())

    @provide
    def provide_registry(self) -> CollectorRegistry:
        """Provide isolated Prometheus registry."""
        return CollectorRegistry()
