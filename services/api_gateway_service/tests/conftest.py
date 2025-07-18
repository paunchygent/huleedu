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
                    return f"ws:{user_id}"

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
    """Mock Redis client fixture for WebSocket and other tests."""

    # Create a simple mock object that tracks calls manually
    class MockRedisClient:
        def __init__(self):
            self.get_user_channel_calls = []
            self.subscribe_calls = []
            self._mock_pubsub = AsyncMock()
            self._mock_pubsub.get_message = AsyncMock(return_value=None)

        def get_user_channel(self, user_id):
            self.get_user_channel_calls.append(user_id)
            return f"ws:{user_id}"

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
