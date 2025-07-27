"""
Unit tests for pending validation failures handling in Essay Lifecycle Service.

Tests the race condition fix where validation failures arrive before batch registration.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)
from services.essay_lifecycle_service.tests.redis_test_utils import MockRedisPipeline


class TestPendingValidationFailures:
    """Test pending validation failures handling to fix race conditions."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create a minimal mock Redis client."""
        mock = AsyncMock()
        # Set default return values for common operations
        mock.rpush = AsyncMock(return_value=1)
        mock.expire = AsyncMock(return_value=True)
        mock.lrange = AsyncMock(return_value=[])
        mock.hgetall = AsyncMock(return_value={})
        mock.scard = AsyncMock(return_value=0)
        return mock

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Create mock settings."""
        settings = MagicMock()
        settings.redis_transaction_retries = 3
        return settings

    @pytest.fixture
    def redis_coordinator(
        self, mock_redis_client: AsyncMock, mock_settings: MagicMock
    ) -> RedisBatchCoordinator:
        """Create Redis coordinator with mocks."""
        return RedisBatchCoordinator(redis_client=mock_redis_client, settings=mock_settings)

    async def test_add_validation_failure_stores_as_pending_when_batch_not_exists(
        self,
        mock_redis_client: AsyncMock,
        redis_coordinator: RedisBatchCoordinator,
    ) -> None:
        """Test that validation failures are stored as pending when batch doesn't exist."""
        # Arrange
        batch_id = "test-batch-123"
        failure_data = {
            "batch_id": batch_id,
            "file_upload_id": "upload-123",
            "original_file_name": "test.pdf",
            "error": "validation_failed",
        }

        # Mock batch doesn't exist (get_batch_metadata returns None)
        mock_redis_client.hgetall = AsyncMock(return_value={})

        # Act - Call the public method that adds validation failures
        await redis_coordinator.track_validation_failure(
            batch_id=batch_id,
            failure=failure_data,
        )

        # Assert - verify pending failure was stored with TTL
        mock_redis_client.rpush.assert_called_once()
        rpush_call = mock_redis_client.rpush.call_args
        assert "pending_failures" in rpush_call[0][0]
        assert batch_id in rpush_call[0][0]

        # Verify the data was JSON encoded
        stored_data = rpush_call[0][1]
        assert isinstance(stored_data, str)  # Should be JSON string
        assert json.loads(stored_data) == failure_data

        mock_redis_client.expire.assert_called_once()
        expire_call = mock_redis_client.expire.call_args
        assert expire_call[0][0] == rpush_call[0][0]  # Same key
        assert expire_call[0][1] == 86400  # 24 hours TTL (from the code)

    async def test_register_batch_processes_pending_failures(
        self,
        mock_redis_client: AsyncMock,
        redis_coordinator: RedisBatchCoordinator,
    ) -> None:
        """Test that batch registration processes any pending failures."""
        # Arrange
        batch_id = "test-batch-123"
        pending_failure = {"error": "validation_failed"}

        # Mock pending failures exist
        mock_redis_client.lrange = AsyncMock(return_value=[json.dumps(pending_failure).encode()])

        # Mock pipeline for atomic operations
        pipeline = MockRedisPipeline(results=[[True]])
        mock_redis_client.create_transaction_pipeline = AsyncMock(return_value=pipeline)

        # Act
        await redis_coordinator.register_batch_slots(
            batch_id=batch_id,
            essay_ids=["essay-001"],
            metadata={"course_code": "ENG5"},
            timeout_seconds=86400,
        )

        # Assert - verify pending failures were retrieved
        mock_redis_client.lrange.assert_called()
        lrange_call = mock_redis_client.lrange.call_args
        assert "pending_failures" in lrange_call[0][0]
        assert batch_id in lrange_call[0][0]

    async def test_no_pending_failures_normal_registration(
        self,
        mock_redis_client: AsyncMock,
        redis_coordinator: RedisBatchCoordinator,
    ) -> None:
        """Test normal batch registration when no pending failures exist."""
        # Arrange
        batch_id = "test-batch-456"

        # Mock no pending failures
        mock_redis_client.lrange = AsyncMock(return_value=[])

        # Mock pipeline
        pipeline = MockRedisPipeline(results=[[True]])
        mock_redis_client.create_transaction_pipeline = AsyncMock(return_value=pipeline)

        # Act
        await redis_coordinator.register_batch_slots(
            batch_id=batch_id,
            essay_ids=["essay-001", "essay-002"],
            metadata={"course_code": "ENG5"},
            timeout_seconds=86400,
        )

        # Assert - verify it still checks for pending failures
        mock_redis_client.lrange.assert_called_once()
        lrange_call = mock_redis_client.lrange.call_args
        assert "pending_failures" in lrange_call[0][0]
        assert batch_id in lrange_call[0][0]

    async def test_check_batch_completion_considers_all_states(
        self,
        mock_redis_client: AsyncMock,
        redis_coordinator: RedisBatchCoordinator,
    ) -> None:
        """Test that batch completion check considers available slots, assignments, and failures."""
        # Arrange
        batch_id = "test-batch-789"

        # Mock pipeline that returns completion state
        # Return: 0 available slots, 1 failure, 0 assignments, expected=1, not already completed
        pipeline = MockRedisPipeline(results=[[0, 1, 0, b"1", False]])
        mock_redis_client.create_transaction_pipeline = AsyncMock(return_value=pipeline)

        # Act
        is_complete = await redis_coordinator.check_batch_completion(batch_id)

        # Assert
        assert is_complete is True  # Batch is complete: 0 available + 1 failure = 1 expected
