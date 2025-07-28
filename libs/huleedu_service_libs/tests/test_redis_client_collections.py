"""
Unit tests for Redis Client collections functionality.

Tests Redis set, hash, and list operations with comprehensive coverage of
collection-specific operations and error scenarios. Follows HuleEdu testing
excellence patterns with comprehensive edge case coverage.
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
    """Provide mock Redis connection for collections testing."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def started_redis_client(redis_client: RedisClient, mock_redis_connection: AsyncMock) -> RedisClient:
    """Provide started RedisClient with mocked connection for collections."""
    redis_client.client = mock_redis_connection
    redis_client._started = True
    redis_client._pubsub = MagicMock(spec=RedisPubSub)
    return redis_client


class TestRedisClientSetOperations:
    """Test Redis set operations for slot management."""

    @pytest.mark.asyncio
    async def test_sadd_success_single_member(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test adding single member to Redis set."""
        mock_redis_connection.sadd.return_value = 1
        
        result = await started_redis_client.sadd("test_set", "member1")
        
        assert result == 1
        mock_redis_connection.sadd.assert_called_once_with("test_set", "member1")

    @pytest.mark.asyncio
    async def test_sadd_success_multiple_members(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test adding multiple members to Redis set."""
        mock_redis_connection.sadd.return_value = 2
        
        result = await started_redis_client.sadd("test_set", "member1", "member2")
        
        assert result == 2
        mock_redis_connection.sadd.assert_called_once_with("test_set", "member1", "member2")

    @pytest.mark.asyncio
    async def test_sadd_not_started_raises_error(self, redis_client: RedisClient) -> None:
        """Test sadd raises error when client not started."""
        with pytest.raises(RuntimeError, match="Redis client 'test-client' is not running"):
            await redis_client.sadd("test_set", "member1")

    @pytest.mark.asyncio
    async def test_spop_success_with_member(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test removing member from non-empty set."""
        mock_redis_connection.spop.return_value = "removed_member"
        
        result = await started_redis_client.spop("test_set")
        
        assert result == "removed_member"
        mock_redis_connection.spop.assert_called_once_with("test_set")

    @pytest.mark.asyncio
    async def test_spop_empty_set(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test removing member from empty set."""
        mock_redis_connection.spop.return_value = None
        
        result = await started_redis_client.spop("empty_set")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_scard_with_members(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting cardinality of set with members."""
        mock_redis_connection.scard.return_value = 5
        
        result = await started_redis_client.scard("test_set")
        
        assert result == 5

    @pytest.mark.asyncio
    async def test_scard_empty_set(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting cardinality of empty set."""
        mock_redis_connection.scard.return_value = 0
        
        result = await started_redis_client.scard("empty_set")
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_smembers_with_members(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting all members from set with data."""
        mock_redis_connection.smembers.return_value = {"member1", "member2", "member3"}
        
        result = await started_redis_client.smembers("test_set")
        
        assert result == {"member1", "member2", "member3"}

    @pytest.mark.asyncio
    async def test_smembers_empty_set(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting all members from empty set."""
        mock_redis_connection.smembers.return_value = set()
        
        result = await started_redis_client.smembers("empty_set")
        
        assert result == set()


class TestRedisClientHashOperations:
    """Test Redis hash operations for metadata storage."""

    @pytest.mark.asyncio
    async def test_hset_new_field(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test setting new field in hash."""
        mock_redis_connection.hset.return_value = 1
        
        result = await started_redis_client.hset("test_hash", "field1", "value1")
        
        assert result == 1
        mock_redis_connection.hset.assert_called_once_with("test_hash", "field1", "value1")

    @pytest.mark.asyncio
    async def test_hset_update_field(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test updating existing field in hash."""
        mock_redis_connection.hset.return_value = 0
        
        result = await started_redis_client.hset("test_hash", "existing_field", "new_value")
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_hget_existing_field(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting existing field from hash."""
        mock_redis_connection.hget.return_value = "field_value"
        
        result = await started_redis_client.hget("test_hash", "field1")
        
        assert result == "field_value"
        mock_redis_connection.hget.assert_called_once_with("test_hash", "field1")

    @pytest.mark.asyncio
    async def test_hget_nonexistent_field(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting non-existent field from hash."""
        mock_redis_connection.hget.return_value = None
        
        result = await started_redis_client.hget("test_hash", "missing_field")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_hget_bytes_response(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test hget handles bytes response correctly."""
        mock_redis_connection.hget.return_value = b"byte_value"
        
        result = await started_redis_client.hget("test_hash", "byte_field")
        
        assert result == "byte_value"

    @pytest.mark.asyncio
    async def test_hlen_with_fields(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting hash length with fields."""
        mock_redis_connection.hlen.return_value = 3
        
        result = await started_redis_client.hlen("test_hash")
        
        assert result == 3

    @pytest.mark.asyncio
    async def test_hlen_empty_hash(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting hash length for empty hash."""
        mock_redis_connection.hlen.return_value = 0
        
        result = await started_redis_client.hlen("empty_hash")
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_hgetall_with_data(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting all fields and values from hash."""
        mock_redis_connection.hgetall.return_value = {"field1": "value1", "field2": "value2"}
        
        result = await started_redis_client.hgetall("test_hash")
        
        assert result == {"field1": "value1", "field2": "value2"}

    @pytest.mark.asyncio
    async def test_hgetall_empty_hash(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting all fields from empty hash."""
        mock_redis_connection.hgetall.return_value = {}
        
        result = await started_redis_client.hgetall("empty_hash")
        
        assert result == {}

    @pytest.mark.asyncio
    async def test_hexists_field_exists(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test checking existence of existing field."""
        mock_redis_connection.hexists.return_value = 1
        
        result = await started_redis_client.hexists("test_hash", "existing_field")
        
        assert result is True
        mock_redis_connection.hexists.assert_called_once_with("test_hash", "existing_field")

    @pytest.mark.asyncio
    async def test_hexists_field_not_exists(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test checking existence of non-existent field."""
        mock_redis_connection.hexists.return_value = 0
        
        result = await started_redis_client.hexists("test_hash", "missing_field")
        
        assert result is False


class TestRedisClientListOperations:
    """Test Redis list operations for validation failure tracking."""

    @pytest.mark.asyncio
    async def test_rpush_single_value(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test appending single value to list."""
        mock_redis_connection.rpush.return_value = 1
        
        result = await started_redis_client.rpush("test_list", "value1")
        
        assert result == 1
        mock_redis_connection.rpush.assert_called_once_with("test_list", "value1")

    @pytest.mark.asyncio
    async def test_rpush_multiple_values(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test appending multiple values to list."""
        mock_redis_connection.rpush.return_value = 3
        
        result = await started_redis_client.rpush("test_list", "value1", "value2")
        
        assert result == 3
        mock_redis_connection.rpush.assert_called_once_with("test_list", "value1", "value2")

    @pytest.mark.asyncio
    async def test_lpush_single_value(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test prepending single value to list."""
        mock_redis_connection.lpush.return_value = 1
        
        result = await started_redis_client.lpush("test_list", "value1")
        
        assert result == 1
        mock_redis_connection.lpush.assert_called_once_with("test_list", "value1")

    @pytest.mark.asyncio
    async def test_lpush_multiple_values(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test prepending multiple values to list."""
        mock_redis_connection.lpush.return_value = 3
        
        result = await started_redis_client.lpush("test_list", "value1", "value2")
        
        assert result == 3

    @pytest.mark.asyncio
    async def test_lrange_with_elements(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting range of elements from list."""
        mock_redis_connection.lrange.return_value = ["elem1", "elem2", "elem3"]
        
        result = await started_redis_client.lrange("test_list", 0, 2)
        
        assert result == ["elem1", "elem2", "elem3"]
        mock_redis_connection.lrange.assert_called_once_with("test_list", 0, 2)

    @pytest.mark.asyncio
    async def test_lrange_empty_list(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting range from empty list."""
        mock_redis_connection.lrange.return_value = []
        
        result = await started_redis_client.lrange("empty_list", 0, -1)
        
        assert result == []

    @pytest.mark.asyncio
    async def test_llen_with_elements(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting length of list with elements."""
        mock_redis_connection.llen.return_value = 5
        
        result = await started_redis_client.llen("test_list")
        
        assert result == 5

    @pytest.mark.asyncio
    async def test_llen_empty_list(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test getting length of empty list."""
        mock_redis_connection.llen.return_value = 0
        
        result = await started_redis_client.llen("empty_list")
        
        assert result == 0

    @pytest.mark.asyncio
    async def test_blpop_with_element(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test blocking pop with available element."""
        mock_redis_connection.blpop.return_value = ("test_list", "popped_value")
        
        result = await started_redis_client.blpop(["test_list"], timeout=1.0)
        
        assert result == ("test_list", "popped_value")
        mock_redis_connection.blpop.assert_called_once_with(["test_list"], timeout=1.0)

    @pytest.mark.asyncio
    async def test_blpop_timeout(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test blocking pop with timeout."""
        mock_redis_connection.blpop.return_value = None
        
        result = await started_redis_client.blpop(["empty_list"], timeout=0.1)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_blpop_default_timeout(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test blocking pop with default timeout (block indefinitely)."""
        mock_redis_connection.blpop.return_value = ("test_list", "value")
        
        result = await started_redis_client.blpop(["test_list"])
        
        assert result == ("test_list", "value")
        mock_redis_connection.blpop.assert_called_once_with(["test_list"], timeout=0)


class TestRedisClientCollectionsErrorHandling:
    """Test comprehensive error handling for collection operations."""

    @pytest.mark.asyncio
    async def test_set_operation_not_started_error(self, redis_client: RedisClient) -> None:
        """Test set operations raise error when client not started."""
        with pytest.raises(RuntimeError, match="Redis client 'test-client' is not running"):
            await redis_client.spop("test_set")

    @pytest.mark.asyncio
    async def test_hash_operation_not_started_error(self, redis_client: RedisClient) -> None:
        """Test hash operations raise error when client not started."""
        with pytest.raises(RuntimeError, match="Redis client 'test-client' is not running"):
            await redis_client.hget("test_hash", "field")

    @pytest.mark.asyncio
    async def test_list_operation_not_started_error(self, redis_client: RedisClient) -> None:
        """Test list operations raise error when client not started."""
        with pytest.raises(RuntimeError, match="Redis client 'test-client' is not running"):
            await redis_client.llen("test_list")

    @pytest.mark.asyncio
    async def test_collection_operation_generic_error(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test collection operations handle generic errors."""
        mock_redis_connection.sadd.side_effect = Exception("Redis connection lost")
        
        with pytest.raises(Exception, match="Redis connection lost"):
            await started_redis_client.sadd("test_set", "member")

    @pytest.mark.asyncio
    async def test_hash_operation_connection_error(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test hash operations handle connection errors."""
        mock_redis_connection.hset.side_effect = RedisConnectionError("Connection failed")
        
        with pytest.raises(RedisConnectionError, match="Connection failed"):
            await started_redis_client.hset("test_hash", "field", "value")

    @pytest.mark.asyncio
    async def test_list_operation_timeout_error(self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock) -> None:
        """Test list operations handle timeout errors."""
        mock_redis_connection.lrange.side_effect = RedisTimeoutError("Operation timed out")
        
        with pytest.raises(RedisTimeoutError, match="Operation timed out"):
            await started_redis_client.lrange("test_list", 0, -1)