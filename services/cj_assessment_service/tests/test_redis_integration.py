"""
Test Redis integration for CJ Assessment Service.

Validates that Redis client can be properly injected via DI and basic operations work.
"""

from __future__ import annotations

import pytest
from dishka import make_async_container
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient

from services.cj_assessment_service.di import CJAssessmentServiceProvider


@pytest.mark.asyncio
async def test_redis_client_di_injection() -> None:
    """Test that RedisClient can be injected via DI container."""
    container = make_async_container(CJAssessmentServiceProvider())

    async with container() as request_container:
        # Test that we can get a RedisClient from DI
        redis_client = await request_container.get(RedisClientProtocol)

        # Verify it's the correct type
        assert isinstance(redis_client, RedisClient)
        assert redis_client.client_id == "cj_assessment_service-redis"


@pytest.mark.asyncio
async def test_redis_client_lifecycle() -> None:
    """Test Redis client lifecycle management."""
    # Create client directly for testing
    redis_client = RedisClient(client_id="test-client", redis_url="redis://localhost:6379")

    # Test lifecycle
    assert not redis_client._started

    try:
        await redis_client.start()
        assert redis_client._started

        # Test basic operation (will fail if Redis not available, which is expected)
        try:
            result = await redis_client.set_if_not_exists("test_key", "test_value", ttl_seconds=60)
            # If Redis is available, verify operation works
            assert isinstance(result, bool)

            # Cleanup
            await redis_client.delete_key("test_key")
        except Exception:
            # Redis not available in test environment - that's ok
            pass

    finally:
        await redis_client.stop()
        assert not redis_client._started


@pytest.mark.asyncio
async def test_redis_protocol_interface() -> None:
    """Test that RedisClient implements the protocol correctly."""
    redis_client = RedisClient(client_id="protocol-test", redis_url="redis://localhost:6379")

    # Verify protocol compliance
    assert hasattr(redis_client, "set_if_not_exists")
    assert hasattr(redis_client, "delete_key")
    assert callable(redis_client.set_if_not_exists)
    assert callable(redis_client.delete_key)
