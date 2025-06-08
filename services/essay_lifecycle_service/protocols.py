"""
Protocol interfaces for the Essay Lifecycle Service.

This module defines typing.Protocol interfaces for all ELS dependencies to enable
proper dependency injection and testability.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from common_core.enums import ContentType, EssayStatus
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1


class EssayState(Protocol):
    """Protocol for essay state data model."""

    essay_id: str
    batch_id: str | None
    current_status: EssayStatus
    processing_metadata: dict[str, Any]
    timeline: dict[str, Any]
    storage_references: dict[ContentType, str]
    created_at: Any  # datetime
    updated_at: Any  # datetime


class EssayRepositoryProtocol(Protocol):
    """
    Protocol for essay state persistence operations.

    This follows the repository pattern established by BOS BatchRepositoryProtocol,
    providing an abstraction layer for essay state persistence that supports
    both SQLite (development/testing) and PostgreSQL (production) implementations.
    """

    async def get_essay_state(self, essay_id: str) -> EssayState | None:
        """Retrieve essay state by ID."""
        ...

    async def update_essay_state(
        self, essay_id: str, new_status: EssayStatus, metadata: dict[str, Any]
    ) -> None:
        """Update essay state with new status and metadata."""
        ...

    async def update_essay_status_via_machine(
        self, essay_id: str, new_status: EssayStatus, metadata: dict[str, Any]
    ) -> None:
        """Update essay state using status from state machine."""
        ...

    async def create_essay_record(self, essay_ref: EntityReference) -> EssayState:
        """Create new essay record from entity reference."""
        ...

    async def list_essays_by_batch(self, batch_id: str) -> list[EssayState]:
        """List all essays in a batch."""
        ...

    async def get_batch_status_summary(self, batch_id: str) -> dict[EssayStatus, int]:
        """Get status count breakdown for a batch."""
        ...

    async def get_essay_by_text_storage_id_and_batch_id(
        self, batch_id: str, text_storage_id: str
    ) -> EssayState | None:
        """Retrieve essay state by text_storage_id and batch_id for idempotency checking."""
        ...

    async def create_or_update_essay_state_for_slot_assignment(
        self,
        internal_essay_id: str,
        batch_id: str,
        text_storage_id: str,
        original_file_name: str,
        file_size: int,
        content_hash: str | None,
        initial_status: EssayStatus,
    ) -> EssayState:
        """Create or update essay state for slot assignment with content metadata."""
        ...

    async def list_essays_by_batch_and_phase(
        self, batch_id: str, phase_name: str
    ) -> list[EssayState]:
        """List all essays in a batch that are part of a specific processing phase."""
        ...


class EventPublisher(Protocol):
    """Protocol for publishing events to Kafka."""

    async def publish_status_update(
        self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID | None = None
    ) -> None:
        """Publish essay status update event."""
        ...

    async def publish_batch_phase_progress(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
        total_essays_in_phase: int,
        correlation_id: UUID | None = None,
    ) -> None:
        """Report aggregated progress of a specific phase for a batch to BS."""
        ...

    async def publish_batch_phase_concluded(
        self,
        batch_id: str,
        phase: str,
        status: str,
        details: dict[str, Any],
        correlation_id: UUID | None = None,
    ) -> None:
        """Report the final conclusion of a phase for a batch to BS."""
        ...

    async def publish_excess_content_provisioned(
        self,
        event_data: Any,  # ExcessContentProvisionedV1
        correlation_id: UUID | None = None,
    ) -> None:
        """Publish ExcessContentProvisionedV1 event when no slots are available."""
        ...

    async def publish_batch_essays_ready(
        self,
        event_data: Any,  # BatchEssaysReady
        correlation_id: UUID | None = None,
    ) -> None:
        """Publish BatchEssaysReady event when batch is complete."""
        ...

    async def publish_els_batch_phase_outcome(
        self,
        event_data: Any,  # ELSBatchPhaseOutcomeV1
        correlation_id: UUID | None = None,
    ) -> None:
        """Publish ELSBatchPhaseOutcomeV1 event when batch phase is complete."""
        ...


class BatchCommandHandler(Protocol):
    """Protocol for handling batch processing commands from Batch Service."""

    async def process_initiate_spellcheck_command(
        self,
        command_data: Any,  # BatchServiceSpellcheckInitiateCommandDataV1
        correlation_id: UUID | None = None,
    ) -> None:
        """Process spellcheck phase initiation command from Batch Service."""
        ...

    async def process_initiate_nlp_command(
        self,
        command_data: Any,  # BatchServiceNLPInitiateCommandDataV1
        correlation_id: UUID | None = None,
    ) -> None:
        """Process NLP phase initiation command from Batch Service."""
        ...

    async def process_initiate_ai_feedback_command(
        self,
        command_data: Any,  # BatchServiceAIFeedbackInitiateCommandDataV1
        correlation_id: UUID | None = None,
    ) -> None:
        """Process AI feedback phase initiation command from Batch Service."""
        ...

    async def process_initiate_cj_assessment_command(
        self,
        command_data: Any,  # BatchServiceCJAssessmentInitiateCommandDataV1
        correlation_id: UUID | None = None,
    ) -> None:
        """Process CJ assessment phase initiation command from Batch Service."""
        ...


class BatchCoordinationHandler(Protocol):
    """Protocol for handling batch coordination events."""

    async def handle_batch_essays_registered(
        self,
        event_data: Any,  # BatchEssaysRegistered
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle batch registration from BOS."""
        ...

    async def handle_essay_content_provisioned(
        self,
        event_data: Any,  # EssayContentProvisionedV1
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle content provisioning and slot assignment."""
        ...

    async def handle_essay_validation_failed(
        self,
        event_data: Any,  # EssayValidationFailedV1
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle validation failure events for coordination."""
        ...


class ServiceResultHandler(Protocol):
    """Protocol for handling specialized service result events."""

    async def handle_spellcheck_result(
        self,
        result_data: Any,  # SpellcheckResultDataV1
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle spellcheck result from Spell Checker Service."""
        ...

    async def handle_cj_assessment_completed(
        self,
        result_data: Any,  # CJAssessmentCompletedV1
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle CJ assessment completion from CJ Assessment Service."""
        ...

    async def handle_cj_assessment_failed(
        self,
        result_data: Any,  # CJAssessmentFailedV1
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle CJ assessment failure from CJ Assessment Service."""
        ...


class BatchPhaseCoordinator(Protocol):
    """Protocol for coordinating batch-level phase completion and outcome publishing."""

    async def check_batch_completion(
        self,
        essay_state: EssayState,
        phase_name: str,
        correlation_id: UUID | None = None,
    ) -> None:
        """
        Check if all essays in a batch phase are complete and publish ELSBatchPhaseOutcomeV1 if so.

        This method should be called after individual essay state updates to trigger
        batch-level aggregation and outcome publishing when a phase is complete.

        Args:
            essay_state: The essay state that was just updated
            phase_name: Name of the processing phase (e.g., 'spellcheck', 'cj_assessment')
            correlation_id: Optional correlation ID for event tracking
        """
        ...


class SpecializedServiceRequestDispatcher(Protocol):
    """Protocol for dispatching individual essay processing requests to Specialized Services."""

    async def dispatch_spellcheck_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: str,
        correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch spellcheck requests to Spellcheck Service."""
        ...

    async def dispatch_nlp_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: str,
        batch_correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch NLP requests to NLP Service."""
        ...

    async def dispatch_ai_feedback_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        context: Any,  # AIFeedbackBatchContextDataV1 (to be defined)
        batch_correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch AI feedback requests to AI Feedback Service."""
        ...

    async def dispatch_cj_assessment_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: str,
        course_code: str,
        essay_instructions: str,
        batch_id: str,
        correlation_id: UUID | None = None,
    ) -> None:
        """Dispatch CJ assessment requests to CJ Assessment Service."""
        ...


class StateTransitionValidator(Protocol):
    """Protocol for validating essay state transitions."""

    def validate_transition(self, current_status: EssayStatus, target_status: EssayStatus) -> bool:
        """Validate if state transition is allowed."""
        ...

    def get_next_valid_statuses(self, current_status: EssayStatus) -> list[EssayStatus]:
        """Get list of valid next statuses from current state."""
        ...


class ContentClient(Protocol):
    """Protocol for interacting with Content Service."""

    async def fetch_content(self, storage_id: str) -> bytes:
        """Fetch content from storage by ID."""
        ...

    async def store_content(self, content: bytes, content_type: ContentType) -> str:
        """Store content and return storage ID."""
        ...


class MetricsCollector(Protocol):
    """Protocol for collecting service metrics."""

    def record_state_transition(self, from_status: str, to_status: str) -> None:
        """Record a state transition metric."""
        ...

    def record_processing_time(self, operation: str, duration_ms: float) -> None:
        """Record processing time for an operation."""
        ...

    def increment_counter(self, metric_name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        ...


class BatchEssayTracker(Protocol):
    """Protocol for tracking batch readiness and coordination."""

    async def register_batch(self, event: Any) -> None:  # BatchEssaysRegistered
        """Register batch expectations from BOS."""
        ...

    def assign_slot_to_content(
        self, batch_id: str, text_storage_id: str, original_file_name: str
    ) -> str | None:
        """Assign an available slot to content and return assigned internal essay ID."""
        ...

    def mark_slot_fulfilled(
        self, batch_id: str, internal_essay_id: str, text_storage_id: str
    ) -> Any | None:  # BatchEssaysReady | None
        """Mark a slot as fulfilled and check if batch is complete."""
        ...

    def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """Get current status of a batch."""
        ...

    def list_active_batches(self) -> list[str]:
        """Get list of currently tracked batch IDs."""
        ...

    def register_event_callback(
        self, event_type: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register callback for batch coordination events."""
        ...

    async def handle_validation_failure(
        self, event: Any
    ) -> Any | None:  # EssayValidationFailedV1 -> BatchEssaysReady | None
        """Handle validation failure event for batch coordination."""
        ...

    def check_batch_completion(self, batch_id: str) -> Any | None:  # BatchEssaysReady | None
        """Check if batch is complete and return BatchEssaysReady event if so."""
        ...
