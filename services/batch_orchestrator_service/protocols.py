from __future__ import annotations

from typing import Any, List, Optional, Protocol

# Import the new API model for batch context storage
from api_models import BatchRegistrationRequestV1

# Assuming common_core models might be used in signatures
from common_core.events.envelope import EventEnvelope
from common_core.pipeline_models import ProcessingPipelineState


# Placeholder for a Pydantic model representing a BatchUpload entity
# if not directly from common_core
# If BatchUpload is a Pydantic model defined elsewhere (e.g., common_core.models.batch.BatchUpload)
# then that should be imported instead.
class BatchUpload: ...  # Placeholder for actual BatchUpload Pydantic model


class BatchRepositoryProtocol(Protocol):
    async def get_batch_by_id(self, batch_id: str) -> BatchUpload | None:
        """Retrieves a batch by its ID."""
        ...

    async def create_batch(self, batch_data: BatchUpload) -> BatchUpload:
        """Creates a new batch and returns the created entity."""
        ...

    async def update_batch_status(self, batch_id: str, new_status: str) -> bool:
        """Updates the status of a batch."""
        # new_status would ideally be from common_core.enums.BatchStatus
        ...

    async def save_processing_pipeline_state(
        self, batch_id: str, pipeline_state: ProcessingPipelineState
    ) -> bool:
        """Saves or updates the detailed processing pipeline state for a batch."""
        ...

    async def get_processing_pipeline_state(
        self, batch_id: str
    ) -> dict | None:
        """Retrieves the detailed processing pipeline state for a batch.

        Args:
            batch_id: Unique identifier for the batch

        Returns:
            The pipeline state dictionary if found, None otherwise
        """
        ...

    async def store_batch_context(
        self, batch_id: str, registration_data: BatchRegistrationRequestV1
    ) -> bool:
        """Stores the full batch context including course info and essay instructions.

        Args:
            batch_id: Unique identifier for the batch
            registration_data: Complete batch registration data including course_code,
                             class_designation, essay_instructions, etc.

        Returns:
            True if storage was successful, False otherwise
        """
        ...

    async def get_batch_context(self, batch_id: str) -> Optional[BatchRegistrationRequestV1]:
        """Retrieves the stored batch context for a given batch ID.

        Args:
            batch_id: Unique identifier for the batch

        Returns:
            The batch registration data if found, None otherwise
        """
        ...


class BatchEventPublisherProtocol(Protocol):
    async def publish_batch_event(self, event_envelope: EventEnvelope[Any]) -> None:
        """Publishes a batch-related event to the event bus."""
        ...


class EssayLifecycleClientProtocol(Protocol):
    async def request_essay_phase_initiation(
        self,
        batch_id: str,
        essay_ids: List[str],
        phase: str,  # phase might be an Enum too
    ) -> None:
        """Requests the Essay Lifecycle Service to initiate a processing phase for essays."""
        ...
