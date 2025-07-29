"""
Real infrastructure integration test for pending validation failures fix.

Tests the core flow where validation failures arrive before batch registration
using real Redis infrastructure via testcontainers.

Focuses on testing actual behavior with real components, not implementation details.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from huleedu_service_libs.redis_client import RedisClient
from testcontainers.redis import RedisContainer

from services.essay_lifecycle_service.implementations.redis_batch_state import (
    RedisBatchState,
)
from services.essay_lifecycle_service.implementations.redis_failure_tracker import (
    RedisFailureTracker,
)
from services.essay_lifecycle_service.implementations.redis_script_manager import (
    RedisScriptManager,
)


@pytest.mark.integration
class TestPendingValidationSimpleReal:
    """Real infrastructure tests for pending validation failures functionality."""

    @pytest.fixture
    async def test_infrastructure(self) -> AsyncIterator[dict[str, Any]]:
        """Set up real Redis infrastructure with modular components."""
        # Start Redis container
        redis_container = RedisContainer("redis:7-alpine")

        with redis_container as redis:
            # Connection string
            redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}"

            # Initialize Redis client
            redis_client = RedisClient(client_id="test-pending-validation", redis_url=redis_url)
            await redis_client.start()

            # Create real modular components
            redis_script_manager = RedisScriptManager(redis_client)
            batch_state = RedisBatchState(redis_client, redis_script_manager)
            failure_tracker = RedisFailureTracker(redis_client, redis_script_manager)

            yield {
                "redis_client": redis_client,
                "batch_state": batch_state,
                "failure_tracker": failure_tracker,
                "redis_script_manager": redis_script_manager,
            }

            # Cleanup
            await redis_client.stop()

    async def test_pending_failures_stored_when_batch_not_registered(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test that validation failures are stored as pending when batch doesn't exist yet."""
        failure_tracker = test_infrastructure["failure_tracker"]
        redis_client = test_infrastructure["redis_client"]

        # Track validation failure for non-existent batch
        batch_id = f"test-batch-{uuid4().hex[:8]}"
        failure_data = {
            "batch_id": batch_id,
            "file_upload_id": f"upload-{uuid4().hex[:8]}",
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
            "raw_file_storage_id": f"raw-{uuid4().hex[:8]}",
            "correlation_id": str(uuid4()),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Store validation failure
        await failure_tracker.track_validation_failure(batch_id, failure_data)

        # Verify pending failure was stored in Redis
        pending_key = f"batch:{batch_id}:pending_failures"
        pending_failures = await redis_client.lrange(pending_key, 0, -1)

        assert len(pending_failures) == 1, "Should have one pending failure stored"

        # Verify TTL was set for cleanup
        ttl = await redis_client.ttl(pending_key)
        assert ttl > 0, "Pending failures should have TTL set for cleanup"

    async def test_pending_failures_processed_on_batch_registration(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test that pending failures are processed when batch is registered."""
        batch_state = test_infrastructure["batch_state"]
        failure_tracker = test_infrastructure["failure_tracker"]
        redis_client = test_infrastructure["redis_client"]

        batch_id = f"test-batch-{uuid4().hex[:8]}"

        # Store validation failure BEFORE batch registration
        failure_data = {
            "batch_id": batch_id,
            "file_upload_id": f"upload-{uuid4().hex[:8]}",
            "original_file_name": "essay.pdf",
            "validation_error_code": "CORRUPT_FILE",
        }
        await failure_tracker.track_validation_failure(batch_id, failure_data)

        # Verify pending failure exists
        pending_key = f"batch:{batch_id}:pending_failures"
        pending_before = await redis_client.lrange(pending_key, 0, -1)
        assert len(pending_before) == 1, "Should have pending failure before registration"

        # Register batch with 1 slot (should process pending failure)
        await batch_state.register_batch_slots(
            batch_id=batch_id,
            essay_ids=["essay-1"],
            metadata={
                "course_code": CourseCode.ENG5.value,
                "essay_instructions": "Write an essay",
            },
            timeout_seconds=86400,
        )

        # Verify pending failures were processed and removed
        pending_after = await redis_client.lrange(pending_key, 0, -1)
        assert len(pending_after) == 0, "Pending failures should be processed and removed"

        # Verify failure was moved to regular validation failures
        failures_key = f"batch:{batch_id}:validation_failures"
        processed_failures = await redis_client.lrange(failures_key, 0, -1)
        assert len(processed_failures) == 1, "Should have one processed validation failure"

    async def test_batch_completes_when_all_slots_consumed_by_pending_failures(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test that batch completes immediately if pending failures consume all available slots."""
        batch_state = test_infrastructure["batch_state"]
        failure_tracker = test_infrastructure["failure_tracker"]
        redis_client = test_infrastructure["redis_client"]

        batch_id = f"test-batch-{uuid4().hex[:8]}"

        # Store TWO validation failures before batch registration (for 2-essay batch)
        for i in range(2):
            failure_data = {
                "batch_id": batch_id,
                "file_upload_id": f"upload-{i}-{uuid4().hex[:8]}",
                "original_file_name": f"essay{i}.pdf",
                "validation_error_code": "EMPTY_CONTENT",
            }
            await failure_tracker.track_validation_failure(batch_id, failure_data)

        # Register batch with 2 slots (all will be consumed by pending failures)
        await batch_state.register_batch_slots(
            batch_id=batch_id,
            essay_ids=["essay-1", "essay-2"],
            metadata={
                "course_code": CourseCode.ENG5.value,
                "essay_instructions": "Write an essay",
            },
            timeout_seconds=86400,
        )

        # Verify batch is marked as completed (no available slots remain)
        available_key = f"batch:{batch_id}:available_slots"
        available_count = await redis_client.scard(available_key)
        assert available_count == 0, "No slots should remain available"

        # Verify completion flag is set
        completed_key = f"batch:{batch_id}:completed"
        is_completed = await redis_client.exists(completed_key)
        assert is_completed, "Batch should be marked as completed when all slots consumed"

        # Verify all failures were processed
        failures_key = f"batch:{batch_id}:validation_failures"
        processed_failures = await redis_client.lrange(failures_key, 0, -1)
        assert len(processed_failures) == 2, "Both validation failures should be processed"

    async def test_mixed_pending_and_normal_failures(
        self, test_infrastructure: dict[str, Any]
    ) -> None:
        """Test scenario with both pending failures (before registration) and normal failures (after)."""
        batch_state = test_infrastructure["batch_state"]
        failure_tracker = test_infrastructure["failure_tracker"]
        redis_client = test_infrastructure["redis_client"]

        batch_id = f"test-batch-{uuid4().hex[:8]}"

        # Store ONE pending failure before batch registration
        pending_failure = {
            "batch_id": batch_id,
            "file_upload_id": f"upload-pending-{uuid4().hex[:8]}",
            "original_file_name": "pending.pdf",
            "validation_error_code": "EMPTY_CONTENT",
        }
        await failure_tracker.track_validation_failure(batch_id, pending_failure)

        # Register batch with 3 slots (1 consumed by pending, 2 remain)
        await batch_state.register_batch_slots(
            batch_id=batch_id,
            essay_ids=["essay-1", "essay-2", "essay-3"],
            metadata={
                "course_code": CourseCode.ENG5.value,
                "essay_instructions": "Write an essay",
            },
            timeout_seconds=86400,
        )

        # Add normal failure AFTER registration
        normal_failure = {
            "batch_id": batch_id,
            "file_upload_id": f"upload-normal-{uuid4().hex[:8]}",
            "original_file_name": "normal.pdf",
            "validation_error_code": "CORRUPT_FILE",
        }
        await failure_tracker.track_validation_failure(batch_id, normal_failure)

        # Verify batch state: 1 slot consumed by pending + 1 by normal = 1 remaining
        available_key = f"batch:{batch_id}:available_slots"
        available_count = await redis_client.scard(available_key)
        assert available_count == 1, "Should have 1 slot remaining after 2 failures"

        # Verify both failures were processed
        failures_key = f"batch:{batch_id}:validation_failures"
        processed_failures = await redis_client.lrange(failures_key, 0, -1)
        assert len(processed_failures) == 2, (
            "Should have both pending and normal failures processed"
        )

        # Batch should NOT be completed yet (1 slot remains)
        completed_key = f"batch:{batch_id}:completed"
        is_completed = await redis_client.exists(completed_key)
        assert not is_completed, "Batch should not be completed with remaining slots"
