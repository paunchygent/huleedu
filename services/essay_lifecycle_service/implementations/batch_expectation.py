"""
Batch expectation business logic for slot-based coordination.

Tracks slot expectations and assignments for batch coordination between BOS and ELS.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from common_core.domain_enums import CourseCode
from common_core.metadata_models import EssayProcessingInputRefV1
from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.implementations.slot_assignment import SlotAssignment


class BatchExpectation:
    """
    Tracks slot expectations for a specific batch.

    Maintains the slot-based coordination state between BOS and ELS.
    Enhanced to include course context for proper BatchEssaysReady event creation.
    """

    def __init__(
        self,
        batch_id: str,
        expected_essay_ids: list[str],  # Internal essay ID slots from BOS
        course_code: CourseCode,
        essay_instructions: str,
        user_id: str,
        timeout_seconds: int = 300,  # 5 minutes default
    ) -> None:
        self.batch_id = batch_id
        self.expected_essay_ids = set(expected_essay_ids)
        self.expected_count = len(expected_essay_ids)
        self.available_slots = set(expected_essay_ids)  # Unassigned slots
        self.slot_assignments: dict[str, SlotAssignment] = {}  # internal_essay_id -> SlotAssignment

        # Course context from BOS
        self.course_code = course_code
        self.essay_instructions = essay_instructions
        self.user_id = user_id

        self.created_at = datetime.now(UTC)
        self.timeout_seconds = timeout_seconds
        self._timeout_task: asyncio.Task[None] | None = None
        self._logger = create_service_logger("batch_expectation")

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
            self._logger.warning(f"No available slots for batch {self.batch_id}")
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

        self._logger.info(
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
            self._logger.error(f"Slot {internal_essay_id} not assigned in batch {self.batch_id}")
            return False

        assignment = self.slot_assignments[internal_essay_id]
        if assignment.text_storage_id != text_storage_id:
            self._logger.error(
                f"Text storage ID mismatch for slot {internal_essay_id}: "
                f"expected {assignment.text_storage_id}, got {text_storage_id}"
            )
            return False

        self._logger.info(f"Slot {internal_essay_id} fulfilled for batch {self.batch_id}")
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
