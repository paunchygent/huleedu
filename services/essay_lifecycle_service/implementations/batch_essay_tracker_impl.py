"""
Default implementation of BatchEssayTracker protocol.

Lean implementation following clean architecture principles with proper DI.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from common_core.enums import get_course_language
from common_core.events.batch_coordination_events import (
    BatchEssaysReady,
    BatchEssaysRegistered,
    BatchReadinessTimeout,
)
from common_core.events.file_events import EssayValidationFailedV1
from common_core.metadata_models import (
    EntityReference,
    SystemProcessingMetadata,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.implementations.batch_expectation import BatchExpectation
from services.essay_lifecycle_service.protocols import BatchEssayTracker


class DefaultBatchEssayTracker(BatchEssayTracker):
    """
    Default implementation of BatchEssayTracker protocol.

    Manages batch slot assignment and readiness tracking across multiple batches.
    Implements the ELS side of slot-based batch coordination pattern.
    Enhanced to handle validation failures and prevent infinite waits.
    """

    def __init__(self) -> None:
        self._logger = create_service_logger("batch_tracker")
        self.batch_expectations: dict[str, BatchExpectation] = {}
        self.validation_failures: dict[str, list[EssayValidationFailedV1]] = {}
        self._event_callbacks: dict[str, Callable[[Any], Awaitable[None]]] = {}

    def register_event_callback(
        self, event_type: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register callback for batch coordination events."""
        self._event_callbacks[event_type] = callback

    async def register_batch(self, event: Any) -> None:  # BatchEssaysRegistered
        """
        Register batch slot expectations from BOS.

        Args:
            event: BatchEssaysRegistered event from BOS containing internal essay ID slots and course context
        """
        batch_essays_registered = BatchEssaysRegistered.model_validate(event)
        batch_id = batch_essays_registered.batch_id

        if batch_id in self.batch_expectations:
            self._logger.warning(f"Batch {batch_id} already registered, overwriting")

        expectation = BatchExpectation(
            batch_id=batch_id,
            # Internal essay ID slots from BOS
            expected_essay_ids=batch_essays_registered.essay_ids,
            # Course context from BOS
            course_code=batch_essays_registered.course_code,
            essay_instructions=batch_essays_registered.essay_instructions,
            user_id=batch_essays_registered.user_id,
        )

        self.batch_expectations[batch_id] = expectation

        # Start timeout monitoring
        await self._start_timeout_monitoring(expectation)

        self._logger.info(
            f"Registered batch {batch_id} with {len(batch_essays_registered.essay_ids)} "
            f"slots: {batch_essays_registered.essay_ids}, course: {batch_essays_registered.course_code.value}"
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
            self._logger.error(f"No expectation registered for batch {batch_id}")
            return None

        expectation = self.batch_expectations[batch_id]
        return expectation.assign_next_slot(text_storage_id, original_file_name)

    def mark_slot_fulfilled(
        self, batch_id: str, internal_essay_id: str, text_storage_id: str
    ) -> Any | None:  # BatchEssaysReady | None
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
            self._logger.error(f"No expectation registered for batch {batch_id}")
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
            return self._create_batch_ready_event(batch_id, expectation)

        return None

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

    async def handle_validation_failure(
        self, event: Any
    ) -> Any | None:  # EssayValidationFailedV1 -> BatchEssaysReady | None
        """
        Handle validation failure by adjusting batch expectations.

        Prevents ELS from waiting indefinitely for content that will never arrive.
        """
        validation_failed = EssayValidationFailedV1.model_validate(event)
        batch_id = validation_failed.batch_id

        # Track validation failure
        if batch_id not in self.validation_failures:
            self.validation_failures[batch_id] = []
        self.validation_failures[batch_id].append(validation_failed)

        self._logger.info(
            f"Tracked validation failure for batch {batch_id}: "
            f"{validation_failed.validation_error_code} ({validation_failed.original_file_name}). "
            f"Total failures: {len(self.validation_failures[batch_id])}"
        )

        # Check if we should trigger early batch completion
        if batch_id in self.batch_expectations:
            expectation = self.batch_expectations[batch_id]
            failure_count = len(self.validation_failures[batch_id])
            assigned_count = len(expectation.slot_assignments)
            total_processed = assigned_count + failure_count

            self._logger.info(
                f"Batch {batch_id} processing status: {assigned_count} assigned + "
                f"{failure_count} failed = {total_processed}/{expectation.expected_count}"
            )

            # If processed count meets expectation, complete batch early
            if total_processed >= expectation.expected_count:
                self._logger.info(
                    f"Batch {batch_id} completing early: "
                    f"{assigned_count} assigned + {failure_count} failed = {total_processed}"
                )
                return self._create_batch_ready_event(batch_id, expectation)

        return None

    def check_batch_completion(self, batch_id: str) -> Any | None:  # BatchEssaysReady | None
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
            return self._create_batch_ready_event(batch_id, expectation)

        return None

    def _create_batch_ready_event(
        self, batch_id: str, expectation: BatchExpectation
    ) -> BatchEssaysReady:
        """Create BatchEssaysReady event and clean up completed batch."""
        # Get validation failures for this batch
        failures = self.validation_failures.get(batch_id, [])

        # Cancel timeout monitoring
        if expectation._timeout_task:
            expectation._timeout_task.cancel()

        # Infer language from course code using helper function
        course_language = get_course_language(expectation.course_code).value

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
            # Enhanced lean registration fields from batch context
            course_code=expectation.course_code,
            course_language=course_language,
            essay_instructions=expectation.essay_instructions,
            class_type="GUEST",  # Placeholder - until Class Management Service integration
            teacher_first_name=None,  # No teacher info for GUEST classes
            teacher_last_name=None,  # No teacher info for GUEST classes
            validation_failures=failures if failures else None,
            total_files_processed=len(expectation.slot_assignments) + len(failures),
        )

        self._logger.info(
            f"Batch {batch_id} completed: "
            f"{len(expectation.slot_assignments)} successful, {len(failures)} failed, "
            f"{ready_event.total_files_processed} total processed, course: {expectation.course_code.value}"
        )

        # Clean up completed batch
        del self.batch_expectations[batch_id]
        if batch_id in self.validation_failures:
            del self.validation_failures[batch_id]

        return ready_event

    async def _start_timeout_monitoring(self, expectation: BatchExpectation) -> None:
        """Start timeout monitoring for a batch expectation."""

        async def timeout_monitor() -> None:
            await asyncio.sleep(expectation.timeout_seconds)

            # Check if batch is still pending
            if expectation.batch_id in self.batch_expectations:
                self._logger.warning(
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
