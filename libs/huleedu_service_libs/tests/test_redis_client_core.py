"""
Unit tests for Redis Client core functionality.

Tests connection lifecycle, core CRUD operations, error handling, and protocol compliance.
Follows HuleEdu testing excellence patterns with comprehensive coverage of untested
core Redis operations.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from huleedu_service_libs.redis_client import RedisClient
from huleedu_service_libs.redis_pubsub import RedisPubSub
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

# Following HuleEdu testing excellence patterns with proper type safety


# Test fixtures
@pytest.fixture
def redis_client() -> RedisClient:
    """Provide RedisClient instance for testing."""
    return RedisClient(client_id="test-client", redis_url="redis://localhost:6379")


@pytest.fixture
def mock_redis_connection() -> AsyncMock:
    """Provide mock Redis connection for boundary testing."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def started_redis_client(
    redis_client: RedisClient, mock_redis_connection: AsyncMock
) -> RedisClient:
    """Provide started RedisClient with mocked connection."""
    redis_client.client = mock_redis_connection
    redis_client._started = True
    redis_client._pubsub = MagicMock(spec=RedisPubSub)
    return redis_client


class TestRedisClientInitialization:
    """Test RedisClient initialization and configuration."""

    def test_client_initialization_default_url(self) -> None:
        """Test client initialization with default Redis URL."""
        client = RedisClient(client_id="test-client")

        assert client.client_id == "test-client"
        assert client.redis_url == "redis://redis:6379"
        assert not client._started
        assert client._pubsub is None

    def test_client_initialization_custom_url(self) -> None:
        """Test client initialization with custom Redis URL."""
        custom_url = "redis://custom-host:6379"
        client = RedisClient(client_id="custom-client", redis_url=custom_url)

        assert client.client_id == "custom-client"
        assert client.redis_url == custom_url
        assert not client._started


class TestRedisClientLifecycle:
    """Test Redis client connection lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_success(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test successful client startup with connection verification."""
        redis_client.client = mock_redis_connection

        await redis_client.start()

        assert redis_client._started is True
        assert redis_client._pubsub is not None
        mock_redis_connection.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_already_started(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test that start() is idempotent when already started."""
        mock_redis_connection.reset_mock()

        await started_redis_client.start()

        mock_redis_connection.ping.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_connection_error(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test start failure with Redis connection error."""
        mock_redis_connection.ping.side_effect = RedisConnectionError("Connection failed")
        redis_client.client = mock_redis_connection

        with pytest.raises(RedisConnectionError):
            await redis_client.start()

        assert redis_client._started is False

    @pytest.mark.asyncio
    async def test_start_generic_error(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test start failure with generic error."""
        mock_redis_connection.ping.side_effect = Exception("Generic error")
        redis_client.client = mock_redis_connection

        with pytest.raises(Exception, match="Generic error"):
            await redis_client.start()

    @pytest.mark.asyncio
    async def test_stop_success(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test successful client shutdown."""
        await started_redis_client.stop()

        assert started_redis_client._started is False
        mock_redis_connection.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_not_started(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test stop when client not started is safe."""
        redis_client.client = mock_redis_connection

        await redis_client.stop()

        mock_redis_connection.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_with_error(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test stop handles errors gracefully."""
        mock_redis_connection.aclose.side_effect = Exception("Close error")

        # Should not raise, just log error and preserve _started state (True)
        # since we cannot be certain the connection was actually closed
        await started_redis_client.stop()

        assert started_redis_client._started is True

    @pytest.mark.asyncio
    async def test_ping_success(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test successful ping operation."""
        result = await started_redis_client.ping()

        assert result is True
        mock_redis_connection.ping.assert_called()

    @pytest.mark.asyncio
    async def test_ping_auto_start(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test ping triggers auto-start when not started."""
        redis_client.client = mock_redis_connection

        result = await redis_client.ping()

        assert result is True
        assert redis_client._started is True

    @pytest.mark.asyncio
    async def test_ping_error_handling(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test ping handles errors and returns False."""
        mock_redis_connection.ping.side_effect = Exception("Ping error")

        result = await started_redis_client.ping()

        assert result is False


class TestRedisClientCoreOperations:
    """Test core Redis CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_success(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test successful get operation."""
        mock_redis_connection.get.return_value = "test_value"

        result = await started_redis_client.get("test_key")

        assert result == "test_value"
        mock_redis_connection.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_not_found(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test get operation for non-existent key."""
        mock_redis_connection.get.return_value = None

        result = await started_redis_client.get("missing_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_auto_start(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test get triggers auto-start when not started."""
        redis_client.client = mock_redis_connection
        mock_redis_connection.get.return_value = "auto_value"

        result = await redis_client.get("auto_key")

        assert result == "auto_value"
        assert redis_client._started is True

    @pytest.mark.asyncio
    async def test_get_timeout_error(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test get operation timeout handling."""
        mock_redis_connection.get.side_effect = RedisTimeoutError("Timeout")

        with pytest.raises(RedisTimeoutError):
            await started_redis_client.get("timeout_key")

    @pytest.mark.asyncio
    async def test_set_if_not_exists_new_key(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test set_if_not_exists with new key."""
        mock_redis_connection.set.return_value = True

        result = await started_redis_client.set_if_not_exists(
            "new_key", "new_value", ttl_seconds=300
        )

        assert result is True
        mock_redis_connection.set.assert_called_once_with("new_key", "new_value", ex=300, nx=True)

    @pytest.mark.asyncio
    async def test_set_if_not_exists_existing_key(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test set_if_not_exists with existing key."""
        mock_redis_connection.set.return_value = None

        result = await started_redis_client.set_if_not_exists("existing_key", "new_value")

        assert result is False

    @pytest.mark.asyncio
    async def test_setex_success(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test setex operation."""
        mock_redis_connection.setex.return_value = True

        result = await started_redis_client.setex("setex_key", 600, "setex_value")

        assert result is True
        mock_redis_connection.setex.assert_called_once_with("setex_key", 600, "setex_value")

    @pytest.mark.asyncio
    async def test_delete_key_success(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test delete_key operation."""
        mock_redis_connection.delete.return_value = 1

        result = await started_redis_client.delete_key("delete_key")

        assert result == 1

    @pytest.mark.asyncio
    async def test_delete_key_not_found(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test delete_key for non-existent key."""
        mock_redis_connection.delete.return_value = 0

        result = await started_redis_client.delete_key("missing_key")

        assert result == 0

    @pytest.mark.asyncio
    async def test_exists_found(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test exists operation for existing key."""
        mock_redis_connection.exists.return_value = 1

        result = await started_redis_client.exists("existing_key")

        assert result == 1

    @pytest.mark.asyncio
    async def test_exists_not_found(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test exists operation for non-existent key."""
        mock_redis_connection.exists.return_value = 0

        result = await started_redis_client.exists("missing_key")

        assert result == 0

    @pytest.mark.asyncio
    async def test_ttl_with_ttl(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test ttl operation for key with TTL."""
        mock_redis_connection.ttl.return_value = 300

        result = await started_redis_client.ttl("ttl_key")

        assert result == 300

    @pytest.mark.asyncio
    async def test_ttl_no_ttl(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test ttl operation for key without TTL."""
        mock_redis_connection.ttl.return_value = -1

        result = await started_redis_client.ttl("no_ttl_key")

        assert result == -1

    @pytest.mark.asyncio
    async def test_expire_success(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test expire operation success."""
        mock_redis_connection.expire.return_value = 1

        result = await started_redis_client.expire("expire_key", 3600)

        assert result is True

    @pytest.mark.asyncio
    async def test_expire_key_not_found(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test expire operation for non-existent key."""
        mock_redis_connection.expire.return_value = 0

        result = await started_redis_client.expire("missing_key", 3600)

        assert result is False


class TestRedisClientErrorHandling:
    """Test comprehensive error handling scenarios."""

    @pytest.mark.asyncio
    async def test_operation_not_started_raises_error(self, redis_client: RedisClient) -> None:
        """Test operations raise error when client not started."""
        with pytest.raises(RuntimeError, match="Redis client 'test-client' is not running"):
            await redis_client.delete_key("test_key")

    @pytest.mark.asyncio
    async def test_auto_start_failure_raises_error(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test auto-start failure in operations."""
        redis_client.client = mock_redis_connection
        mock_redis_connection.ping.side_effect = RedisConnectionError("Connection failed")

        with pytest.raises(RedisConnectionError, match="Connection failed"):
            await redis_client.get("test_key")

    @pytest.mark.asyncio
    async def test_generic_operation_error(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test generic operation error handling."""
        mock_redis_connection.get.side_effect = Exception("Generic Redis error")

        with pytest.raises(Exception, match="Generic Redis error"):
            await started_redis_client.get("error_key")


class TestRedisClientProtocolCompliance:
    """Test AtomicRedisClientProtocol compliance."""

    def test_protocol_compliance(self, redis_client: RedisClient) -> None:
        """Test that RedisClient implements required protocol methods."""
        # Verify core protocol methods exist and are callable
        required_methods = [
            "start",
            "stop",
            "ping",
            "get",
            "set_if_not_exists",
            "delete_key",
            "publish",
            "subscribe",
            "create_transaction_pipeline",
        ]
        for method in required_methods:
            assert hasattr(redis_client, method)
            assert callable(getattr(redis_client, method))

    @pytest.mark.asyncio
    async def test_pubsub_property_access(self, started_redis_client: RedisClient) -> None:
        """Test pubsub property access."""
        pubsub = started_redis_client.pubsub

        assert pubsub is not None
        assert isinstance(pubsub, MagicMock)

    @pytest.mark.asyncio
    async def test_pubsub_property_not_started(self, redis_client: RedisClient) -> None:
        """Test pubsub property when client not started."""
        pubsub = redis_client.pubsub

        assert pubsub is None
