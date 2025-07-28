"""
Simple integration test for the pending validation failures fix.

Focuses on testing the core flow without extensive mocking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode

from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)
from services.essay_lifecycle_service.tests.redis_test_utils import MockRedisPipeline


@pytest.mark.integration
class TestPendingValidationSimple:
    """Simple tests for the pending validation failures functionality."""

    async def test_pending_failures_are_stored_when_batch_does_not_exist(self) -> None:
        """Test that validation failures are stored as pending when batch doesn't exist."""
        # Mock Redis client
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})  # Batch doesn't exist
        mock_redis.rpush = AsyncMock(return_value=1)  # Store pending failure
        mock_redis.expire = AsyncMock(return_value=True)

        # Create coordinator
        coordinator = RedisBatchCoordinator(
            redis_client=mock_redis,
            settings=AsyncMock(redis_transaction_retries=3),
        )

        # Track validation failure for non-existent batch
        batch_id = "test-batch-123"
        failure_data = {
            "batch_id": batch_id,
            "file_upload_id": "upload-456",
            "original_file_name": "essay.pdf",
            "validation_error_code": "EMPTY_CONTENT",
            "validation_error_detail": {
                "error_code": "EMPTY_CONTENT",
                "message": "File is empty",
                "correlation_id": str(uuid4()),
                "timestamp": datetime.now(UTC).isoformat(),
                "service": "file_service",
                "operation": "validate",
                "details": {},
            },
            "file_size_bytes": 0,
            "raw_file_storage_id": "raw-789",
            "correlation_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        await coordinator.track_validation_failure(batch_id, failure_data)

        # Verify pending failure was stored
        expected_key = f"batch:{batch_id}:pending_failures"
        mock_redis.rpush.assert_called_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == expected_key

        # Verify TTL was set (24 hours)
        mock_redis.expire.assert_called_once_with(expected_key, 86400)

    async def test_pending_failures_are_processed_on_batch_registration(self) -> None:
        """Test that pending failures are processed when batch is registered."""
        # Setup mock Redis with pending failures
        mock_redis = AsyncMock()
        pending_failures = ['{"file_upload_id": "upload-123", "batch_id": "test-batch"}']

        # Mock lrange to return pending failures
        mock_redis.lrange = AsyncMock(return_value=pending_failures)

        # Mock pipeline for atomic operations
        mock_pipeline = MockRedisPipeline(
            results=[[True, "slot1", True, True]]  # Results for execute()
        )

        # Use AsyncMock for create_transaction_pipeline since it's async in production
        mock_redis.create_transaction_pipeline = AsyncMock(return_value=mock_pipeline)

        # Create coordinator
        coordinator = RedisBatchCoordinator(
            redis_client=mock_redis,
            settings=AsyncMock(redis_transaction_retries=3),
        )

        # Register batch (which should process pending failures)
        batch_id = "test-batch"
        await coordinator.register_batch_slots(
            batch_id=batch_id,
            essay_ids=["essay-1"],
            metadata={
                "course_code": CourseCode.ENG5.value,
                "essay_instructions": "Write an essay",
            },
            timeout_seconds=86400,
        )

        # Verify pending failures were fetched
        mock_redis.lrange.assert_called_with(f"batch:{batch_id}:pending_failures", 0, -1)

        # Verify pending failures were deleted
        delete_operations = [
            op
            for op in mock_pipeline.operations
            if op[0] == "delete" and f"batch:{batch_id}:pending_failures" in op[1]
        ]
        assert len(delete_operations) > 0, "Expected delete operation for pending failures"

    async def test_batch_completes_immediately_if_all_pending_failures(self) -> None:
        """Test that batch completes immediately if pending failures consume all slots."""
        # Setup mock Redis
        mock_redis = AsyncMock()

        # One pending failure for a batch expecting one essay
        pending_failure = {
            "file_upload_id": "upload-123",
            "original_file_name": "essay.pdf",
            "validation_error_code": "EMPTY_CONTENT",
        }
        mock_redis.lrange = AsyncMock(return_value=[str(pending_failure)])

        # Mock pipeline for processing
        mock_pipeline = MockRedisPipeline(
            results=[[1, "slot1", 1]]  # All slots consumed
        )

        # Use AsyncMock for create_transaction_pipeline since it's async in production
        mock_redis.create_transaction_pipeline = AsyncMock(return_value=mock_pipeline)

        # Create coordinator
        coordinator = RedisBatchCoordinator(
            redis_client=mock_redis,
            settings=AsyncMock(redis_transaction_retries=3),
        )

        # Spy on _process_pending_failures
        with patch.object(
            coordinator, "_process_pending_failures", wraps=coordinator._process_pending_failures
        ) as spy:
            # Register batch with 1 slot
            batch_id = "test-batch"
            await coordinator.register_batch_slots(
                batch_id=batch_id,
                essay_ids=["essay-1"],
                metadata={
                    "course_code": CourseCode.ENG5.value,
                    "essay_instructions": "Write an essay",
                },
                timeout_seconds=86400,
            )

            # Verify pending failures were processed
            spy.assert_called_once_with(batch_id, 86400)
