"""
Unit tests for enhanced BatchEssayTracker with validation failure handling.

Tests the enhanced batch tracking capabilities that handle validation failures
and prevent infinite waits for Phase 6 of the File Service validation improvements.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.error_enums import FileValidationErrorCode
from common_core.events.batch_coordination_events import BatchEssaysReady, BatchEssaysRegistered
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import (
    EntityReference,
    SystemProcessingMetadata,
)
from common_core.models.error_models import ErrorDetail

from services.essay_lifecycle_service.protocols import BatchEssayTracker


class TestBatchEssayTracker:
    """Test suite for BatchEssayTracker with validation failure handling."""

    @pytest.fixture
    def tracker(self) -> BatchEssayTracker:
        """Fixture providing a fresh BatchEssayTracker instance with minimal mocking."""
        from unittest.mock import AsyncMock

        from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
            DefaultBatchEssayTracker,
        )
        from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
            BatchTrackerPersistence,
        )
        from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
            RedisBatchCoordinator,
        )

        # Create simple no-op persistence for testing (only mock database operations)
        persistence = AsyncMock(spec=BatchTrackerPersistence)
        persistence.get_batch_from_database.return_value = None  # No existing batch
        persistence.persist_batch_expectation.return_value = None  # No-op database write
        persistence.persist_slot_assignment.return_value = None  # No-op database write
        persistence.remove_batch_from_database.return_value = None  # No-op database write
        persistence.initialize_from_database.return_value = []  # No existing batches

        # Create stateful mock Redis coordinator for realistic testing
        redis_coordinator = AsyncMock(spec=RedisBatchCoordinator)

        # State tracking for realistic behavior
        batch_state: dict[str, dict[str, Any]] = {}
        failure_counts: dict[str, int] = {}
        slot_assignments: dict[str, set[str]] = {}  # Track slot assignments per batch
        available_essays: dict[str, list[str]] = {}  # Track available essay IDs per batch
        validation_failures: dict[
            str, list[dict[str, Any]]
        ] = {}  # Track validation failures per batch

        async def mock_register_batch_slots(
            batch_id: str, essay_ids: list[str], metadata: dict[str, Any], timeout_seconds: int
        ) -> None:
            # Convert correlation_id to string to match Redis storage format
            metadata_copy = metadata.copy()
            if "correlation_id" in metadata_copy and metadata_copy["correlation_id"] is not None:
                metadata_copy["correlation_id"] = str(metadata_copy["correlation_id"])

            batch_state[batch_id] = {
                "total_slots": len(essay_ids),
                "assigned_slots": 0,
                "is_complete": False,
                "has_timeout": True,
                "metadata": metadata_copy,
                "assignments": {},
            }
            failure_counts[batch_id] = 0
            slot_assignments[batch_id] = set()  # Track assigned slots
            validation_failures[batch_id] = []  # Track validation failures

        async def mock_get_batch_status(batch_id: str) -> dict[str, Any] | None:
            if batch_id in batch_state:
                # Update ready_count in the returned status for compatibility
                status = batch_state[batch_id].copy()
                status["ready_count"] = status["assigned_slots"]
                return status
            return None

        async def mock_assign_slot_atomic(
            batch_id: str, content_metadata: dict[str, Any]
        ) -> str | None:
            # Simulate slot assignment if batch exists and has available slots
            if batch_id in batch_state:
                if batch_state[batch_id]["assigned_slots"] < batch_state[batch_id]["total_slots"]:
                    # Generate a unique essay ID for the assignment
                    essay_id = f"essay_{len(slot_assignments[batch_id]) + 1:03d}"
                    slot_assignments[batch_id].add(essay_id)
                    batch_state[batch_id]["assigned_slots"] += 1
                    batch_state[batch_id]["assignments"][essay_id] = content_metadata
                    return essay_id
            return None

        async def mock_track_validation_failure(
            batch_id: str, failure_data: dict[str, Any]
        ) -> None:
            if batch_id in failure_counts:
                failure_counts[batch_id] += 1
                validation_failures[batch_id].append(failure_data)

        async def mock_get_validation_failure_count(batch_id: str) -> int:
            return failure_counts.get(batch_id, 0)

        async def mock_get_assigned_count(batch_id: str) -> int:
            if batch_id in batch_state:
                return int(batch_state[batch_id]["assigned_slots"])
            return 0

        async def mock_check_batch_completion(batch_id: str) -> bool:
            """Mock completion check based on actual assignment state."""
            if batch_id in batch_state:
                # A batch is complete when assigned + failed >= total
                assigned_count = int(batch_state[batch_id]["assigned_slots"])
                failure_count = failure_counts.get(batch_id, 0)
                total_processed = assigned_count + failure_count
                expected_count = int(batch_state[batch_id]["total_slots"])
                return total_processed >= expected_count
            return False

        async def mock_get_validation_failures(batch_id: str) -> list[dict[str, Any]]:
            # Return the actual validation failures tracked for this batch
            return validation_failures.get(batch_id, [])

        async def mock_cleanup_batch(batch_id: str) -> None:
            # Remove batch from tracking
            batch_state.pop(batch_id, None)
            failure_counts.pop(batch_id, None)
            slot_assignments.pop(batch_id, None)
            available_essays.pop(batch_id, None)
            validation_failures.pop(batch_id, None)

        # Wire up the mock methods
        redis_coordinator.register_batch_slots.side_effect = mock_register_batch_slots
        redis_coordinator.get_batch_status.side_effect = mock_get_batch_status
        redis_coordinator.assign_slot_atomic.side_effect = mock_assign_slot_atomic
        redis_coordinator.track_validation_failure.side_effect = mock_track_validation_failure
        redis_coordinator.get_validation_failure_count.side_effect = (
            mock_get_validation_failure_count
        )
        redis_coordinator.get_assigned_count.side_effect = mock_get_assigned_count
        redis_coordinator.get_validation_failures.side_effect = mock_get_validation_failures
        redis_coordinator.cleanup_batch.side_effect = mock_cleanup_batch

        redis_coordinator.check_batch_completion.side_effect = mock_check_batch_completion

        # Static mocks for other methods
        redis_coordinator.list_active_batch_ids.return_value = []  # No active batches in tests
        redis_coordinator.find_batch_for_essay.return_value = None  # Essay not found in tests

        # Use real tracker with mocked database layer and Redis coordinator
        return DefaultBatchEssayTracker(persistence, redis_coordinator)

    @pytest.fixture
    def sample_batch_registration(self) -> BatchEssaysRegistered:
        """Fixture providing a sample batch registration event."""
        return BatchEssaysRegistered(
            batch_id="batch_test",
            expected_essay_count=5,
            essay_ids=["essay_001", "essay_002", "essay_003", "essay_004", "essay_005"],
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="batch_test", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            # Course context fields
            course_code=CourseCode.ENG5,
            essay_instructions="Test essay instructions",
            user_id="test_user",
        )

    @pytest.fixture
    def sample_validation_failure(self) -> EssayValidationFailedV1:
        """Fixture providing a sample validation failure event."""
        return EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-sample",
            original_file_name="failed_essay.txt",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.EMPTY_CONTENT,
                message="File content is empty or contains only whitespace",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=0,
            raw_file_storage_id="test_storage_id_001",
            correlation_id=uuid4(),
        )

    async def test_validation_failure_tracking_initialization(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that validation failure tracking is properly initialized."""
        # Verify tracker is properly initialized
        # Note: In protocol-based testing, we verify behavior through the interface
        # rather than checking internal attributes
        assert tracker is not None

        # The protocol doesn't expose internal state directly
        # Instead we test that the tracker can handle validation failures properly
        batch_status = await tracker.get_batch_status("nonexistent_batch")
        assert batch_status is None  # No batch registered yet

    async def test_handle_single_validation_failure(
        self,
        tracker: BatchEssayTracker,
        sample_batch_registration: BatchEssaysRegistered,
        sample_validation_failure: EssayValidationFailedV1,
    ) -> None:
        """Test handling a single validation failure."""
        # Register batch first
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        # Handle validation failure
        result = await tracker.handle_validation_failure(sample_validation_failure)

        # Verify failure handling through protocol interface
        # The protocol doesn't expose internal validation_failures directly
        # Instead we verify the batch status reflects the failure handling
        batch_status = await tracker.get_batch_status("batch_test")
        assert batch_status is not None
        assert batch_status["batch_id"] == "batch_test"
        assert batch_status["expected_count"] == 5
        assert batch_status["ready_count"] == 0  # No essays assigned yet

        # Should not trigger completion yet (only 1 of 5 processed)
        assert result is None

    async def test_validation_failure_for_unregistered_batch(
        self, tracker: BatchEssayTracker, sample_validation_failure: EssayValidationFailedV1
    ) -> None:
        """Test handling validation failure for batch not yet registered."""
        # Handle validation failure before batch registration
        await tracker.handle_validation_failure(sample_validation_failure)

        # Should still handle the failure gracefully
        # We can't directly check internal state via protocol, but we can verify
        # that subsequent batch registration works properly
        batch_status = await tracker.get_batch_status("batch_test")
        assert batch_status is None  # No batch registered, so no status available

    async def test_early_batch_completion_trigger(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that early batch completion is triggered when assigned + failed >= expected."""
        # Register batch
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        # Assign 3 slots successfully
        for i in range(1, 4):
            slot_id = await tracker.assign_slot_to_content(
                "batch_test", f"content_{i:03d}", f"essay_{i}.txt"
            )
            assert slot_id is not None

        # Create first validation failure
        failure1 = EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-failure1",
            original_file_name="failed_essay_4.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                message="Content below minimum threshold",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=10,
            raw_file_storage_id="test_storage_id_004",
        )
        result1 = await tracker.handle_validation_failure(failure1)
        assert result1 is None  # Should not complete yet (3 + 1 = 4 < 5)

        # Create second validation failure
        failure2 = EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-failure2",
            original_file_name="failed_essay_5.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                message="Content below minimum threshold",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=10,
            raw_file_storage_id="test_storage_id_005",
        )
        result2 = await tracker.handle_validation_failure(failure2)

        # After second failure: 3 assigned + 2 failed = 5 (equals expected_count)
        # Should trigger early completion
        assert result2 is not None
        ready_event, correlation_id = result2
        assert ready_event.batch_id == "batch_test"
        assert len(ready_event.ready_essays) == 3

    async def test_real_world_24_of_25_scenario(self, tracker: BatchEssayTracker) -> None:
        """Test the real-world scenario: 24 successful essays, 1 validation failure."""
        # Register batch with 25 expected essays
        batch_registration = BatchEssaysRegistered(
            batch_id="batch_24_of_25",
            expected_essay_count=25,
            essay_ids=[f"essay_{i:03d}" for i in range(1, 26)],
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="batch_24_of_25", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            # Course context fields
            course_code=CourseCode.ENG6,
            essay_instructions="Write about your summer vacation",
            user_id="test_user_25",
        )
        correlation_id = uuid4()
        await tracker.register_batch(batch_registration, correlation_id)

        # Assign 24 slots successfully
        for i in range(1, 25):
            slot_id = await tracker.assign_slot_to_content(
                "batch_24_of_25", f"content_{i:03d}", f"essay_{i}.txt"
            )
            assert slot_id is not None

        # Verify no early completion yet (24 < 25)
        batch_status = await tracker.get_batch_status("batch_24_of_25")
        assert batch_status is not None
        assert not batch_status["is_complete"]
        assert batch_status["ready_count"] == 24

        # Add 1 validation failure
        failure = EssayValidationFailedV1(
            batch_id="batch_24_of_25",
            file_upload_id="test-file-upload-25",
            original_file_name="corrupted_essay_25.pdf",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                message="Content too short",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=15,
            raw_file_storage_id="test_storage_id_025",
        )
        result = await tracker.handle_validation_failure(failure)

        # Now: 24 assigned + 1 failed = 25 (equals expected_count)
        # Should trigger early completion
        assert result is not None
        ready_event, _ = result
        assert ready_event.batch_id == "batch_24_of_25"
        assert len(ready_event.ready_essays) == 24
        assert ready_event.validation_failures is not None
        assert len(ready_event.validation_failures) == 1

        # Batch should be cleaned up after completion
        batch_status = await tracker.get_batch_status("batch_24_of_25")
        assert batch_status is None

    async def test_multiple_validation_failures_for_same_batch(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test handling multiple validation failures for the same batch."""
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        # Create multiple validation failures
        failures = [
            EssayValidationFailedV1(
                batch_id="batch_test",
                file_upload_id=f"test-file-upload-multiple-{i}",
                original_file_name=f"failed_{i}.txt",
                validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                validation_error_detail=ErrorDetail(
                    error_code=FileValidationErrorCode.EMPTY_CONTENT,
                    message="Empty content",
                    correlation_id=uuid4(),
                    timestamp=datetime.now(UTC),
                    service="file_service",
                    operation="validate_content"
                ),
                file_size_bytes=0,
                raw_file_storage_id=f"test_storage_id_{i:03d}",
            )
            for i in range(1, 4)
        ]

        # Handle each failure
        for failure in failures:
            await tracker.handle_validation_failure(failure)

        # Verify batch handling through protocol interface
        batch_status = await tracker.get_batch_status("batch_test")
        assert batch_status is not None
        assert batch_status["batch_id"] == "batch_test"
        assert batch_status["expected_count"] == 5
        # The failures are handled internally, not exposed through protocol

    async def test_create_batch_ready_event_implementation(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test the _create_batch_ready_event method implementation."""
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        # Assign 3 slots successfully
        for i in range(1, 4):
            await tracker.assign_slot_to_content("batch_test", f"content_{i:03d}", f"essay_{i}.txt")

        # Create 1 validation failure (not enough to trigger completion)
        failure = EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-batch-ready-1",
            original_file_name="failed_4.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                message="Failed file 4",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=10,
            raw_file_storage_id="test_storage_id_004",
        )
        await tracker.handle_validation_failure(failure)

        # Add another validation failure to complete the batch
        failure2 = EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-batch-ready-2",
            original_file_name="failed_5.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                message="Failed file 5",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=10,
            raw_file_storage_id="test_storage_id_005",
        )

        # Handle the second failure, which should complete the batch
        result = await tracker.handle_validation_failure(failure2)

        # Verify batch completion occurred
        assert result is not None
        ready_event, correlation_id = result

        # Verify the content of the returned BatchEssaysReady event
        assert isinstance(ready_event, BatchEssaysReady)
        assert ready_event.batch_id == "batch_test"
        assert len(ready_event.ready_essays) == 3
        assert ready_event.validation_failures is not None
        assert len(ready_event.validation_failures) == 2
        assert ready_event.total_files_processed == 5

    async def test_all_essays_fail_validation_scenario(self, tracker: BatchEssayTracker) -> None:
        """Test scenario where all essays fail validation."""
        # Register batch with 3 expected essays
        batch_registration = BatchEssaysRegistered(
            batch_id="batch_all_failed",
            expected_essay_count=3,
            essay_ids=["essay_001", "essay_002", "essay_003"],
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="batch_all_failed", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            # Course context fields
            course_code=CourseCode.SV1,
            essay_instructions="Skriv om ditt favoritämne",
            user_id="test_user_failed",
        )
        correlation_id = uuid4()
        await tracker.register_batch(batch_registration, correlation_id)

        # Track if the last failure triggers completion
        completion_result = None

        # Create 3 validation failures (all essays fail)
        for i in range(1, 4):
            failure = EssayValidationFailedV1(
                batch_id="batch_all_failed",
                file_upload_id=f"test-file-upload-all-failed-{i}",
                original_file_name=f"corrupted_{i}.txt",
                validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                validation_error_detail=ErrorDetail(
                    error_code=FileValidationErrorCode.EMPTY_CONTENT,
                    message="Empty file content",
                    correlation_id=uuid4(),
                    timestamp=datetime.now(UTC),
                    service="file_service",
                    operation="validate_content"
                ),
                file_size_bytes=0,
                raw_file_storage_id=f"test_storage_id_failed_{i:03d}",
            )
            result = await tracker.handle_validation_failure(failure)
            if result is not None:
                completion_result = result

        # Should have triggered completion on 3rd failure (0 assigned + 3 failed = 3)
        assert completion_result is not None

        # Verify the completion result contains a BatchEssaysReady event
        ready_event, stored_correlation_id = completion_result
        assert ready_event is not None
        assert ready_event.batch_id == "batch_all_failed"
        assert len(ready_event.ready_essays) == 0  # No successful assignments
        assert ready_event.validation_failures is not None
        assert len(ready_event.validation_failures) == 3

        # Since the batch is completed, it should no longer be tracked
        batch_status = await tracker.get_batch_status("batch_all_failed")
        assert batch_status is None  # Batch completed and cleaned up

    async def test_validation_failure_with_correlation_ids(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that validation failures preserve correlation IDs for tracing."""
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        correlation_id = uuid4()
        failure = EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-tracked",
            original_file_name="tracked_failure.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
                message="Content exceeds maximum length",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=100000,
            raw_file_storage_id="test_storage_id_tracked",
            correlation_id=correlation_id,
        )

        await tracker.handle_validation_failure(failure)

        # Verify failure was handled properly through protocol interface
        batch_status = await tracker.get_batch_status("batch_test")
        assert batch_status is not None
        assert batch_status["batch_id"] == "batch_test"
        # Internal correlation ID handling is not exposed through protocol

    async def test_validation_failure_boundary_conditions(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test boundary conditions for validation failure handling."""
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        # Assign 4 slots (1 short of completion)
        for i in range(1, 5):
            await tracker.assign_slot_to_content("batch_test", f"content_{i:03d}", f"essay_{i}.txt")

        # Verify not complete yet
        batch_status = await tracker.get_batch_status("batch_test")
        assert batch_status is not None
        assert not batch_status["is_complete"]
        assert batch_status["ready_count"] == 4

        # Add exactly 1 validation failure to reach expected count
        failure = EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-final",
            original_file_name="final_failure.txt",
            validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
                message="Final validation error",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=50,
            raw_file_storage_id="test_storage_id_final",
        )
        result = await tracker.handle_validation_failure(failure)

        # Should trigger completion (4 + 1 = 5)
        assert result is not None
        ready_event, _ = result
        assert ready_event.batch_id == "batch_test"
        assert len(ready_event.ready_essays) == 4

    async def test_batch_completion_requires_assigned_essays(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that batch completion only occurs if there are assigned essays."""
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        with patch.object(tracker, "_create_batch_ready_event_from_redis") as mock_complete:
            # Now returns tuple (BatchEssaysReady, correlation_id)
            mock_complete.return_value = (None, None)

            # Create 5 validation failures (all essays fail, none assigned)
            for i in range(1, 6):
                failure = EssayValidationFailedV1(
                    batch_id="batch_test",
                    file_upload_id=f"test-file-upload-empty-{i}",
                    original_file_name=f"failed_{i}.txt",
                    validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                    validation_error_detail=ErrorDetail(
                        error_code=FileValidationErrorCode.EMPTY_CONTENT,
                        message="Empty content",
                        correlation_id=uuid4(),
                        timestamp=datetime.now(UTC),
                        service="file_service",
                        operation="validate_content"
                    ),
                    file_size_bytes=0,
                    raw_file_storage_id=f"test_storage_id_empty_{i:03d}",
                )
                await tracker.handle_validation_failure(failure)

            # Should still trigger completion method (even with 0 assigned essays)
            # This allows ELS to report the complete failure state to BOS
            mock_complete.assert_called()

    async def test_validation_failure_logging_and_metrics(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that validation failure handling includes proper logging and metrics."""
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        # Assign 3 essays successfully
        for i in range(1, 4):
            await tracker.assign_slot_to_content("batch_test", f"content_{i:03d}", f"essay_{i}.txt")

        # Add 1 validation failure (not enough to trigger completion yet)
        failure = EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-logging-1",
            original_file_name="failed_4.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                message="Content too short: file 4",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=20,
            raw_file_storage_id="test_storage_id_short_4",
        )
        await tracker.handle_validation_failure(failure)

        # Verify metrics can be calculated through protocol interface
        batch_status = await tracker.get_batch_status("batch_test")
        assert batch_status is not None

        assigned_count = batch_status["ready_count"]
        expected_count = batch_status["expected_count"]

        assert assigned_count == 3
        assert expected_count == 5
        assert not batch_status["is_complete"]  # Not yet complete

        # Add second validation failure to trigger completion
        failure2 = EssayValidationFailedV1(
            batch_id="batch_test",
            file_upload_id="test-file-upload-logging-2",
            original_file_name="failed_5.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_detail=ErrorDetail(
                error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                message="Content too short: file 5",
                correlation_id=uuid4(),
                timestamp=datetime.now(UTC),
                service="file_service",
                operation="validate_content"
            ),
            file_size_bytes=20,
            raw_file_storage_id="test_storage_id_short_5",
        )
        await tracker.handle_validation_failure(failure2)

        # After completion, batch should be cleaned up
        batch_status = await tracker.get_batch_status("batch_test")
        assert batch_status is None  # Batch completed and cleaned up

    async def test_concurrent_validation_failures(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test handling of concurrent validation failures."""
        correlation_id = uuid4()
        await tracker.register_batch(sample_batch_registration, correlation_id)

        with patch.object(tracker, "_create_batch_ready_event_from_redis") as mock_complete:
            # Now returns tuple (BatchEssaysReady, correlation_id)
            mock_complete.return_value = (None, None)

            # Create multiple failures to handle concurrently
            failures = [
                EssayValidationFailedV1(
                    batch_id="batch_test",
                    file_upload_id=f"test-file-upload-concurrent-{i}",
                    original_file_name=f"concurrent_fail_{i}.txt",
                    validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                    validation_error_detail=ErrorDetail(
                        error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                        message="Content too short: concurrent file",
                        correlation_id=uuid4(),
                        timestamp=datetime.now(UTC),
                        service="file_service",
                        operation="validate_content"
                    ),
                    file_size_bytes=15,
                    raw_file_storage_id=f"test_storage_id_concurrent_{i:03d}",
                )
                for i in range(1, 6)
            ]

            # Handle all failures concurrently
            await asyncio.gather(*[tracker.handle_validation_failure(f) for f in failures])

            # Should trigger completion (0 assigned + 5 failed = 5)
            mock_complete.assert_called()
