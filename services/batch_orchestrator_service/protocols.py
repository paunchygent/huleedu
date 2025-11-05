"""Protocol definitions for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from common_core.metadata_models import EssayProcessingInputRefV1

# Import observability enums for metrics collection
from common_core.observability_enums import OperationType

# Import common_core models for standardized interfaces
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus, ProcessingPipelineState
from common_core.status_enums import BatchStatus, EssayStatus, OperationStatus, ValidationStatus

# Import the new API model for batch context storage
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1

# Assuming common_core models might be used in signatures


# Note: Custom exceptions removed in favor of HuleEduError pattern
# Use raise_validation_error for data validation issues
# Use raise_processing_error for phase initiation failures
# Use raise_kafka_publish_error for command publishing failures


# Placeholder for a Pydantic model representing a BatchUpload entity
# if not directly from common_core
# If BatchUpload is a Pydantic model defined elsewhere (e.g., common_core.models.batch.BatchUpload)
# then that should be imported instead.
class BatchUpload:  # Placeholder for actual BatchUpload Pydantic model
    pass


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
        correlation_id: UUID,
        essays_for_processing: list[EssayProcessingInputRefV1],
        batch_context: BatchRegistrationRequestV1,
    ) -> None:
        """
        Initiate a specific pipeline phase for the batch.

        Args:
            batch_id: Unique identifier of the batch
            phase_to_initiate: The phase to initiate (type-safe enum)
            correlation_id: Correlation ID for event tracing
            essays_for_processing: List of essays with their content references
            batch_context: Full batch context from registration

        Raises:
            HuleEduError: If phase initiation cannot proceed
        """
        pass


class SpellcheckInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating spellcheck operations.

    Inherits from PipelinePhaseInitiatorProtocol for standardized interface,
    primarily for semantic grouping and potential future spellcheck-specific methods.
    """

    pass


class StudentMatchingInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating Phase 1 student matching operations.

    Inherits from PipelinePhaseInitiatorProtocol for standardized interface,
    used for REGULAR batches that require student-essay association validation.
    """

    pass


class BatchRepositoryProtocol(Protocol):
    """Protocol for batch data persistence operations."""

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        """Retrieve batch data by ID."""
        pass

    async def create_batch(self, batch_data: dict) -> dict:
        """Create a new batch record."""
        pass

    async def update_batch_status(self, batch_id: str, new_status: BatchStatus) -> bool:
        """Update the status of an existing batch."""
        pass

    async def save_processing_pipeline_state(
        self, batch_id: str, pipeline_state: ProcessingPipelineState
    ) -> bool:
        """Save pipeline processing state for a batch."""
        pass

    async def get_processing_pipeline_state(self, batch_id: str) -> ProcessingPipelineState | None:
        """Retrieve pipeline processing state for a batch."""
        pass

    async def store_batch_context(
        self,
        batch_id: str,
        registration_data: BatchRegistrationRequestV1,
        correlation_id: str | None = None,
    ) -> bool:
        """Store batch context information."""
        pass

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        """Retrieve batch context information."""
        pass

    async def store_batch_essays(self, batch_id: str, essays: list[Any]) -> bool:
        """Store essay data from BatchEssaysReady event for later pipeline processing."""
        pass

    async def get_batch_essays(self, batch_id: str) -> list[Any] | None:
        """Retrieve stored essay data for pipeline processing."""
        pass

    async def update_phase_status_atomically(
        self,
        batch_id: str,
        phase_name: PhaseName,
        expected_status: PipelineExecutionStatus,
        new_status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
        correlation_id: str | None = None,
    ) -> bool:
        """
        Atomically update phase status if current status matches expected.

        Returns True if update was successful, False if status didn't match expected
        (indicating another process already updated it).

        This method prevents race conditions in phase initiation.

        Note: Uses PipelineExecutionStatus enum for internal pipeline state management.
        """
        pass


class BatchEventPublisherProtocol(Protocol):
    """Protocol for publishing batch-related events."""

    async def publish_batch_event(
        self,
        event_envelope: Any,
        key: str | None = None,
        session: Any | None = None,
    ) -> None:
        """Publish a batch event using TRUE OUTBOX PATTERN."""
        pass


class EssayLifecycleClientProtocol(Protocol):
    """Protocol for interacting with Essay Lifecycle Service."""

    async def get_essay_status(self, essay_id: str) -> dict | None:
        """Retrieve the current status of an essay from ELS."""
        pass

    async def update_essay_status(self, essay_id: str, new_status: EssayStatus) -> bool:
        """Update the status of an essay in ELS."""
        pass


class BatchProcessingServiceProtocol(Protocol):
    """Protocol for batch processing service operations."""

    async def register_new_batch(
        self,
        registration_data: BatchRegistrationRequestV1,
        correlation_id: UUID,
    ) -> str:
        """Register a new batch for processing and return the batch ID."""
        pass


class PipelinePhaseCoordinatorProtocol(Protocol):
    """Protocol for coordinating pipeline phase transitions."""

    async def handle_phase_concluded(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        phase_status: BatchStatus,
        correlation_id: UUID,
        processed_essays_for_next_phase: list[Any] | None = None,
    ) -> None:
        """Handle completion of a pipeline phase and determine next actions."""
        pass

    async def update_phase_status(
        self,
        batch_id: str,
        phase: PhaseName,
        status: PipelineExecutionStatus,
        correlation_id: UUID,
        completion_timestamp: str | None = None,
    ) -> None:
        """Update the status of a specific pipeline phase."""
        pass

    async def initiate_resolved_pipeline(
        self,
        batch_id: str,
        resolved_pipeline: list[PhaseName],
        correlation_id: UUID,
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
            HuleEduError: If pipeline initiation fails or resolved pipeline is invalid
        """
        pass


class CJAssessmentInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating CJ assessment operations.

    Now implements the standardized PipelinePhaseInitiatorProtocol interface
    for consistency with other phase initiators.
    """


class AIFeedbackInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating AI feedback operations.

    Inherits from PipelinePhaseInitiatorProtocol for standardized interface,
    primarily for semantic grouping and potential future AI feedback-specific methods.

    Note: AI Feedback Service is not yet implemented - this initiator will publish
    commands that will be consumed once the AI Feedback Service is built.
    """


class NLPInitiatorProtocol(PipelinePhaseInitiatorProtocol, Protocol):
    """
    Protocol for initiating NLP processing operations.

    Inherits from PipelinePhaseInitiatorProtocol for standardized interface,
    primarily for semantic grouping and potential future NLP-specific methods.

    Publishes commands to Kafka topics consumed by the NLP Service for both
    Phase 1 student matching and Phase 2 text analysis operations.
    """


class BatchConductorClientProtocol(Protocol):
    """Protocol for HTTP communication with Batch Conductor Service."""

    async def resolve_pipeline(
        self,
        batch_id: str,
        requested_pipeline: PhaseName,
        correlation_id: str,
        batch_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Request pipeline resolution from BCS internal API.

        Args:
            batch_id: The unique identifier of the target batch
            requested_pipeline: The final pipeline the user wants to run
            correlation_id: The correlation ID from the original request for event tracking
            batch_metadata: Optional metadata (e.g., prompt attachment flags) needed for validation

        Returns:
            BCS response containing resolved pipeline and analysis

        Raises:
            Exception: If BCS communication fails or returns error
        """
        pass

    async def report_phase_completion(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        success: bool = True,
    ) -> None:
        """
        Report phase completion to BCS for tracking and dependency resolution.

        Args:
            batch_id: The unique identifier of the batch
            completed_phase: The phase that has completed
            success: Whether the phase completed successfully

        Note: This is a best-effort operation - failures should be logged but not block.
        """
        pass


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
        pass

    def record_validation_operation(
        self,
        validation_status: ValidationStatus,
        batch_id: str,
        error_details: str | None = None,
    ) -> None:
        """Record validation operation metrics."""
        pass


class EntitlementsServiceProtocol(Protocol):
    """Protocol for interacting with the Entitlements Service for credit checking."""

    async def check_credits_bulk(
        self,
        user_id: str,
        org_id: str | None,
        requirements: dict[str, int],
        correlation_id: str,
    ) -> dict[str, Any]:
        """Bulk credit check for multiple metrics atomically.

        Args:
            user_id: User requesting the credits
            org_id: Organization ID (if applicable)
            requirements: Mapping of metric -> quantity
            correlation_id: Request correlation ID for tracing

        Returns:
            Dict with 'allowed' bool, optional 'denial_reason', balances and per-metric details
        """
        pass
