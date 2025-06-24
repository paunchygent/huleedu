"""
Unit tests for enhanced BatchEssayTracker with validation failure handling.

Tests the enhanced batch tracking capabilities that handle validation failures
and prevent infinite waits for Phase 6 of the File Service validation improvements.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from common_core.enums import CourseCode, FileValidationErrorCode
from common_core.events.batch_coordination_events import BatchEssaysReady, BatchEssaysRegistered
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import (
    EntityReference,
    SystemProcessingMetadata,
)

from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
    DefaultBatchEssayTracker as BatchEssayTracker,
)


class TestEnhancedBatchEssayTracker:
    """Test suite for enhanced BatchEssayTracker with validation failure handling."""

    @pytest.fixture
    def tracker(self) -> BatchEssayTracker:
        """Fixture providing a fresh BatchEssayTracker instance."""
        return BatchEssayTracker()

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
            original_file_name="failed_essay.txt",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_message="File content is empty or contains only whitespace",
            file_size_bytes=0,
            raw_file_storage_id="test_storage_id_001",
            correlation_id=uuid4(),
        )

    async def test_validation_failure_tracking_initialization(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that validation failure tracking is properly initialized."""
        # Verify initialization
        assert hasattr(tracker, "validation_failures")
        assert isinstance(tracker.validation_failures, dict)
        assert len(tracker.validation_failures) == 0

    async def test_handle_single_validation_failure(
        self,
        tracker: BatchEssayTracker,
        sample_batch_registration: BatchEssaysRegistered,
        sample_validation_failure: EssayValidationFailedV1,
    ) -> None:
        """Test handling a single validation failure."""
        # Register batch first
        await tracker.register_batch(sample_batch_registration)

        # Mock the completion method to track calls
        with patch.object(tracker, "_create_batch_ready_event") as mock_complete:
            mock_complete.return_value = None

            # Handle validation failure
            await tracker.handle_validation_failure(sample_validation_failure)

            # Verify failure is tracked
            assert "batch_test" in tracker.validation_failures
            assert len(tracker.validation_failures["batch_test"]) == 1
            failure = tracker.validation_failures["batch_test"][0]
            assert failure.validation_error_code == FileValidationErrorCode.EMPTY_CONTENT

            # Should not trigger completion yet (only 1 of 5 processed)
            mock_complete.assert_not_called()

    async def test_validation_failure_for_unregistered_batch(
        self, tracker: BatchEssayTracker, sample_validation_failure: EssayValidationFailedV1
    ) -> None:
        """Test handling validation failure for batch not yet registered."""
        # Handle validation failure before batch registration
        await tracker.handle_validation_failure(sample_validation_failure)

        # Should still track the failure
        assert "batch_test" in tracker.validation_failures
        assert len(tracker.validation_failures["batch_test"]) == 1

    async def test_early_batch_completion_trigger(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that early batch completion is triggered when assigned + failed >= expected."""
        # Register batch
        await tracker.register_batch(sample_batch_registration)

        # Mock the completion method
        with patch.object(tracker, "_create_batch_ready_event") as mock_complete:
            mock_complete.return_value = None

            # Assign 3 slots successfully
            for i in range(1, 4):
                slot_id = tracker.assign_slot_to_content(
                    "batch_test", f"content_{i:03d}", f"essay_{i}.txt"
                )
                assert slot_id is not None

            # Create 2 validation failures
            for i in range(4, 6):
                failure = EssayValidationFailedV1(
                    batch_id="batch_test",
                    original_file_name=f"failed_essay_{i}.txt",
                    validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                    validation_error_message="Content below minimum threshold",
                    file_size_bytes=10,
                    raw_file_storage_id=f"test_storage_id_{i:03d}",
                )
                await tracker.handle_validation_failure(failure)

            # After second failure: 3 assigned + 2 failed = 5 (equals expected_count)
            # Should trigger early completion
            mock_complete.assert_called_once()

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
        await tracker.register_batch(batch_registration)

        # Mock completion method
        with patch.object(tracker, "_create_batch_ready_event") as mock_complete:
            mock_complete.return_value = None

            # Assign 24 slots successfully
            for i in range(1, 25):
                slot_id = tracker.assign_slot_to_content(
                    "batch_24_of_25", f"content_{i:03d}", f"essay_{i}.txt"
                )
                assert slot_id is not None

            # Verify no early completion yet (24 < 25)
            mock_complete.assert_not_called()

            # Add 1 validation failure
            failure = EssayValidationFailedV1(
                batch_id="batch_24_of_25",
                original_file_name="corrupted_essay_25.pdf",
                validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                validation_error_message="Content too short",
                file_size_bytes=15,
                raw_file_storage_id="test_storage_id_025",
            )
            await tracker.handle_validation_failure(failure)

            # Now: 24 assigned + 1 failed = 25 (equals expected_count)
            # Should trigger early completion
            mock_complete.assert_called_once()

            # Verify batch state
            expectation = tracker.batch_expectations["batch_24_of_25"]
            assert len(expectation.slot_assignments) == 24
            assert len(tracker.validation_failures["batch_24_of_25"]) == 1

    async def test_multiple_validation_failures_for_same_batch(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test handling multiple validation failures for the same batch."""
        await tracker.register_batch(sample_batch_registration)

        # Create multiple validation failures
        failures = [
            EssayValidationFailedV1(
                batch_id="batch_test",
                original_file_name=f"failed_{i}.txt",
                validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                validation_error_message="Empty content",
                file_size_bytes=0,
                raw_file_storage_id=f"test_storage_id_{i:03d}",
            )
            for i in range(1, 4)
        ]

        # Handle each failure
        for failure in failures:
            await tracker.handle_validation_failure(failure)

        # Verify all failures are tracked
        assert len(tracker.validation_failures["batch_test"]) == 3
        assert all(
            f.validation_error_code == FileValidationErrorCode.EMPTY_CONTENT
            for f in tracker.validation_failures["batch_test"]
        )

    async def test_create_batch_ready_event_implementation(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test the _create_batch_ready_event method implementation."""
        await tracker.register_batch(sample_batch_registration)

        # Assign 3 slots successfully
        for i in range(1, 4):
            tracker.assign_slot_to_content("batch_test", f"content_{i:03d}", f"essay_{i}.txt")

        # Create 1 validation failure (not enough to trigger completion)
        failure = EssayValidationFailedV1(
            batch_id="batch_test",
            original_file_name="failed_4.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_message="Failed file 4",
            file_size_bytes=10,
            raw_file_storage_id="test_storage_id_004",
        )
        await tracker.handle_validation_failure(failure)

        # Get expectation before completion
        expectation = tracker.batch_expectations["batch_test"]

        # Manually add another failure to the tracker for testing
        failure2 = EssayValidationFailedV1(
            batch_id="batch_test",
            original_file_name="failed_5.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_message="Failed file 5",
            file_size_bytes=10,
            raw_file_storage_id="test_storage_id_005",
        )
        tracker.validation_failures["batch_test"].append(failure2)

        # Call _create_batch_ready_event directly (no need to mock for this test)
        ready_event = tracker._create_batch_ready_event("batch_test", expectation)

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
        await tracker.register_batch(batch_registration)

        # Mock completion method
        with patch.object(tracker, "_create_batch_ready_event") as mock_complete:
            mock_complete.return_value = None

            # Create 3 validation failures (all essays fail)
            for i in range(1, 4):
                failure = EssayValidationFailedV1(
                    batch_id="batch_all_failed",
                    original_file_name=f"corrupted_{i}.txt",
                    validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                    validation_error_message="Empty file content",
                    file_size_bytes=0,
                    raw_file_storage_id=f"test_storage_id_failed_{i:03d}",
                )
                await tracker.handle_validation_failure(failure)

            # Should trigger completion on 3rd failure (0 assigned + 3 failed = 3)
            mock_complete.assert_called_once()

            # Verify state
            assert len(tracker.validation_failures["batch_all_failed"]) == 3
            expectation = tracker.batch_expectations["batch_all_failed"]
            assert len(expectation.slot_assignments) == 0  # No successful assignments

    async def test_validation_failure_with_correlation_ids(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that validation failures preserve correlation IDs for tracing."""
        await tracker.register_batch(sample_batch_registration)

        correlation_id = uuid4()
        failure = EssayValidationFailedV1(
            batch_id="batch_test",
            original_file_name="tracked_failure.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_LONG,
            validation_error_message="Content exceeds maximum length",
            file_size_bytes=100000,
            raw_file_storage_id="test_storage_id_tracked",
            correlation_id=correlation_id,
        )

        await tracker.handle_validation_failure(failure)

        # Verify correlation ID is preserved
        tracked_failure = tracker.validation_failures["batch_test"][0]
        assert tracked_failure.correlation_id == correlation_id

    async def test_validation_failure_boundary_conditions(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test boundary conditions for validation failure handling."""
        await tracker.register_batch(sample_batch_registration)

        with patch.object(tracker, "_create_batch_ready_event") as mock_complete:
            mock_complete.return_value = None

            # Assign 4 slots (1 short of completion)
            for i in range(1, 5):
                tracker.assign_slot_to_content("batch_test", f"content_{i:03d}", f"essay_{i}.txt")

            # Should not trigger completion yet
            mock_complete.assert_not_called()

            # Add exactly 1 validation failure to reach expected count
            failure = EssayValidationFailedV1(
                batch_id="batch_test",
                original_file_name="final_failure.txt",
                validation_error_code=FileValidationErrorCode.UNKNOWN_VALIDATION_ERROR,
                validation_error_message="Final validation error",
                file_size_bytes=50,
                raw_file_storage_id="test_storage_id_final",
            )
            await tracker.handle_validation_failure(failure)

            # Should trigger completion (4 + 1 = 5)
            mock_complete.assert_called_once()

    async def test_batch_completion_requires_assigned_essays(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test that batch completion only occurs if there are assigned essays."""
        await tracker.register_batch(sample_batch_registration)

        with patch.object(tracker, "_create_batch_ready_event") as mock_complete:
            mock_complete.return_value = None

            # Create 5 validation failures (all essays fail, none assigned)
            for i in range(1, 6):
                failure = EssayValidationFailedV1(
                    batch_id="batch_test",
                    original_file_name=f"failed_{i}.txt",
                    validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
                    validation_error_message="Empty content",
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
        await tracker.register_batch(sample_batch_registration)

        # Assign 3 essays successfully
        for i in range(1, 4):
            tracker.assign_slot_to_content("batch_test", f"content_{i:03d}", f"essay_{i}.txt")

        # Add 1 validation failure (not enough to trigger completion yet)
        failure = EssayValidationFailedV1(
            batch_id="batch_test",
            original_file_name="failed_4.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_message="Content too short: file 4",
            file_size_bytes=20,
            raw_file_storage_id="test_storage_id_short_4",
        )
        await tracker.handle_validation_failure(failure)

        # Verify metrics can be calculated (before completion)
        expectation = tracker.batch_expectations["batch_test"]
        failure_count = len(tracker.validation_failures["batch_test"])
        assigned_count = len(expectation.slot_assignments)
        total_processed = assigned_count + failure_count

        assert failure_count == 1
        assert assigned_count == 3
        assert total_processed == 4
        assert total_processed < expectation.expected_count  # Not yet complete

        # Add second validation failure to trigger completion
        failure2 = EssayValidationFailedV1(
            batch_id="batch_test",
            original_file_name="failed_5.txt",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_message="Content too short: file 5",
            file_size_bytes=20,
            raw_file_storage_id="test_storage_id_short_5",
        )
        await tracker.handle_validation_failure(failure2)

        # After completion, batch should be cleaned up
        assert "batch_test" not in tracker.batch_expectations
        assert "batch_test" not in tracker.validation_failures

    async def test_concurrent_validation_failures(
        self, tracker: BatchEssayTracker, sample_batch_registration: BatchEssaysRegistered
    ) -> None:
        """Test handling of concurrent validation failures."""
        await tracker.register_batch(sample_batch_registration)

        with patch.object(tracker, "_create_batch_ready_event") as mock_complete:
            mock_complete.return_value = None

            # Create multiple failures to handle concurrently
            failures = [
                EssayValidationFailedV1(
                    batch_id="batch_test",
                    original_file_name=f"concurrent_fail_{i}.txt",
                    validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
                    validation_error_message="Content too short: concurrent file",
                    file_size_bytes=15,
                    raw_file_storage_id=f"test_storage_id_concurrent_{i:03d}",
                )
                for i in range(1, 6)
            ]

            # Handle all failures concurrently
            await asyncio.gather(*[tracker.handle_validation_failure(f) for f in failures])

            # Should trigger completion (0 assigned + 5 failed = 5)
            mock_complete.assert_called()
