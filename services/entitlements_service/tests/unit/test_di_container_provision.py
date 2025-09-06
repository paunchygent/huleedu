"""Behavioral DI container tests without patching internals.

Validates that Dishka resolves the service protocols using provider composition
in line with Rule 075. Avoids network calls by overriding Redis provider.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from huleedu_service_libs.resilience import CircuitBreakerRegistry
from huleedu_service_libs.outbox.manager import OutboxManager
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol
from sqlalchemy.ext.asyncio import AsyncEngine

from services.entitlements_service.di import (
    CoreProvider,
    EntitlementsServiceProvider,
    ImplementationProvider,
    ServiceProvider,
)
from services.entitlements_service.protocols import (
    CreditManagerProtocol,
    EntitlementsRepositoryProtocol,
    PolicyLoaderProtocol,
    RateLimiterProtocol,
    EventPublisherProtocol,
)
from services.entitlements_service.config import Settings


class CoreProviderOverrideForTests(CoreProvider):
    """CoreProvider override to avoid real Redis connections."""

    @provide  # type: ignore[override]
    async def provide_redis_client(self) -> AtomicRedisClientProtocol:  # type: ignore[override]
        client = AsyncMock(spec=AtomicRedisClientProtocol)
        return client

    @provide  # type: ignore[override]
    async def provide_kafka_publisher(
        self,
        settings: Settings,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> KafkaPublisherProtocol:  # type: ignore[override]
        # Return a lightweight mock to avoid creating real Kafka producers
        return AsyncMock(spec=KafkaPublisherProtocol)


class ImplementationProviderOverrideForTests(ImplementationProvider):
    """Implementation override to avoid outbox wiring and Kafka objects."""

    @provide  # type: ignore[override]
    def provide_outbox_manager(self) -> OutboxManager:  # type: ignore[override]
        return AsyncMock(spec=OutboxManager)

    @provide  # type: ignore[override]
    def provide_event_publisher(self) -> EventPublisherProtocol:  # type: ignore[override]
        return AsyncMock(spec=EventPublisherProtocol)


@pytest.fixture()
def test_container() -> any:
    """Compose a container with a mocked Redis client to avoid I/O."""
    mock_engine = AsyncMock(spec=AsyncEngine)
    container = make_async_container(
        CoreProviderOverrideForTests(),
        ImplementationProviderOverrideForTests(),
        ServiceProvider(),
        EntitlementsServiceProvider(engine=mock_engine),
    )
    return container


class TestDIContainerProvision:
    """Verify DI resolves protocol contracts without patching internals."""

    @pytest.mark.asyncio
    async def test_provides_redis_client(self, test_container) -> None:
        client = await test_container.get(AtomicRedisClientProtocol)
        assert client is not None

    @pytest.mark.asyncio
    async def test_provides_kafka_publisher(self, test_container) -> None:
        publisher = await test_container.get(KafkaPublisherProtocol)
        assert publisher is not None
        # Protocol-style behavioral assertion: has publish coroutine/method
        assert hasattr(publisher, "publish")

    @pytest.mark.asyncio
    async def test_provides_repository(self, test_container) -> None:
        async with test_container() as request_container:
            repo = await request_container.get(EntitlementsRepositoryProtocol)
            assert repo is not None

    @pytest.mark.asyncio
    async def test_provides_policy_loader(self, test_container) -> None:
        async with test_container() as request_container:
            loader = await request_container.get(PolicyLoaderProtocol)
            assert loader is not None

    @pytest.mark.asyncio
    async def test_provides_rate_limiter(self, test_container) -> None:
        async with test_container() as request_container:
            limiter = await request_container.get(RateLimiterProtocol)
            assert limiter is not None

    @pytest.mark.asyncio
    async def test_provides_credit_manager(self, test_container) -> None:
        async with test_container() as request_container:
            manager = await request_container.get(CreditManagerProtocol)
            assert manager is not None

    @pytest.mark.asyncio
    async def test_container_close(self, test_container) -> None:
        # Ensure container closes cleanly
        await test_container.close()
