"""
Unit test that verifies the fix for validation failure batch completion.

This test ensures that handle_validation_failure properly checks for
batch completion and returns BatchEssaysReady when appropriate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.error_enums import FileValidationErrorCode
from common_core.events.batch_coordination_events import BatchEssaysReady, BatchEssaysRegistered
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata

from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
    DefaultBatchEssayTracker,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)


class TestValidationFailureCompletionFix:
    """Test suite verifying the fix for validation failure batch completion."""

    @pytest.fixture
    def mock_persistence(self) -> AsyncMock:
        """Mock database persistence layer."""
        persistence = AsyncMock(spec=BatchTrackerPersistence)
        persistence.get_batch_from_database.return_value = None
        persistence.persist_batch_expectation.return_value = None
        persistence.persist_slot_assignment.return_value = None
        persistence.remove_batch_from_database.return_value = None
        persistence.initialize_from_database.return_value = []
        return persistence

    @pytest.fixture
    def mock_redis_coordinator(self) -> AsyncMock:
        """Mock Redis coordinator with correct completion logic."""
        redis = AsyncMock(spec=RedisBatchCoordinator)

        # Track state
        batch_states: dict[str, dict[str, Any]] = {}
        failure_counts: dict[str, int] = {}
        failure_data: dict[str, list[dict[str, Any]]] = {}
        completed_batches = set()

        async def mock_register_batch_slots(
            batch_id: str, essay_ids: list[str], metadata: dict[str, Any], timeout_seconds: int
        ) -> None:
            batch_states[batch_id] = {
                "total_slots": len(essay_ids),
                "assigned_slots": 0,
                "available_slots": len(essay_ids),
                "is_complete": False,
                "has_timeout": True,
                "metadata": metadata,
                "assignments": {},
            }
            failure_counts[batch_id] = 0
            failure_data[batch_id] = []

        async def mock_get_batch_status(batch_id: str) -> dict[str, Any] | None:
            return batch_states.get(batch_id)

        async def mock_track_validation_failure(batch_id: str, data: dict[str, Any]) -> None:
            if batch_id in failure_counts:
                failure_counts[batch_id] += 1
                failure_data[batch_id].append(data)

        async def mock_get_validation_failure_count(batch_id: str) -> int:
            return failure_counts.get(batch_id, 0)

        async def mock_get_assigned_count(batch_id: str) -> int:
            if batch_id in batch_states:
                return int(batch_states[batch_id]["assigned_slots"])
            return 0

        async def mock_check_batch_completion(batch_id: str) -> bool:
            """Real completion logic."""
            if batch_id not in batch_states:
                return False

            state = batch_states[batch_id]
            assigned = state["assigned_slots"]
            failed = failure_counts.get(batch_id, 0)
            total_processed = assigned + failed
            expected = state["total_slots"]

            # Complete if all processed AND not already marked complete
            return total_processed >= expected and batch_id not in completed_batches

        async def mock_mark_batch_completed_atomically(batch_id: str) -> bool:
            if batch_id not in completed_batches:
                completed_batches.add(batch_id)
                return True
            return False

        async def mock_get_validation_failures(batch_id: str) -> list[dict[str, Any]]:
            return failure_data.get(batch_id, [])

        async def mock_cleanup_batch(batch_id: str) -> None:
            batch_states.pop(batch_id, None)
            failure_counts.pop(batch_id, None)
            failure_data.pop(batch_id, None)

        # Wire up mocks
        redis.register_batch_slots.side_effect = mock_register_batch_slots
        redis.get_batch_status.side_effect = mock_get_batch_status
        redis.track_validation_failure.side_effect = mock_track_validation_failure
        redis.get_validation_failure_count.side_effect = mock_get_validation_failure_count
        redis.get_assigned_count.side_effect = mock_get_assigned_count
        redis.check_batch_completion.side_effect = mock_check_batch_completion
        redis.mark_batch_completed_atomically.side_effect = mock_mark_batch_completed_atomically
        redis.get_validation_failures.side_effect = mock_get_validation_failures
        redis.cleanup_batch.side_effect = mock_cleanup_batch

        return redis

    async def test_all_failures_triggers_completion(
        self, mock_persistence: AsyncMock, mock_redis_coordinator: AsyncMock
    ) -> None:
        """Test that all validation failures properly trigger batch completion."""
        tracker = DefaultBatchEssayTracker(mock_persistence, mock_redis_coordinator)

        # Register batch with 3 essays
        batch_registration = BatchEssaysRegistered(
            batch_id="batch_complete_on_failure",
            expected_essay_count=3,
            essay_ids=["essay_001", "essay_002", "essay_003"],
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="batch_complete_on_failure", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Test all failures",
            user_id="test_user",
        )

        correlation_id = uuid4()
        await tracker.register_batch(batch_registration, correlation_id)

        # First two failures should not trigger completion
        for i in range(1, 3):
            failure = EssayValidationFailedV1(
                batch_id="batch_complete_on_failure",
                original_file_name=f"failed_{i}.txt",
                validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                validation_error_message="Empty content",
                file_size_bytes=0,
                raw_file_storage_id=f"storage_{i}",
                correlation_id=uuid4(),
            )
            result = await tracker.handle_validation_failure(failure)
            assert result is None, f"Failure {i} should not trigger completion"

        # Third failure SHOULD trigger completion
        failure3 = EssayValidationFailedV1(
            batch_id="batch_complete_on_failure",
            original_file_name="failed_3.txt",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_message="Empty content",
            file_size_bytes=0,
            raw_file_storage_id="storage_3",
            correlation_id=uuid4(),
        )

        result = await tracker.handle_validation_failure(failure3)

        # Verify completion was triggered
        assert result is not None, "Third failure should trigger batch completion"
        batch_ready_event, returned_correlation_id = result

        assert isinstance(batch_ready_event, BatchEssaysReady)
        assert batch_ready_event.batch_id == "batch_complete_on_failure"
        assert len(batch_ready_event.ready_essays) == 0  # No successful essays
        assert batch_ready_event.validation_failures is not None
        assert len(batch_ready_event.validation_failures) == 3  # All failed
        assert batch_ready_event.total_files_processed == 3
        assert returned_correlation_id == correlation_id  # Original correlation ID preserved

    async def test_mixed_success_and_failure_completion(
        self, mock_persistence: AsyncMock, mock_redis_coordinator: AsyncMock
    ) -> None:
        """Test batch completion with mix of successful assignments and failures."""
        tracker = DefaultBatchEssayTracker(mock_persistence, mock_redis_coordinator)

        # Register batch with 4 essays
        batch_registration = BatchEssaysRegistered(
            batch_id="batch_mixed",
            expected_essay_count=4,
            essay_ids=["essay_001", "essay_002", "essay_003", "essay_004"],
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="batch_mixed", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.SV1,
            essay_instructions="Mixed results test",
            user_id="test_user_mixed",
        )

        await tracker.register_batch(batch_registration, uuid4())

        # Mock 2 successful slot assignments
        async def mock_assign_slot(
            batch_id: str, content_metadata: dict[str, Any]
        ) -> str | None:
            if batch_id == "batch_mixed":
                state = await mock_redis_coordinator.get_batch_status(batch_id)
                if state["assigned_slots"] < 2:  # Allow 2 assignments
                    state["assigned_slots"] += 1
                    essay_id = f"essay_{state['assigned_slots']:03d}"
                    state["assignments"][essay_id] = content_metadata
                    return essay_id
            return None

        mock_redis_coordinator.assign_slot_atomic.side_effect = mock_assign_slot

        # Assign 2 slots
        for i in range(1, 3):
            essay_id = await tracker.assign_slot_to_content(
                "batch_mixed", f"content_{i}", f"file_{i}.txt"
            )
            assert essay_id is not None

        # Now add 2 validation failures
        failure1 = EssayValidationFailedV1(
            batch_id="batch_mixed",
            original_file_name="failed_3.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_message="Too short",
            file_size_bytes=10,
            raw_file_storage_id="storage_3",
        )

        result1 = await tracker.handle_validation_failure(failure1)
        assert result1 is None  # Not complete yet (2 + 1 < 4)

        failure2 = EssayValidationFailedV1(
            batch_id="batch_mixed",
            original_file_name="failed_4.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            validation_error_message="Too long",
            file_size_bytes=1000000,
            raw_file_storage_id="storage_4",
        )

        result2 = await tracker.handle_validation_failure(failure2)

        # Should complete now (2 assigned + 2 failed = 4)
        assert result2 is not None
        batch_ready_event, _ = result2

        assert batch_ready_event.batch_id == "batch_mixed"
        assert len(batch_ready_event.ready_essays) == 2  # 2 successful
        assert len(batch_ready_event.validation_failures) == 2  # 2 failed
        assert batch_ready_event.total_files_processed == 4

    async def test_no_double_completion(
        self, mock_persistence: AsyncMock, mock_redis_coordinator: AsyncMock
    ) -> None:
        """Test that batch completion can only happen once."""
        tracker = DefaultBatchEssayTracker(mock_persistence, mock_redis_coordinator)

        # Register batch with 2 essays
        batch_registration = BatchEssaysRegistered(
            batch_id="batch_once",
            expected_essay_count=2,
            essay_ids=["essay_001", "essay_002"],
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="batch_once", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Test once",
            user_id="test_user",
        )

        await tracker.register_batch(batch_registration, uuid4())

        # Two failures to complete the batch
        for i in range(1, 3):
            failure = EssayValidationFailedV1(
                batch_id="batch_once",
                original_file_name=f"failed_{i}.txt",
                validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                validation_error_message="Empty",
                file_size_bytes=0,
                raw_file_storage_id=f"storage_{i}",
            )
            result = await tracker.handle_validation_failure(failure)

            if i == 2:
                # Second failure should trigger completion
                assert result is not None

        # Try to add another failure - should not trigger completion again
        extra_failure = EssayValidationFailedV1(
            batch_id="batch_once",
            original_file_name="extra_fail.txt",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_message="Extra",
            file_size_bytes=0,
            raw_file_storage_id="storage_extra",
        )

        # This should check completion but find it's already marked complete
        extra_result = await tracker.handle_validation_failure(extra_failure)
        assert extra_result is None, "Should not complete twice"
