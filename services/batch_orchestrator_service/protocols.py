"""Protocol definitions for Batch Orchestrator Service."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

# Import the new API model for batch context storage
from api_models import BatchRegistrationRequestV1

# Assuming common_core models might be used in signatures


# Placeholder for a Pydantic model representing a BatchUpload entity
# if not directly from common_core
# If BatchUpload is a Pydantic model defined elsewhere (e.g., common_core.models.batch.BatchUpload)
# then that should be imported instead.
class BatchUpload: ...  # Placeholder for actual BatchUpload Pydantic model


class BatchRepositoryProtocol(Protocol):
    """Protocol for batch data persistence operations."""

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Retrieve a batch by its ID."""
        ...

    async def create_batch(self, batch_data: dict) -> dict:
        """Create a new batch and return it with an ID."""
        ...

    async def update_batch_status(self, batch_id: str, new_status: str) -> bool:
        """Update the status of a batch."""
        # new_status would ideally be from common_core.enums.BatchStatus
        ...

    async def save_processing_pipeline_state(self, batch_id: str, pipeline_state: dict) -> bool:
        """Save the processing pipeline state for a batch."""
        ...

    async def get_processing_pipeline_state(self, batch_id: str) -> dict | None:
        """Retrieve the processing pipeline state for a batch."""
        ...

    async def store_batch_context(
        self, batch_id: str, registration_data: BatchRegistrationRequestV1
    ) -> bool:
        """Store the full batch context including course info and essay instructions."""
        ...

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        """Retrieve the stored batch context for a given batch ID."""
        ...


class BatchEventPublisherProtocol(Protocol):
    """Protocol for publishing batch-related events."""

    async def publish_batch_event(self, event_envelope: Any) -> None:
        """Publish a batch event to the appropriate Kafka topic."""
        ...


class EssayLifecycleClientProtocol(Protocol):
    """Protocol for interacting with Essay Lifecycle Service."""

    async def get_essay_status(self, essay_id: str) -> dict | None:
        """Retrieve the current status of an essay from ELS."""
        ...

    async def update_essay_status(self, essay_id: str, new_status: str) -> bool:
        """Update the status of an essay in ELS."""
        ...


class BatchProcessingServiceProtocol(Protocol):
    """Protocol for batch processing service operations."""

    async def register_new_batch(
        self, registration_data: BatchRegistrationRequestV1, correlation_id: uuid.UUID
    ) -> str:
        """Register a new batch for processing and return the batch ID."""
        ...


class PipelinePhaseCoordinatorProtocol(Protocol):
    """Protocol for coordinating pipeline phase transitions."""

    async def handle_phase_concluded(
        self,
        batch_id: str,
        completed_phase: str,
        phase_status: str,
        correlation_id: str,
        processed_essays_for_next_phase: list[Any] | None = None,
    ) -> None:
        """Handle completion of a pipeline phase and determine next actions."""
        ...

    async def update_phase_status(
        self,
        batch_id: str,
        phase: str,
        status: str,
        completion_timestamp: str | None = None,
    ) -> None:
        """Update the status of a specific pipeline phase."""
        ...


class CJAssessmentInitiatorProtocol(Protocol):
    """Protocol for initiating CJ assessment operations."""

    async def initiate_cj_assessment(
        self,
        batch_id: str,
        batch_context: BatchRegistrationRequestV1,
        correlation_id: str,
        essays_to_process: list[Any] | None = None,
    ) -> None:
        """Initiate CJ assessment for a batch with the given context."""
        ...

    async def can_initiate_cj_assessment(
        self,
        batch_context: BatchRegistrationRequestV1,
        current_pipeline_state: dict,
    ) -> bool:
        """Check if CJ assessment can be initiated for the given batch context."""
        ...
