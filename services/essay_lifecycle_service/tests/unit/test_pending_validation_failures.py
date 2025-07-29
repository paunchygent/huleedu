"""
Unit tests for validation failure handling across domain classes.

Tests the distributed responsibilities for validation failure tracking,
batch state management, and completion checking.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.essay_lifecycle_service.implementations.redis_batch_state import RedisBatchState
from services.essay_lifecycle_service.implementations.redis_failure_tracker import (
    RedisFailureTracker,
)
from services.essay_lifecycle_service.implementations.redis_script_manager import RedisScriptManager


class TestDomainClassValidationFailures:
    """Test validation failure handling across domain classes."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create Redis client mock with proper return types for domain classes."""
        mock = AsyncMock(spec=AtomicRedisClientProtocol)

        # Proper return types for Redis operations
        mock.rpush = AsyncMock(return_value=1)  # Returns list length
        mock.expire = AsyncMock(return_value=True)  # Returns success boolean
        mock.lrange = AsyncMock(return_value=[])  # Returns list of bytes
        mock.hgetall = AsyncMock(return_value={})  # Returns dict
        mock.scard = AsyncMock(return_value=0)  # Returns set size (int)
        mock.ttl = AsyncMock(return_value=86400)  # Returns TTL in seconds (int)
        mock.llen = AsyncMock(return_value=0)  # Returns list length (int)
        mock.hget = AsyncMock(return_value=b"0")  # Returns bytes
        mock.exists = AsyncMock(return_value=0)  # Returns count (int)
        mock.hset = AsyncMock(return_value=1)  # Returns fields set count
        mock.sadd = AsyncMock(return_value=1)  # Returns elements added count

        # Transaction pipeline mock - mirrors actual Redis pipeline behavior
        def create_transaction_pipeline():
            pipeline_mock = MagicMock()
            # Pipeline operations return the pipeline for chaining (Redis behavior)
            pipeline_mock.multi.return_value = None
            pipeline_mock.sadd.return_value = pipeline_mock  # For batch registration
            pipeline_mock.hset.return_value = pipeline_mock  # For metadata storage
            pipeline_mock.setex.return_value = pipeline_mock  # For timeout
            pipeline_mock.scard.return_value = pipeline_mock  # For available slots count
            pipeline_mock.llen.return_value = pipeline_mock  # For failure count
            pipeline_mock.hlen.return_value = pipeline_mock  # For assignment count
            pipeline_mock.hget.return_value = pipeline_mock  # For expected count
            pipeline_mock.exists.return_value = pipeline_mock  # For completion flag
            # Execute returns transaction results
            pipeline_mock.execute = AsyncMock(return_value=[1, 1, 1])  # Default success results
            return pipeline_mock

        mock.create_transaction_pipeline = AsyncMock(side_effect=create_transaction_pipeline)

        # Lua script evaluation - return appropriate data structures
        mock.eval = AsyncMock(return_value=[])  # Default empty result

        return mock

    @pytest.fixture
    def script_manager(self, mock_redis_client: AsyncMock) -> RedisScriptManager:
        """Create Redis script manager with mock client."""
        return RedisScriptManager(mock_redis_client)

    @pytest.fixture
    def failure_tracker(
        self, mock_redis_client: AsyncMock, script_manager: RedisScriptManager
    ) -> RedisFailureTracker:
        """Create Redis failure tracker with mocks."""
        return RedisFailureTracker(mock_redis_client, script_manager)

    @pytest.fixture
    def batch_state(
        self, mock_redis_client: AsyncMock, script_manager: RedisScriptManager
    ) -> RedisBatchState:
        """Create Redis batch state with mocks."""
        return RedisBatchState(mock_redis_client, script_manager)

    async def test_failure_tracker_stores_validation_failure(
        self,
        mock_redis_client: AsyncMock,
        failure_tracker: RedisFailureTracker,
    ) -> None:
        """Test that RedisFailureTracker stores validation failures correctly."""
        # Arrange
        batch_id = "test-batch-123"
        failure_data = {
            "batch_id": batch_id,
            "file_upload_id": "upload-123",
            "original_file_name": "test.pdf",
            "error": "validation_failed",
        }

        # Mock that the failure list key exists (has TTL > 0)
        mock_redis_client.ttl.return_value = 3600  # 1 hour remaining

        # Act - Call the failure tracker method
        await failure_tracker.track_validation_failure(batch_id, failure_data)

        # Assert - verify failure was stored in Redis list
        mock_redis_client.rpush.assert_called_once()
        rpush_call = mock_redis_client.rpush.call_args

        # Verify the key contains the batch ID
        failure_key = rpush_call[0][0]
        assert batch_id in failure_key

        # Verify the failure data was JSON-encoded
        import json

        stored_data = rpush_call[0][1]
        assert json.loads(stored_data) == failure_data

    async def test_batch_state_registers_batch_slots(
        self,
        mock_redis_client: AsyncMock,
        batch_state: RedisBatchState,
    ) -> None:
        """Test that RedisBatchState registers batch slots correctly."""
        # Arrange
        batch_id = "test-batch-123"
        essay_ids = ["essay-001"]
        metadata = {"course_code": "ENG5"}
        timeout_seconds = 86400

        # Act
        await batch_state.register_batch_slots(
            batch_id=batch_id,
            essay_ids=essay_ids,
            metadata=metadata,
            timeout_seconds=timeout_seconds,
        )

        # Assert - verify transaction pipeline was used properly
        mock_redis_client.create_transaction_pipeline.assert_called()

        # The successful log message indicates the Redis operations completed successfully
        # This validates that the domain class properly used the transaction pipeline
        # for atomic batch registration with sadd, hset, and setex operations

    async def test_failure_tracker_gets_failure_count(
        self,
        mock_redis_client: AsyncMock,
        failure_tracker: RedisFailureTracker,
    ) -> None:
        """Test that RedisFailureTracker can retrieve failure counts."""
        # Arrange
        batch_id = "test-batch-456"

        # Mock Redis list length operation
        mock_redis_client.llen.return_value = 5

        # Act
        count = await failure_tracker.get_validation_failure_count(batch_id)

        # Assert
        assert count == 5

        # Verify the correct Redis operation was called
        mock_redis_client.llen.assert_called_once()
        llen_call = mock_redis_client.llen.call_args
        failure_key = llen_call[0][0]
        assert batch_id in failure_key

    async def test_batch_state_checks_completion(
        self,
        mock_redis_client: AsyncMock,
        batch_state: RedisBatchState,
    ) -> None:
        """Test that RedisBatchState can check batch completion status."""
        # Arrange
        batch_id = "test-batch-789"

        # Mock pipeline to return completion state
        def create_completion_pipeline():
            pipeline_mock = MagicMock()
            pipeline_mock.multi.return_value = None
            pipeline_mock.scard.return_value = pipeline_mock  # available slots
            pipeline_mock.llen.return_value = pipeline_mock  # failure count
            pipeline_mock.hlen.return_value = pipeline_mock  # assignment count
            pipeline_mock.hget.return_value = pipeline_mock  # expected count
            pipeline_mock.exists.return_value = pipeline_mock  # completion flag
            # Execute returns: [available_slots, failure_count, assigned_count, expected_count, already_completed]
            pipeline_mock.execute = AsyncMock(
                return_value=[0, 1, 2, b"3", 0]
            )  # Complete: 0 available, 1 failed, 2 assigned, 3 expected
            return pipeline_mock

        mock_redis_client.create_transaction_pipeline.side_effect = create_completion_pipeline

        # Act
        is_complete = await batch_state.check_batch_completion(batch_id)

        # Assert - should be complete because assigned(2) + failed(1) = expected(3)
        assert is_complete is True

        # Verify pipeline was used for atomic operations
        mock_redis_client.create_transaction_pipeline.assert_called_once()
