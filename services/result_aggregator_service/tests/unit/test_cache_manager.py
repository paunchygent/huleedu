"""Unit tests for CacheManagerImpl."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from huleedu_service_libs.protocols import RedisClientProtocol
from huleedu_service_libs.redis_set_operations import RedisSetOperations

from services.result_aggregator_service.implementations.cache_manager_impl import CacheManagerImpl


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create a mock Redis client."""
    client = AsyncMock(spec=RedisClientProtocol)
    # Configure the async methods to return appropriate values
    client.get.return_value = None
    client.setex.return_value = True
    client.delete_key.return_value = True
    return client


@pytest.fixture
def mock_redis_set_ops() -> MagicMock:
    """Create a mock Redis SET operations."""
    mock = MagicMock(spec=RedisSetOperations)
    # Create async mock for the pipeline context manager
    async_pipeline = AsyncMock()
    async_pipeline.__aenter__.return_value = async_pipeline
    async_pipeline.__aexit__.return_value = None
    async_pipeline.execute.return_value = [True, True, True]  # Results for setex, sadd, expire
    mock.pipeline.return_value = async_pipeline
    # Configure async methods
    mock.smembers = AsyncMock(return_value=set())
    mock.sadd = AsyncMock(return_value=1)
    mock.srem = AsyncMock(return_value=1)
    return mock


@pytest.fixture
def cache_manager(mock_redis_client: AsyncMock, mock_redis_set_ops: MagicMock) -> CacheManagerImpl:
    """Create a cache manager instance with mocked Redis."""
    return CacheManagerImpl(
        redis_client=mock_redis_client, redis_set_ops=mock_redis_set_ops, cache_ttl=300
    )


class TestCacheManagerImpl:
    """Test cases for CacheManagerImpl."""

    async def test_get_batch_status_json_cache_hit(
        self, cache_manager: CacheManagerImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test getting batch status from cache when data exists.

        Note: The cache manager works with JSON strings, so using string literals
        for cached data is correct here - we're testing the caching layer, not
        the business logic.
        """
        # Arrange
        batch_id = "batch-123"
        cached_data = '{"batch_id": "batch-123", "status": "COMPLETED"}'
        mock_redis_client.get.return_value = cached_data

        # Act
        result = await cache_manager.get_batch_status_json(batch_id)

        # Assert
        assert result == cached_data
        mock_redis_client.get.assert_called_once_with("ras:batch:batch-123")

    async def test_get_batch_status_json_cache_miss(
        self, cache_manager: CacheManagerImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test getting batch status from cache when no data exists."""
        # Arrange
        batch_id = "batch-123"
        mock_redis_client.get.return_value = None

        # Act
        result = await cache_manager.get_batch_status_json(batch_id)

        # Assert
        assert result is None
        mock_redis_client.get.assert_called_once_with("ras:batch:batch-123")

    async def test_set_batch_status_json(
        self, cache_manager: CacheManagerImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test setting batch status in cache."""
        # Arrange
        batch_id = "batch-123"
        status_json = '{"batch_id": "batch-123", "status": "COMPLETED"}'
        ttl = 300

        # Act
        await cache_manager.set_batch_status_json(batch_id, status_json, ttl)

        # Assert
        mock_redis_client.setex.assert_called_once_with("ras:batch:batch-123", ttl, status_json)

    async def test_get_user_batches_json_cache_hit(
        self, cache_manager: CacheManagerImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test getting user batches from cache when data exists.

        Note: The status parameter is a string here because it comes from
        the API query parameters, before being converted to an enum.
        """
        # Arrange
        user_id = "user-456"
        limit = 20
        offset = 0
        status = "COMPLETED"  # This is a string from API query params
        cached_data = '{"batches": [...], "pagination": {...}}'
        mock_redis_client.get.return_value = cached_data

        # Act
        result = await cache_manager.get_user_batches_json(user_id, limit, offset, status)

        # Assert
        assert result == cached_data
        mock_redis_client.get.assert_called_once_with("ras:user:user-456:batches:20:0:COMPLETED")

    async def test_get_user_batches_json_cache_miss(
        self, cache_manager: CacheManagerImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test getting user batches from cache when no data exists."""
        # Arrange
        user_id = "user-456"
        limit = 20
        offset = 0
        status = None
        mock_redis_client.get.return_value = None

        # Act
        result = await cache_manager.get_user_batches_json(user_id, limit, offset, status)

        # Assert
        assert result is None
        mock_redis_client.get.assert_called_once_with("ras:user:user-456:batches:20:0:all")

    async def test_set_user_batches_json(
        self,
        cache_manager: CacheManagerImpl,
        mock_redis_client: AsyncMock,
        mock_redis_set_ops: MagicMock,
    ) -> None:
        """Test setting user batches in cache with tracking."""
        # Arrange
        user_id = "user-456"
        limit = 20
        offset = 0
        status = "PROCESSING"  # String from API query params
        data_json = '{"batches": [...], "pagination": {...}}'
        ttl = 600

        # Setup pipeline mock
        pipeline = AsyncMock()
        pipeline.__aenter__.return_value = pipeline
        pipeline.__aexit__.return_value = None
        pipeline.execute.return_value = [True, 1, True]  # Results for setex, sadd, expire
        mock_redis_set_ops.pipeline.return_value = pipeline

        # Act
        await cache_manager.set_user_batches_json(user_id, limit, offset, status, data_json, ttl)

        # Assert
        # Verify pipeline operations
        pipeline.setex.assert_called_once_with(
            "ras:user:user-456:batches:20:0:PROCESSING", ttl, data_json
        )
        pipeline.sadd.assert_called_once_with(
            "ras:user:user-456:cache_keys", "ras:user:user-456:batches:20:0:PROCESSING"
        )
        pipeline.expire.assert_called_once_with("ras:user:user-456:cache_keys", ttl + 60)
        pipeline.execute.assert_called_once()

    async def test_invalidate_batch(
        self, cache_manager: CacheManagerImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test invalidating batch cache."""
        # Arrange
        batch_id = "batch-123"

        # Act
        await cache_manager.invalidate_batch(batch_id)

        # Assert
        mock_redis_client.delete_key.assert_called_once_with("ras:batch:batch-123")

    async def test_invalidate_user_batches(
        self, cache_manager: CacheManagerImpl, mock_redis_set_ops: MagicMock
    ) -> None:
        """Test invalidating user batches cache with SET-based tracking."""
        # Arrange
        user_id = "user-456"
        cache_keys = {
            "ras:user:user-456:batches:10:0:all",
            "ras:user:user-456:batches:20:0:COMPLETED",
            "ras:user:user-456:batches:10:10:all",
        }
        mock_redis_set_ops.smembers.return_value = cache_keys

        # Setup pipeline mock
        pipeline = AsyncMock()
        pipeline.__aenter__.return_value = pipeline
        pipeline.__aexit__.return_value = None
        pipeline.execute.return_value = [1, 1, 1, 1]  # Results for delete operations
        mock_redis_set_ops.pipeline.return_value = pipeline

        # Act
        await cache_manager.invalidate_user_batches(user_id)

        # Assert
        mock_redis_set_ops.smembers.assert_called_once_with("ras:user:user-456:cache_keys")
        # Verify pipeline operations
        assert pipeline.delete.call_count == 4  # 3 cache keys + 1 tracking key
        pipeline.execute.assert_called_once()

    async def test_build_user_batches_key(self, cache_manager: CacheManagerImpl) -> None:
        """Test cache key generation for user batches."""
        # Test with status
        key = cache_manager._build_user_batches_key("user-123", 10, 20, "COMPLETED")
        assert key == "ras:user:user-123:batches:10:20:COMPLETED"

        # Test without status (should default to "all")
        key = cache_manager._build_user_batches_key("user-123", 10, 20, None)
        assert key == "ras:user:user-123:batches:10:20:all"

    async def test_error_handling_get_batch_status(
        self, cache_manager: CacheManagerImpl, mock_redis_client: AsyncMock
    ) -> None:
        """Test error handling when getting batch status fails."""
        # Arrange
        batch_id = "batch-123"
        mock_redis_client.get.side_effect = Exception("Redis connection error")

        # Act
        with patch(
            "services.result_aggregator_service.implementations.cache_manager_impl.logger"
        ) as mock_logger:
            result = await cache_manager.get_batch_status_json(batch_id)

            # Assert
            assert result is None
            mock_logger.warning.assert_called_once()

    async def test_error_handling_set_user_batches(
        self,
        cache_manager: CacheManagerImpl,
        mock_redis_client: AsyncMock,
        mock_redis_set_ops: MagicMock,
    ) -> None:
        """Test error handling when setting user batches fails."""
        # Arrange
        # Setup pipeline mock to raise exception
        pipeline = AsyncMock()
        pipeline.__aenter__.side_effect = Exception("Redis connection error")
        mock_redis_set_ops.pipeline.return_value = pipeline

        # Act
        with patch(
            "services.result_aggregator_service.implementations.cache_manager_impl.logger"
        ) as mock_logger:
            await cache_manager.set_user_batches_json(
                "user-123", 20, 0, None, '{"data": "test"}', 300
            )

            # Assert
            mock_logger.warning.assert_called_once()
