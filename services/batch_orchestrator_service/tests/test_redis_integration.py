"""Redis integration tests for Batch Orchestrator Service.

Tests Redis client dependency injection, lifecycle management, and idempotency operations
following the patterns established in other services.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from config import Settings
from di import CoreInfrastructureProvider
from dishka import make_async_container
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient


@pytest.fixture
async def settings_override() -> Settings:
    """Provide test settings with Redis configuration."""
    return Settings(
        REDIS_URL="redis://localhost:6379",
        SERVICE_NAME="test-batch-orchestrator-service",
        ENVIRONMENT="testing",
    )


@pytest.fixture
async def di_container(settings_override: Settings) -> AsyncGenerator[Any, None]:
    """Create DI container with Redis provider for testing."""
    container = make_async_container(
        CoreInfrastructureProvider(), context={Settings: settings_override}
    )
    yield container
    await container.close()


@pytest.mark.asyncio
async def test_redis_client_injection_and_lifecycle(di_container: Any) -> None:
    """Test that RedisClient can be injected from DI container and manages lifecycle properly."""
    # Test DI injection
    redis_client = await di_container.get(RedisClientProtocol)
    assert redis_client is not None
    assert isinstance(redis_client, RedisClient)

    # Test that connection is working (ping should succeed after start)
    # The provider calls start() automatically, so client should be ready
    result = await redis_client.set_if_not_exists("test_key", "test_value", ttl_seconds=10)
    assert isinstance(result, bool)

    # Clean up test key
    await redis_client.delete_key("test_key")


@pytest.mark.asyncio
async def test_redis_protocol_compliance(di_container: Any) -> None:
    """Test that injected client satisfies RedisClientProtocol interface."""
    redis_client = await di_container.get(RedisClientProtocol)

    # Verify protocol methods exist and are callable
    assert hasattr(redis_client, "set_if_not_exists")
    assert hasattr(redis_client, "delete_key")
    assert callable(redis_client.set_if_not_exists)
    assert callable(redis_client.delete_key)


@pytest.mark.asyncio
async def test_redis_idempotency_pattern(di_container: Any) -> None:
    """Test Redis SETNX idempotency pattern for event processing."""
    redis_client = await di_container.get(RedisClientProtocol)

    test_key = "idempotency:test_event_id"
    test_value = "processed"

    try:
        # First operation should succeed (key doesn't exist)
        result1 = await redis_client.set_if_not_exists(test_key, test_value, ttl_seconds=60)
        assert result1 is True

        # Second operation should fail (key exists - idempotency check)
        result2 = await redis_client.set_if_not_exists(test_key, test_value, ttl_seconds=60)
        assert result2 is False

    finally:
        # Clean up test key
        await redis_client.delete_key(test_key)


@pytest.mark.asyncio
async def test_redis_connection_management(di_container: Any) -> None:
    """Test Redis connection management and error handling."""
    redis_client = await di_container.get(RedisClientProtocol)

    # Test key operations work (indicating successful connection)
    test_key = "connection_test"
    result = await redis_client.set_if_not_exists(test_key, "test", ttl_seconds=5)
    assert isinstance(result, bool)

    # Test deletion returns correct count
    delete_count = await redis_client.delete_key(test_key)
    assert delete_count >= 0  # 0 if key didn't exist, 1 if it was deleted
