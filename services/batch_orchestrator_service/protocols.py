"""Protocol definitions for Batch Orchestrator Service."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

# Import the new API model for batch context storage
from api_models import BatchRegistrationRequestV1

from common_core.metadata_models import EssayProcessingInputRefV1

# Import observability enums for metrics collection
from common_core.observability_enums import OperationType

# Import common_core models for standardized interfaces
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus
from common_core.status_enums import BatchStatus, EssayStatus, OperationStatus, ValidationStatus

# Assuming common_core models might be used in signatures


# Exception hierarchy for phase initiation errors
class InitiationError(Exception):
    """Base exception for errors occurring during phase initiation."""

    pass


class DataValidationError(InitiationError):
    """Raised when critical data is missing or invalid for phase initiation."""

    pass


class CommandPublishError(InitiationError):
    """Raised when command publishing to event system fails."""

    pass


# Placeholder for a Pydantic model representing a BatchUpload entity
# if not directly from common_core
# If BatchUpload is a Pydantic model defined elsewhere (e.g., common_core.models.batch.BatchUpload)
# then that should be imported instead.
class BatchUpload: ...  # Placeholder for actual BatchUpload Pydantic model


class PipelinePhaseInitiatorProtocol(Protocol):
    """
    Protocol for initiating pipeline phases with standardized interface.

    This protocol provides a uniform interface for all phase initiators,
    enabling dynamic dispatch through the phase_initiators_map.
    All concrete initiators must implement this interface.
    """

    async def initiate_phase(
        self,
        batch_id: str,
        phase_to_initiate: PhaseName,
        correlation_id: uuid.UUID | None,
        essays_for_processing: list[EssayProcessingInputRefV1],
        batch_context: BatchRegistrationRequestV1,
    ) -> None:
        """
        Initiate a specific pipeline phase for the batch.

        Args:
            batch_id: Unique identifier of the batch
            phase_to_initiate: The phase to initiate (type-safe enum)
            correlation_id: Optional correlation ID for event tracing
            essays_for_processing: List of essays with their content references
            batch_context: Full batch context from registration

        Raises:
            InitiationError: If phase initiation cannot proceed
        """
        ...


class SpellcheckInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating spellcheck operations.

    Inherits from PipelinePhaseInitiatorProtocol for standardized interface,
    primarily for semantic grouping and potential future spellcheck-specific methods.
    """

    pass


class BatchRepositoryProtocol(Protocol):
    """Protocol for batch data persistence operations."""

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Retrieve batch data by ID."""
        ...

    async def create_batch(self, batch_data: dict) -> dict:
        """Create a new batch record."""
        ...

    async def update_batch_status(self, batch_id: str, new_status: BatchStatus) -> bool:
        """Update the status of an existing batch."""
        ...

    async def save_processing_pipeline_state(self, batch_id: str, pipeline_state: dict) -> bool:
        """Save pipeline processing state for a batch."""
        ...

    async def get_processing_pipeline_state(self, batch_id: str) -> dict | None:
        """Retrieve pipeline processing state for a batch."""
        ...

    async def store_batch_context(
        self,
        batch_id: str,
        registration_data: BatchRegistrationRequestV1,
    ) -> bool:
        """Store batch context information."""
        ...

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        """Retrieve batch context information."""
        ...

    async def store_batch_essays(self, batch_id: str, essays: list[Any]) -> bool:
        """Store essay data from BatchEssaysReady event for later pipeline processing."""
        ...

    async def get_batch_essays(self, batch_id: str) -> list[Any] | None:
        """Retrieve stored essay data for pipeline processing."""
        ...

    async def update_phase_status_atomically(
        self,
        batch_id: str,
        phase_name: PhaseName,
        expected_status: PipelineExecutionStatus,
        new_status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
    ) -> bool:
        """
        Atomically update phase status if current status matches expected.

        Returns True if update was successful, False if status didn't match expected
        (indicating another process already updated it).

        This method prevents race conditions in phase initiation.

        Note: Uses PipelineExecutionStatus enum for internal pipeline state management.
        """
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

    async def update_essay_status(self, essay_id: str, new_status: EssayStatus) -> bool:
        """Update the status of an essay in ELS."""
        ...


class BatchProcessingServiceProtocol(Protocol):
    """Protocol for batch processing service operations."""

    async def register_new_batch(
        self,
        registration_data: BatchRegistrationRequestV1,
        correlation_id: uuid.UUID,
    ) -> str:
        """Register a new batch for processing and return the batch ID."""
        ...


class PipelinePhaseCoordinatorProtocol(Protocol):
    """Protocol for coordinating pipeline phase transitions."""

    async def handle_phase_concluded(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        phase_status: BatchStatus,
        correlation_id: str,
        processed_essays_for_next_phase: list[Any] | None = None,
    ) -> None:
        """Handle completion of a pipeline phase and determine next actions."""
        ...

    async def update_phase_status(
        self,
        batch_id: str,
        phase: PhaseName,
        status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
    ) -> None:
        """Update the status of a specific pipeline phase."""
        ...

    async def initiate_resolved_pipeline(
        self,
        batch_id: str,
        resolved_pipeline: list[PhaseName],
        correlation_id: str,
        batch_context: Any,
    ) -> None:
        """
        Initiate execution of the first phase in a BCS-resolved pipeline.

        Called after ClientBatchPipelineRequestV1 processing to start execution
        of the resolved pipeline returned by BCS.

        Args:
            batch_id: Unique identifier of the batch
            resolved_pipeline: BCS-resolved pipeline sequence using PhaseName enum values
            correlation_id: Event correlation ID for tracing
            batch_context: Full batch context for essay retrieval

        Raises:
            InitiationError: If pipeline initiation fails
            DataValidationError: If resolved pipeline is invalid
        """
        ...


class CJAssessmentInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating CJ assessment operations.

    Now implements the standardized PipelinePhaseInitiatorProtocol interface
    for consistency with other phase initiators.
    """

    pass


class AIFeedbackInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating AI feedback operations.

    Inherits from PipelinePhaseInitiatorProtocol for standardized interface,
    primarily for semantic grouping and potential future AI feedback-specific methods.

    Note: AI Feedback Service is not yet implemented - this initiator will publish
    commands that will be consumed once the AI Feedback Service is built.
    """

    pass


class NLPInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating NLP processing operations.

    Inherits from PipelinePhaseInitiatorProtocol for standardized interface,
    primarily for semantic grouping and potential future NLP-specific methods.

    Note: NLP Service is not yet implemented - this initiator will publish
    commands that will be consumed once the NLP Service is built.
    """

    pass


class BatchConductorClientProtocol(Protocol):
    """Protocol for HTTP communication with Batch Conductor Service."""

    async def resolve_pipeline(
        self, batch_id: str, requested_pipeline: PhaseName
    ) -> dict[str, Any]:
        """
        Request pipeline resolution from BCS internal API.

        Args:
            batch_id: The unique identifier of the target batch
            requested_pipeline: The final pipeline the user wants to run

        Returns:
            BCS response containing resolved pipeline and analysis

        Raises:
            Exception: If BCS communication fails or returns error
        """
        ...


class BatchMetricsProtocol(Protocol):
    """Protocol for batch processing metrics collection."""

    def record_pipeline_operation(
        self,
        operation: OperationType,
        status: OperationStatus,
        pipeline_type: PhaseName,
        batch_id: str,
    ) -> None:
        """Record pipeline operation metrics with standardized enum types."""
        ...

    def record_validation_operation(
        self,
        validation_status: ValidationStatus,
        batch_id: str,
        error_details: str | None = None,
    ) -> None:
        """Record validation operation metrics."""
        ...
