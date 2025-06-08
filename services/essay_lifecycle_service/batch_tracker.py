"""
Batch readiness tracking for Essay Lifecycle Service.

Implements slot-based coordination pattern for coordinating batch processing
between BOS (Batch Orchestrator Service) and File Service via ELS slot assignment.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from common_core.events.batch_coordination_events import (
    BatchEssaysReady,
    BatchEssaysRegistered,
    BatchReadinessTimeout,
)
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("batch_tracker")


class SlotAssignment:
    """Represents assignment of content to an internal essay ID slot."""

    def __init__(
        self,
        internal_essay_id: str,
        text_storage_id: str,
        original_file_name: str,
    ) -> None:
        self.internal_essay_id = internal_essay_id
        self.text_storage_id = text_storage_id
        self.original_file_name = original_file_name
        self.assigned_at = datetime.now(UTC)


class BatchExpectation:
    """
    Tracks slot expectations for a specific batch.

    Maintains the slot-based coordination state between BOS and ELS.
    """

    def __init__(
        self,
        batch_id: str,
        expected_essay_ids: list[str],  # Internal essay ID slots from BOS
        timeout_seconds: int = 300,  # 5 minutes default
    ) -> None:
        self.batch_id = batch_id
        self.expected_essay_ids = set(expected_essay_ids)
        self.expected_count = len(expected_essay_ids)
        self.available_slots = set(expected_essay_ids)  # Unassigned slots
        self.slot_assignments: dict[str, SlotAssignment] = {}  # internal_essay_id -> SlotAssignment
        self.created_at = datetime.now(UTC)
        self.timeout_seconds = timeout_seconds
        self._timeout_task: asyncio.Task[None] | None = None

    @property
    def is_complete(self) -> bool:
        """Check if all expected slots are assigned."""
        return len(self.slot_assignments) >= self.expected_count

    @property
    def is_timeout_due(self) -> bool:
        """Check if batch has exceeded timeout duration."""
        elapsed = datetime.now(UTC) - self.created_at
        return elapsed > timedelta(seconds=self.timeout_seconds)

    @property
    def missing_slot_ids(self) -> list[str]:
        """Get list of internal essay ID slots still pending assignment."""
        return list(self.available_slots)

    def assign_next_slot(self, text_storage_id: str, original_file_name: str) -> str | None:
        """
        Assign content to the next available slot.

        Returns:
            The internal essay ID if assignment successful, None if no slots available
        """
        if not self.available_slots:
            logger.warning(f"No available slots for batch {self.batch_id}")
            return None

        # Get next available slot (arbitrary order)
        internal_essay_id = next(iter(self.available_slots))

        # Create assignment
        assignment = SlotAssignment(
            internal_essay_id=internal_essay_id,
            text_storage_id=text_storage_id,
            original_file_name=original_file_name,
        )

        # Update tracking state
        self.available_slots.remove(internal_essay_id)
        self.slot_assignments[internal_essay_id] = assignment

        logger.info(
            f"Assigned slot {internal_essay_id} to content {text_storage_id} "
            f"(file: {original_file_name}) for batch {self.batch_id}. "
            f"Progress: {len(self.slot_assignments)}/{self.expected_count}"
        )

        return internal_essay_id

    def mark_slot_fulfilled(self, internal_essay_id: str, text_storage_id: str) -> bool:
        """
        Mark a slot as fulfilled after successful persistence.

        Returns:
            True if this completes the batch, False otherwise
        """
        if internal_essay_id not in self.slot_assignments:
            logger.error(f"Slot {internal_essay_id} not assigned in batch {self.batch_id}")
            return False

        assignment = self.slot_assignments[internal_essay_id]
        if assignment.text_storage_id != text_storage_id:
            logger.error(
                f"Text storage ID mismatch for slot {internal_essay_id}: "
                f"expected {assignment.text_storage_id}, got {text_storage_id}"
            )
            return False

        logger.info(f"Slot {internal_essay_id} fulfilled for batch {self.batch_id}")
        return self.is_complete

    def get_ready_essays(self) -> list[EssayProcessingInputRefV1]:
        """Construct EssayProcessingInputRefV1 objects for completed assignments."""
        return [
            EssayProcessingInputRefV1(
                essay_id=assignment.internal_essay_id,
                text_storage_id=assignment.text_storage_id,
            )
            for assignment in self.slot_assignments.values()
        ]


class BatchEssayTracker:
    """
    Manages batch slot assignment and readiness tracking across multiple batches.

    Implements the ELS side of slot-based batch coordination pattern.
    Enhanced to handle validation failures and prevent infinite waits.
    """

    def __init__(self) -> None:
        self.batch_expectations: dict[str, BatchExpectation] = {}
        self.validation_failures: dict[str, list[EssayValidationFailedV1]] = {}
        self._event_callbacks: dict[str, Callable[[Any], Awaitable[None]]] = {}

    def register_event_callback(
        self, event_type: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register callback for batch coordination events."""
        self._event_callbacks[event_type] = callback

    async def register_batch(self, event: BatchEssaysRegistered) -> None:
        """
        Register batch slot expectations from BOS.

        Args:
            event: BatchEssaysRegistered event from BOS containing internal essay ID slots
        """
        batch_id = event.batch_id

        if batch_id in self.batch_expectations:
            logger.warning(f"Batch {batch_id} already registered, overwriting")

        expectation = BatchExpectation(
            batch_id=batch_id,
            expected_essay_ids=event.essay_ids,  # These are internal essay ID slots from BOS
        )

        self.batch_expectations[batch_id] = expectation

        # Start timeout monitoring
        await self._start_timeout_monitoring(expectation)

        logger.info(
            f"Registered batch {batch_id} with {len(event.essay_ids)} slots: {event.essay_ids}"
        )

    def assign_slot_to_content(
        self, batch_id: str, text_storage_id: str, original_file_name: str
    ) -> str | None:
        """
        Assign an available slot to content.

        Args:
            batch_id: The batch ID
            text_storage_id: Storage ID for the essay content
            original_file_name: Original name of uploaded file

        Returns:
            The assigned internal essay ID if successful, None if no slots available
        """
        if batch_id not in self.batch_expectations:
            logger.error(f"No expectation registered for batch {batch_id}")
            return None

        expectation = self.batch_expectations[batch_id]
        return expectation.assign_next_slot(text_storage_id, original_file_name)

    def mark_slot_fulfilled(
        self, batch_id: str, internal_essay_id: str, text_storage_id: str
    ) -> BatchEssaysReady | None:
        """
        Mark a slot as fulfilled and check if batch is complete.

        Args:
            batch_id: The batch ID
            internal_essay_id: The internal essay ID slot that was fulfilled
            text_storage_id: The text storage ID that fulfilled the slot

        Returns:
            BatchEssaysReady event if batch is complete, None otherwise
        """
        if batch_id not in self.batch_expectations:
            logger.error(f"No expectation registered for batch {batch_id}")
            return None

        expectation = self.batch_expectations[batch_id]

        # Mark slot as fulfilled
        expectation.mark_slot_fulfilled(internal_essay_id, text_storage_id)

        # Check completion: either all slots filled OR total processed meets expectation
        failure_count = len(self.validation_failures.get(batch_id, []))
        assigned_count = len(expectation.slot_assignments)
        total_processed = assigned_count + failure_count

        is_complete = expectation.is_complete or total_processed >= expectation.expected_count

        if is_complete:
            # Batch is complete!
            logger.info(
                f"Batch {batch_id} is complete: {assigned_count} assigned + {failure_count} failed = {total_processed}/{expectation.expected_count}"
            )

            # Cancel timeout monitoring
            if expectation._timeout_task:
                expectation._timeout_task.cancel()

            # Create completion event with actual text_storage_id mappings and validation failures
            ready_essays = expectation.get_ready_essays()
            failures = self.validation_failures.get(batch_id, [])

            batch_ready_event = BatchEssaysReady(
                batch_id=batch_id,
                ready_essays=ready_essays,
                batch_entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                ),
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                    timestamp=datetime.now(UTC),
                    event="batch.essays.ready",
                ),
                validation_failures=failures if failures else None,
                total_files_processed=len(ready_essays) + len(failures)
            )

            # Clean up completed batch
            del self.batch_expectations[batch_id]
            if batch_id in self.validation_failures:
                del self.validation_failures[batch_id]

            return batch_ready_event

        return None

    async def _start_timeout_monitoring(self, expectation: BatchExpectation) -> None:
        """Start timeout monitoring for a batch expectation."""

        async def timeout_monitor() -> None:
            await asyncio.sleep(expectation.timeout_seconds)

            # Check if batch is still pending
            if expectation.batch_id in self.batch_expectations:
                logger.warning(
                    f"Batch {expectation.batch_id} timed out. "
                    f"Ready: {len(expectation.slot_assignments)}/{expectation.expected_count}"
                )

                # Create timeout event
                ready_essays = expectation.get_ready_essays()
                timeout_event = BatchReadinessTimeout(
                    batch_id=expectation.batch_id,
                    ready_essays=ready_essays,
                    missing_essay_ids=expectation.missing_slot_ids,
                    expected_count=expectation.expected_count,
                    actual_count=len(expectation.slot_assignments),
                    timeout_duration_seconds=expectation.timeout_seconds,
                    metadata=SystemProcessingMetadata(
                        entity=EntityReference(entity_id=expectation.batch_id, entity_type="batch"),
                        timestamp=datetime.now(UTC),
                        event="batch.readiness.timeout",
                    ),
                )

                # Emit timeout event if callback registered
                if "batch.readiness.timeout" in self._event_callbacks:
                    await self._event_callbacks["batch.readiness.timeout"](timeout_event)

                # Clean up timed out batch
                del self.batch_expectations[expectation.batch_id]

        expectation._timeout_task = asyncio.create_task(timeout_monitor())

    def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """Get current status of a batch."""
        if batch_id not in self.batch_expectations:
            return None

        expectation = self.batch_expectations[batch_id]
        return {
            "batch_id": batch_id,
            "expected_count": expectation.expected_count,
            "ready_count": len(expectation.slot_assignments),
            "ready_essays": expectation.get_ready_essays(),
            "missing_essay_ids": expectation.missing_slot_ids,
            "is_complete": expectation.is_complete,
            "is_timeout_due": expectation.is_timeout_due,
            "created_at": expectation.created_at,
        }

    def list_active_batches(self) -> list[str]:
        """Get list of currently tracked batch IDs."""
        return list(self.batch_expectations.keys())

    async def handle_validation_failure(self, event: EssayValidationFailedV1) -> BatchEssaysReady | None:
        """
        Handle validation failure by adjusting batch expectations.

        Prevents ELS from waiting indefinitely for content that will never arrive.
        """
        batch_id = event.batch_id

        # Track validation failure
        if batch_id not in self.validation_failures:
            self.validation_failures[batch_id] = []
        self.validation_failures[batch_id].append(event)

        logger.info(
            f"Tracked validation failure for batch {batch_id}: {event.validation_error_code} "
            f"({event.original_file_name}). Total failures: {len(self.validation_failures[batch_id])}"
        )

        # Check if we should trigger early batch completion
        if batch_id in self.batch_expectations:
            expectation = self.batch_expectations[batch_id]
            failure_count = len(self.validation_failures[batch_id])
            assigned_count = len(expectation.slot_assignments)
            total_processed = assigned_count + failure_count

            logger.info(
                f"Batch {batch_id} processing status: {assigned_count} assigned + "
                f"{failure_count} failed = {total_processed}/{expectation.expected_count}"
            )

            # If processed count meets expectation, complete batch early
            if total_processed >= expectation.expected_count:
                logger.info(
                    f"Batch {batch_id} completing early: "
                    f"{assigned_count} assigned + {failure_count} failed = {total_processed}"
                )
                ready_event = self._complete_batch_with_failures(batch_id, expectation)
                return ready_event

        return None

    def _complete_batch_with_failures(
        self, batch_id: str, expectation: BatchExpectation
    ) -> BatchEssaysReady:
        """Complete batch with enhanced event including validation failures."""

        # Get validation failures for this batch
        failures = self.validation_failures.get(batch_id, [])

        # Cancel timeout monitoring
        if expectation._timeout_task:
            expectation._timeout_task.cancel()

        # Create enhanced BatchEssaysReady event
        ready_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=expectation.get_ready_essays(),
            batch_entity=EntityReference(entity_id=batch_id, entity_type="batch"),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                timestamp=datetime.now(UTC),
                event="batch.essays.ready",
            ),
            validation_failures=failures if failures else None,
            total_files_processed=len(expectation.slot_assignments) + len(failures)
        )

        logger.info(
            f"Completed batch {batch_id} with failures: "
            f"{len(expectation.slot_assignments)} successful, {len(failures)} failed, "
            f"{ready_event.total_files_processed} total processed"
        )

        # Clean up completed batch
        del self.batch_expectations[batch_id]
        if batch_id in self.validation_failures:
            del self.validation_failures[batch_id]

        return ready_event

    def check_batch_completion(self, batch_id: str) -> BatchEssaysReady | None:
        """
        Check if batch is complete and return BatchEssaysReady event if so.

        This is used to check completion after validation failures or other events
        that might complete a batch.
        """
        if batch_id not in self.batch_expectations:
            return None

        expectation = self.batch_expectations[batch_id]
        failure_count = len(self.validation_failures.get(batch_id, []))
        assigned_count = len(expectation.slot_assignments)
        total_processed = assigned_count + failure_count

        # Check if batch is complete (either all slots filled OR processed count meets expectation)
        if expectation.is_complete or total_processed >= expectation.expected_count:
            # Get validation failures for this batch
            failures = self.validation_failures.get(batch_id, [])

            # Cancel timeout monitoring
            if expectation._timeout_task:
                expectation._timeout_task.cancel()

            # Create enhanced BatchEssaysReady event
            ready_event = BatchEssaysReady(
                batch_id=batch_id,
                ready_essays=expectation.get_ready_essays(),
                batch_entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                    timestamp=datetime.now(UTC),
                    event="batch.essays.ready",
                ),
                validation_failures=failures if failures else None,
                total_files_processed=len(expectation.slot_assignments) + len(failures)
            )

            logger.info(
                f"Batch {batch_id} completion check: "
                f"{len(expectation.slot_assignments)} successful, {len(failures)} failed, "
                f"{ready_event.total_files_processed} total processed"
            )

            # Clean up completed batch
            del self.batch_expectations[batch_id]
            if batch_id in self.validation_failures:
                del self.validation_failures[batch_id]

            return ready_event

        return None
