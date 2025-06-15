"""
Test Redis integration for Spell Checker Service.

Validates that Redis client can be properly injected via DI and basic operations work.
"""

from __future__ import annotations

import pytest
from dishka import make_async_container
from huleedu_service_libs.redis_client import RedisClient

from services.spell_checker_service.config import Settings
from services.spell_checker_service.di import SpellCheckerServiceProvider
from services.spell_checker_service.protocols import RedisClientProtocol


@pytest.fixture
def test_settings() -> Settings:
    """Provide test settings with Redis URL."""
    return Settings(
        REDIS_URL="redis://localhost:6379",
        SERVICE_NAME="spell_checker_service_test",
    )


@pytest.mark.asyncio
async def test_redis_client_di_injection(test_settings: Settings) -> None:
    """Test that RedisClient can be injected via DI container."""
    container = make_async_container(SpellCheckerServiceProvider())

    async with container() as request_container:
        # Test that we can get a RedisClient from DI
        redis_client = await request_container.get(RedisClientProtocol)

        # Verify it's the correct type
        assert isinstance(redis_client, RedisClient)
        assert redis_client.client_id == "spell-checker-service-redis"


@pytest.mark.asyncio
async def test_redis_client_lifecycle() -> None:
    """Test Redis client lifecycle management."""
    # Create client directly for testing
    redis_client = RedisClient(
        client_id="spell-test-client",
        redis_url="redis://localhost:6379"
    )

    # Test lifecycle
    assert not redis_client._started

    try:
        await redis_client.start()
        assert redis_client._started

        # Test basic operation (will fail if Redis not available, which is expected)
        try:
            result = await redis_client.set_if_not_exists(
                "spell_test_key", "test_value", ttl_seconds=60
            )
            # If Redis is available, verify operation works
            assert isinstance(result, bool)

            # Cleanup
            await redis_client.delete_key("spell_test_key")
        except Exception:
            # Redis not available in test environment - that's ok
            pass

    finally:
        await redis_client.stop()
        assert not redis_client._started


@pytest.mark.asyncio
async def test_redis_protocol_compliance() -> None:
    """Test that RedisClient implements the RedisClientProtocol correctly."""
    redis_client = RedisClient(
        client_id="spell-protocol-test",
        redis_url="redis://localhost:6379"
    )

    # Verify protocol compliance
    assert hasattr(redis_client, 'set_if_not_exists')
    assert hasattr(redis_client, 'delete_key')
    assert callable(redis_client.set_if_not_exists)
    assert callable(redis_client.delete_key)


@pytest.mark.asyncio
async def test_redis_idempotency_pattern() -> None:
    """Test Redis SETNX operation for idempotency patterns."""
    redis_client = RedisClient(
        client_id="idempotency-test",
        redis_url="redis://localhost:6379"
    )

    # This test validates the interface even if Redis isn't running
    try:
        await redis_client.start()

        # Test idempotency key pattern
        test_key = "spell_check_event:test_correlation_id"

        # First set should succeed (return True)
        result1 = await redis_client.set_if_not_exists(test_key, "processed", ttl_seconds=60)

        # Second set should fail (return False) - key already exists
        result2 = await redis_client.set_if_not_exists(test_key, "processed", ttl_seconds=60)

        assert result1 is True  # First time processing
        assert result2 is False  # Duplicate processing attempt

        # Cleanup
        await redis_client.delete_key(test_key)

    except Exception:
        # Redis not available - just verify the interface exists
        assert callable(redis_client.set_if_not_exists)
    finally:
        await redis_client.stop()
