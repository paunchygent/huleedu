"""
Test Redis integration for Spell Checker Service.

Validates that Redis client can be properly injected via DI and basic operations work.

These tests require Redis infrastructure and are marked as integration tests.
They can be run either with testcontainers (recommended) or against a local Redis instance.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

import pytest
from dishka import Scope, make_async_container, provide
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_client import RedisClient
from testcontainers.redis import RedisContainer

from services.spellchecker_service.config import Settings
from services.spellchecker_service.di import SpellCheckerServiceProvider


@pytest.fixture(scope="function")
async def redis_container() -> AsyncGenerator[RedisContainer, None]:
    """Provide a Redis testcontainer for each test function."""
    with RedisContainer("redis:7-alpine") as container:  # noqa: S608 docker image OK
        yield container


@pytest.fixture
def test_settings_with_redis(redis_container: RedisContainer) -> Settings:
    """Provide test settings with testcontainer Redis URL."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{host}:{port}"
    return Settings(
        REDIS_URL=redis_url,
        SERVICE_NAME="spellchecker_service_test",
    )


@pytest.fixture
def test_settings_localhost() -> Settings:
    """Provide test settings with localhost Redis URL for local testing."""
    return Settings(
        REDIS_URL="redis://localhost:6379",
        SERVICE_NAME="spellchecker_service_test",
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_client_di_injection_with_testcontainer(
    test_settings_with_redis: Settings,
) -> None:
    """Test that RedisClient can be injected via DI container using testcontainer."""
    from sqlalchemy.ext.asyncio import create_async_engine

    # Create test engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Create provider with test settings that override defaults
    class TestSpellCheckerServiceProvider(SpellCheckerServiceProvider):
        def __init__(self, engine: Any, test_settings: Settings) -> None:
            super().__init__(engine)
            self._test_settings = test_settings

        @provide(scope=Scope.APP)
        def provide_settings(self) -> Settings:
            return self._test_settings  # type: ignore[no-any-return]

    container = make_async_container(
        TestSpellCheckerServiceProvider(engine=engine, test_settings=test_settings_with_redis)
    )

    async with container() as request_container:
        # Test that we can get a RedisClient from DI
        redis_client = await request_container.get(RedisClientProtocol)

        # Verify it's the correct type
        assert isinstance(redis_client, RedisClient)
        assert redis_client.client_id == "spellchecker_service_test-redis"

        # Test basic Redis operation to ensure connection works
        result = await redis_client.set_if_not_exists(
            "test_di_key",
            "test_value",
            ttl_seconds=60,
        )
        assert isinstance(result, bool)

        # Cleanup
        await redis_client.delete_key("test_di_key")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_client_lifecycle_with_testcontainer(
    redis_container: RedisContainer,
) -> None:
    """Test Redis client lifecycle management using testcontainer."""
    # Create client directly for testing
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{host}:{port}"
    redis_client = RedisClient(client_id="spell-test-client", redis_url=redis_url)

    # Test lifecycle
    assert not redis_client._started

    try:
        await redis_client.start()
        assert redis_client._started

        # Test basic operation
        result = await redis_client.set_if_not_exists(
            "spell_test_key",
            "test_value",
            ttl_seconds=60,
        )
        # Verify operation works
        assert isinstance(result, bool)
        assert result is True  # First set should succeed

        # Test duplicate operation
        result2 = await redis_client.set_if_not_exists(
            "spell_test_key",
            "test_value",
            ttl_seconds=60,
        )
        assert result2 is False  # Second set should fail

        # Cleanup
        await redis_client.delete_key("spell_test_key")

    finally:
        await redis_client.stop()
        assert not redis_client._started


@pytest.mark.asyncio
async def test_redis_protocol_compliance() -> None:
    """Test that RedisClient implements the RedisClientProtocol correctly.
    
    This is a unit test that doesn't require Redis infrastructure.
    """
    redis_client = RedisClient(client_id="spell-protocol-test", redis_url="redis://localhost:6379")

    # Verify protocol compliance
    assert hasattr(redis_client, "set_if_not_exists")
    assert hasattr(redis_client, "delete_key")
    assert callable(redis_client.set_if_not_exists)
    assert callable(redis_client.delete_key)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_redis_idempotency_pattern_with_testcontainer(
    redis_container: RedisContainer,
) -> None:
    """Test Redis SETNX operation for idempotency patterns using testcontainer."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{host}:{port}"
    redis_client = RedisClient(client_id="idempotency-test", redis_url=redis_url)

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

    finally:
        await redis_client.stop()


# Legacy test for environments without testcontainers
@pytest.mark.asyncio
@pytest.mark.docker
async def test_redis_client_di_injection_legacy_localhost(
    test_settings_localhost: Settings,
) -> None:
    """Test Redis DI injection against localhost Redis (requires manual Redis setup).
    
    This test is marked with @pytest.mark.docker and expects Redis to be running
    on localhost:6379. Use this for environments where testcontainers cannot be used.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    # Create test engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Create provider with test settings that override defaults
    class TestSpellCheckerServiceProvider(SpellCheckerServiceProvider):
        def __init__(self, engine: Any, test_settings: Settings) -> None:
            super().__init__(engine)
            self._test_settings = test_settings

        @provide(scope=Scope.APP)
        def provide_settings(self) -> Settings:
            return self._test_settings  # type: ignore[no-any-return]

    container = make_async_container(
        TestSpellCheckerServiceProvider(engine=engine, test_settings=test_settings_localhost)
    )

    async with container() as request_container:
        # Test that we can get a RedisClient from DI
        redis_client = await request_container.get(RedisClientProtocol)

        # Verify it's the correct type
        assert isinstance(redis_client, RedisClient)
        assert redis_client.client_id == "spellchecker_service_test-redis"

        # Test basic Redis operation to ensure connection works
        try:
            result = await redis_client.set_if_not_exists(
                "test_di_key_legacy",
                "test_value",
                ttl_seconds=60,
            )
            assert isinstance(result, bool)

            # Cleanup
            await redis_client.delete_key("test_di_key_legacy")
        except Exception as e:
            pytest.skip(f"Redis not available on localhost:6379: {e}")
