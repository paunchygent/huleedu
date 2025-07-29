"""
Unit tests for Redis Client transactions and advanced operations.

Tests Redis transaction pipeline creation, scan operations, and advanced
integration scenarios. Follows HuleEdu testing excellence patterns with
comprehensive coverage of complex Redis features.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock

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
def mock_pipeline() -> Mock:
    """Provide mock Redis pipeline for transaction testing."""
    pipeline = Mock()
    # Async methods
    pipeline.watch = AsyncMock()
    pipeline.execute = AsyncMock()
    # Sync methods that queue operations
    pipeline.multi = Mock()
    pipeline.set = Mock()
    pipeline.sadd = Mock()
    pipeline.get = Mock()
    pipeline.hset = Mock()
    return pipeline


@pytest.fixture
def mock_redis_connection(mock_pipeline: Mock) -> AsyncMock:
    """Provide mock Redis connection for transaction testing."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    mock.pipeline = MagicMock(return_value=mock_pipeline)  # Sync method returning pipeline
    return mock


@pytest.fixture
def started_redis_client(
    redis_client: RedisClient, mock_redis_connection: AsyncMock
) -> RedisClient:
    """Provide started RedisClient with mocked connection for transactions."""
    redis_client.client = mock_redis_connection
    redis_client._started = True
    redis_client._pubsub = MagicMock(spec=RedisPubSub)
    return redis_client


class TestRedisClientTransactionPipeline:
    """Test Redis transaction pipeline creation and management."""

    @pytest.mark.asyncio
    async def test_create_transaction_pipeline_without_watch_keys(
        self,
        started_redis_client: RedisClient,
        mock_redis_connection: AsyncMock,
        mock_pipeline: Mock,
    ) -> None:
        """Test creating transaction pipeline without watch keys."""
        mock_redis_connection.pipeline.return_value = mock_pipeline

        result = await started_redis_client.create_transaction_pipeline()

        assert result == mock_pipeline
        mock_redis_connection.pipeline.assert_called_once_with(transaction=True)
        mock_pipeline.watch.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_transaction_pipeline_with_watch_keys(
        self,
        started_redis_client: RedisClient,
        mock_redis_connection: AsyncMock,
        mock_pipeline: Mock,
    ) -> None:
        """Test creating transaction pipeline with watch keys."""
        mock_redis_connection.pipeline.return_value = mock_pipeline

        result = await started_redis_client.create_transaction_pipeline("key1", "key2")

        assert result == mock_pipeline
        mock_redis_connection.pipeline.assert_called_once_with(transaction=True)
        mock_pipeline.watch.assert_called_once_with("key1", "key2")

    @pytest.mark.asyncio
    async def test_create_transaction_pipeline_single_watch_key(
        self,
        started_redis_client: RedisClient,
        mock_redis_connection: AsyncMock,
        mock_pipeline: Mock,
    ) -> None:
        """Test creating transaction pipeline with single watch key."""
        mock_redis_connection.pipeline.return_value = mock_pipeline

        result = await started_redis_client.create_transaction_pipeline("single_key")

        assert result == mock_pipeline
        mock_pipeline.watch.assert_called_once_with("single_key")

    @pytest.mark.asyncio
    async def test_create_transaction_pipeline_not_started_raises_error(
        self, redis_client: RedisClient
    ) -> None:
        """Test transaction pipeline creation raises error when client not started."""
        with pytest.raises(RuntimeError, match="Redis client 'test-client' is not running"):
            await redis_client.create_transaction_pipeline()

    @pytest.mark.asyncio
    async def test_create_transaction_pipeline_error_handling(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test transaction pipeline creation handles errors."""
        mock_redis_connection.pipeline.side_effect = Exception("Pipeline creation failed")

        with pytest.raises(Exception, match="Pipeline creation failed"):
            await started_redis_client.create_transaction_pipeline("key1")


class TestRedisClientScanOperations:
    """Test Redis scan operations for key discovery."""

    @pytest.mark.asyncio
    async def test_scan_pattern_with_matches(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test scanning with pattern that matches keys."""
        # Mock scan to return keys in batches, then complete
        mock_redis_connection.scan.side_effect = [
            (10, ["key1", "key2"]),  # First batch with cursor 10
            (0, ["key3"]),  # Final batch with cursor 0 (complete)
        ]

        result = await started_redis_client.scan_pattern("key*")

        assert result == ["key1", "key2", "key3"]
        assert mock_redis_connection.scan.call_count == 2
        mock_redis_connection.scan.assert_any_call(cursor=0, match="key*", count=100)
        mock_redis_connection.scan.assert_any_call(cursor=10, match="key*", count=100)

    @pytest.mark.asyncio
    async def test_scan_pattern_no_matches(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test scanning with pattern that matches no keys."""
        mock_redis_connection.scan.return_value = (0, [])

        result = await started_redis_client.scan_pattern("nonexistent*")

        assert result == []
        mock_redis_connection.scan.assert_called_once_with(
            cursor=0, match="nonexistent*", count=100
        )

    @pytest.mark.asyncio
    async def test_scan_pattern_large_result_set(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test scanning pattern with large result set requiring multiple iterations."""
        # Simulate Redis scan with multiple batches
        mock_redis_connection.scan.side_effect = [
            (100, ["batch1_key1", "batch1_key2"]),  # First batch
            (200, ["batch2_key1", "batch2_key2"]),  # Second batch
            (300, ["batch3_key1"]),  # Third batch
            (0, ["batch4_key1", "batch4_key2"]),  # Final batch (cursor=0)
        ]

        result = await started_redis_client.scan_pattern("large_set:*")

        expected_keys = [
            "batch1_key1",
            "batch1_key2",
            "batch2_key1",
            "batch2_key2",
            "batch3_key1",
            "batch4_key1",
            "batch4_key2",
        ]
        assert result == expected_keys
        assert mock_redis_connection.scan.call_count == 4

    @pytest.mark.asyncio
    async def test_scan_pattern_auto_start(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test scan pattern triggers auto-start when not started."""
        redis_client.client = mock_redis_connection
        mock_redis_connection.scan.return_value = (0, ["auto_key"])

        result = await redis_client.scan_pattern("auto*")

        assert result == ["auto_key"]
        assert redis_client._started is True

    @pytest.mark.asyncio
    async def test_scan_pattern_timeout_error(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test scan pattern handles timeout errors."""
        mock_redis_connection.scan.side_effect = RedisTimeoutError("Scan operation timed out")

        with pytest.raises(RedisTimeoutError, match="Scan operation timed out"):
            await started_redis_client.scan_pattern("timeout*")

    @pytest.mark.asyncio
    async def test_scan_pattern_connection_error(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test scan pattern handles connection errors."""
        mock_redis_connection.scan.side_effect = RedisConnectionError("Connection lost during scan")

        with pytest.raises(RedisConnectionError, match="Connection lost during scan"):
            await started_redis_client.scan_pattern("connection*")


class TestRedisClientIntegrationScenarios:
    """Test complex integration scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_auto_start_integration_scenario(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test auto-start behavior across different operations."""
        redis_client.client = mock_redis_connection
        mock_redis_connection.get.return_value = "cached_value"
        mock_redis_connection.set.return_value = True

        # First operation should trigger auto-start
        get_result = await redis_client.get("cache_key")
        assert get_result == "cached_value"
        assert redis_client._started is True

        # Subsequent operations should not trigger start again
        mock_redis_connection.reset_mock()
        set_result = await redis_client.set_if_not_exists("new_key", "new_value")
        assert set_result is True
        mock_redis_connection.ping.assert_not_called()  # No auto-start

    @pytest.mark.asyncio
    async def test_multiple_operation_types_integration(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test integration across different Redis operation types."""
        # Setup mocks for different operation types
        mock_redis_connection.get.return_value = "string_value"
        mock_redis_connection.sadd.return_value = 1
        mock_redis_connection.hset.return_value = 1
        mock_redis_connection.lpush.return_value = 1

        # Test string operation
        string_result = await started_redis_client.get("string_key")
        assert string_result == "string_value"

        # Test set operation
        set_result = await started_redis_client.sadd("set_key", "member")
        assert set_result == 1

        # Test hash operation
        hash_result = await started_redis_client.hset("hash_key", "field", "value")
        assert hash_result == 1

        # Test list operation
        list_result = await started_redis_client.lpush("list_key", "element")
        assert list_result == 1

    @pytest.mark.asyncio
    async def test_error_recovery_integration(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test error recovery across different operation failures."""
        # First operation fails
        mock_redis_connection.get.side_effect = RedisTimeoutError("First timeout")

        with pytest.raises(RedisTimeoutError):
            await started_redis_client.get("failing_key")

        # Client should still be usable for subsequent operations
        mock_redis_connection.get.side_effect = None
        mock_redis_connection.get.return_value = "recovered_value"

        result = await started_redis_client.get("recovery_key")
        assert result == "recovered_value"

    @pytest.mark.asyncio
    async def test_mixed_success_failure_operations(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test mixed success and failure operations maintain client stability."""
        # Setup alternating success and failure
        mock_redis_connection.set.return_value = True
        mock_redis_connection.get.side_effect = Exception("Intermittent failure")
        mock_redis_connection.exists.return_value = 1

        # Success operation
        set_result = await started_redis_client.set_if_not_exists("success_key", "value")
        assert set_result is True

        # Failure operation
        with pytest.raises(Exception, match="Intermittent failure"):
            await started_redis_client.get("failing_key")

        # Another success operation
        exists_result = await started_redis_client.exists("exists_key")
        assert exists_result == 1

    @pytest.mark.asyncio
    async def test_concurrent_operation_simulation(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test simulation of concurrent operation patterns."""
        # Mock responses for concurrent-like operations
        mock_redis_connection.sadd.return_value = 1
        mock_redis_connection.spop.return_value = "work_item"
        mock_redis_connection.hset.return_value = 1

        # Simulate work queue pattern
        await started_redis_client.sadd("work_queue", "item1", "item2", "item3")
        work_item = await started_redis_client.spop("work_queue")
        assert work_item is not None  # Verify we got a work item
        await started_redis_client.hset("processed", work_item, "completed")

        assert work_item == "work_item"

    @pytest.mark.asyncio
    async def test_transaction_pipeline_integration_pattern(
        self,
        started_redis_client: RedisClient,
        mock_redis_connection: AsyncMock,
        mock_pipeline: Mock,
    ) -> None:
        """Test typical transaction pipeline usage pattern."""
        mock_redis_connection.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True, 1, "result"]

        # Create pipeline and simulate typical usage
        pipeline = await started_redis_client.create_transaction_pipeline("watched_key")

        # Simulate pipeline operations (these would normally be sync calls)
        pipeline.multi()
        pipeline.set("key1", "value1")
        pipeline.sadd("set1", "member1")
        pipeline.get("key2")

        # Execute transaction
        results = await pipeline.execute()

        assert results == [True, 1, "result"]
        mock_pipeline.watch.assert_called_once_with("watched_key")


class TestRedisClientAdvancedErrorHandling:
    """Test advanced error handling scenarios."""

    @pytest.mark.asyncio
    async def test_scan_pattern_not_started_with_auto_start_failure(
        self, redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test scan pattern with auto-start failure."""
        redis_client.client = mock_redis_connection
        mock_redis_connection.ping.side_effect = RedisConnectionError("Auto-start failed")

        with pytest.raises(RedisConnectionError, match="Auto-start failed"):
            await redis_client.scan_pattern("test*")

    @pytest.mark.asyncio
    async def test_transaction_creation_with_connection_failure(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test transaction creation handles connection failures."""
        mock_redis_connection.pipeline.side_effect = RedisConnectionError(
            "Transaction creation failed"
        )

        with pytest.raises(RedisConnectionError, match="Transaction creation failed"):
            await started_redis_client.create_transaction_pipeline("key1")

    @pytest.mark.asyncio
    async def test_scan_pattern_generic_error_handling(
        self, started_redis_client: RedisClient, mock_redis_connection: AsyncMock
    ) -> None:
        """Test scan pattern handles generic errors."""
        mock_redis_connection.scan.side_effect = Exception("Unexpected scan error")

        with pytest.raises(Exception, match="Unexpected scan error"):
            await started_redis_client.scan_pattern("error*")
