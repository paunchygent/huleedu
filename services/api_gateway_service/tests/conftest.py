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
from huleedu_service_libs.redis_client import RedisClient
from services.api_gateway_service.app.metrics import GatewayMetrics
from services.api_gateway_service.config import Settings, settings


class UnifiedMockApiGatewayProvider(Provider):
    """
    Unified mock provider for API Gateway tests.
    
    Follows Rule 042.3.4 (DI Provider Pattern) by mirroring the production
    ApiGatewayProvider interface exactly, ensuring test/prod consistency.
    """

    scope = Scope.APP

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
    async def get_redis_client(self) -> AsyncIterator[AtomicRedisClientProtocol]:
        """Provide mocked Redis client following Rule 070.1 (Protocol-based mocking)."""
        client = AsyncMock(spec=RedisClient)
        yield cast(AtomicRedisClientProtocol, client)

    @provide
    async def get_kafka_bus(self) -> AsyncIterator[KafkaBus]:
        """Provide mocked Kafka bus following Rule 070.1 (Protocol-based mocking)."""
        bus = AsyncMock(spec=KafkaBus)
        yield bus

    @provide(scope=Scope.APP)
    def provide_registry(self) -> CollectorRegistry:
        """Provide isolated Prometheus registry for test independence."""
        return CollectorRegistry()

    @provide(scope=Scope.APP)
    def provide_metrics(self, registry: CollectorRegistry) -> GatewayMetrics:
        """Provide GatewayMetrics with isolated registry matching production scope."""
        return GatewayMetrics(registry=registry)


@pytest.fixture
async def unified_container():
    """
    Unified DI container fixture for all API Gateway tests.

    Ensures consistent dependency injection setup across all test files,
    following Rule 042.2.1 (Protocol-based dependencies).
    """
    test_container = make_async_container(UnifiedMockApiGatewayProvider())
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
