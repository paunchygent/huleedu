"""
Protocol interfaces for the Essay Lifecycle Service.

This module defines typing.Protocol interfaces for all ELS dependencies to enable
proper dependency injection and testability.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import UUID

from common_core.domain_enums import ContentType, CourseCode, Language
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus
from sqlalchemy.ext.asyncio import AsyncSession


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
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        session: AsyncSession | None = None,
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """Update essay state with new status and metadata."""
        ...

    async def update_essay_status_via_machine(
        self,
        essay_id: str,
        new_status: EssayStatus,
        metadata: dict[str, Any],
        session: AsyncSession | None = None,
        storage_reference: tuple[ContentType, str] | None = None,
        correlation_id: UUID | None = None,
    ) -> None:
        """Update essay state using status from state machine."""
        ...

    async def create_essay_record(
        self,
        essay_id: str,
        batch_id: str | None = None,
        entity_type: str = "essay",
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> EssayState:
        """Create new essay record from primitive parameters."""
        ...

    async def create_essay_records_batch(
        self,
        essay_data: list[dict[str, str | None]],
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> list[EssayState]:
        """Create multiple essay records in single atomic transaction.

        Args:
            essay_data: List of dicts with keys: essay_id, batch_id, entity_type
        """
        ...

    async def list_essays_by_batch(self, batch_id: str) -> list[EssayState]:
        """List all essays in a batch."""
        ...

    async def get_batch_status_summary(self, batch_id: str) -> dict[EssayStatus, int]:
        """Get status count breakdown for a batch."""
        ...

    async def get_batch_summary_with_essays(
        self, batch_id: str
    ) -> tuple[list[EssayState], dict[EssayStatus, int]]:
        """Get both essays and status summary for a batch in single operation (prevents N+1 queries)."""
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
        session: AsyncSession | None = None,
        correlation_id: UUID | None = None,
    ) -> EssayState:
        """Create or update essay state for slot assignment with content metadata."""
        ...

    async def list_essays_by_batch_and_phase(
        self, batch_id: str, phase_name: str, session: AsyncSession | None = None
    ) -> list[EssayState]:
        """List all essays in a batch that are part of a specific processing phase."""
        ...

    async def create_essay_state_with_content_idempotency(
        self,
        batch_id: str,
        text_storage_id: str,
        essay_data: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> tuple[bool, str | None]:
        """
        Create essay state with atomic idempotency check for content provisioning.

        Returns tuple of (was_created, essay_id) where was_created indicates if this
        was a new creation (True) or idempotent case (False).

        Addresses ELS-002 Phase 1 requirements for database-level race condition prevention.
        """
        ...

    def get_session_factory(self) -> Any:
        """Get the session factory for transaction management."""
        ...


class EventPublisher(Protocol):
    """Protocol for publishing events to Kafka."""

    async def publish_status_update(
        self, essay_id: str, batch_id: str | None, status: EssayStatus, correlation_id: UUID
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
        correlation_id: UUID,
    ) -> None:
        """Report aggregated progress of a specific phase for a batch to BS."""
        ...

    async def publish_batch_phase_concluded(
        self,
        batch_id: str,
        phase: str,
        status: str,
        details: dict[str, Any],
        correlation_id: UUID,
    ) -> None:
        """Report the final conclusion of a phase for a batch to BS."""
        ...

    async def publish_excess_content_provisioned(
        self,
        event_data: Any,  # ExcessContentProvisionedV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Publish ExcessContentProvisionedV1 event when no slots are available."""
        ...

    async def publish_batch_essays_ready(
        self,
        event_data: Any,  # BatchEssaysReady
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Publish BatchEssaysReady event when batch is complete."""
        ...

    async def publish_essay_slot_assigned(
        self,
        event_data: Any,  # EssaySlotAssignedV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Publish EssaySlotAssignedV1 event when content is assigned to a slot."""
        ...

    async def publish_els_batch_phase_outcome(
        self,
        event_data: Any,  # ELSBatchPhaseOutcomeV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Publish ELSBatchPhaseOutcomeV1 event when batch phase is complete."""
        ...


class BatchCommandHandler(Protocol):
    """Protocol for handling batch processing commands from Batch Service."""

    async def process_initiate_spellcheck_command(
        self,
        command_data: Any,  # BatchServiceSpellcheckInitiateCommandDataV1
        correlation_id: UUID,
    ) -> None:
        """Process spellcheck phase initiation command from Batch Service."""
        ...

    async def process_initiate_nlp_command(
        self,
        command_data: Any,  # BatchServiceNLPInitiateCommandDataV1
        correlation_id: UUID,
    ) -> None:
        """Process NLP phase initiation command from Batch Service."""
        ...

    async def process_initiate_ai_feedback_command(
        self,
        command_data: Any,  # BatchServiceAIFeedbackInitiateCommandDataV1
        correlation_id: UUID,
    ) -> None:
        """Process AI feedback phase initiation command from Batch Service."""
        ...

    async def process_initiate_cj_assessment_command(
        self,
        command_data: Any,  # BatchServiceCJAssessmentInitiateCommandDataV1
        correlation_id: UUID,
    ) -> None:
        """Process CJ assessment phase initiation command from Batch Service."""
        ...


class BatchCoordinationHandler(Protocol):
    """Protocol for handling batch coordination events."""

    async def handle_batch_essays_registered(
        self,
        event_data: Any,  # BatchEssaysRegistered
        correlation_id: UUID,
    ) -> bool:
        """Handle batch registration from BOS."""
        ...

    async def handle_essay_content_provisioned(
        self,
        event_data: Any,  # EssayContentProvisionedV1
        correlation_id: UUID,
    ) -> bool:
        """Handle content provisioning and slot assignment."""
        ...

    async def handle_essay_validation_failed(
        self,
        event_data: Any,  # EssayValidationFailedV1
        correlation_id: UUID,
    ) -> bool:
        """Handle validation failure events for coordination."""
        ...


class ServiceResultHandler(Protocol):
    """Protocol for handling specialized service result events."""

    async def handle_spellcheck_result(
        self,
        result_data: Any,  # SpellcheckResultDataV1
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Handle spellcheck result from Spell Checker Service."""
        ...

    async def handle_cj_assessment_completed(
        self,
        result_data: Any,  # CJAssessmentCompletedV1
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Handle CJ assessment completion from CJ Assessment Service."""
        ...

    async def handle_cj_assessment_failed(
        self,
        result_data: Any,  # CJAssessmentFailedV1
        correlation_id: UUID,
    ) -> bool:
        """Handle CJ assessment failure from CJ Assessment Service."""
        ...


class BatchPhaseCoordinator(Protocol):
    """Protocol for coordinating batch-level phase completion and outcome publishing."""

    async def check_batch_completion(
        self,
        essay_state: EssayState,
        phase_name: PhaseName,
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Check if all essays in a batch phase are complete and publish ELSBatchPhaseOutcomeV1 if so.

        This method should be called after individual essay state updates to trigger
        batch-level aggregation and outcome publishing when a phase is complete.

        Args:
            essay_state: The essay state that was just updated
            phase_name: Name of the processing phase (e.g., 'spellcheck', 'cj_assessment')
            correlation_id: Correlation ID for event tracking
        """
        ...


class SpecializedServiceRequestDispatcher(Protocol):
    """Protocol for dispatching individual essay processing requests to Specialized Services."""

    async def dispatch_spellcheck_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: Language,
        batch_id: str,
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Dispatch spellcheck requests to Spellcheck Service."""
        ...

    async def dispatch_nlp_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: Language,
        batch_correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Dispatch NLP requests to NLP Service."""
        ...

    async def dispatch_ai_feedback_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        context: Any,  # AIFeedbackBatchContextDataV1 (to be defined)
        batch_correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Dispatch AI feedback requests to AI Feedback Service."""
        ...

    async def dispatch_cj_assessment_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: Language,
        course_code: CourseCode,
        essay_instructions: str,
        batch_id: str,
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Dispatch CJ assessment requests to CJ Assessment Service."""
        ...


class BatchEssayTracker(Protocol):
    """Protocol for tracking batch readiness and coordination."""

    async def register_batch(
        self, event: Any, correlation_id: UUID
    ) -> None:  # BatchEssaysRegistered
        """Register batch expectations from BOS."""
        ...

    async def assign_slot_to_content(
        self, batch_id: str, text_storage_id: str, original_file_name: str
    ) -> str | None:
        """Assign an available slot to content and return assigned internal essay ID."""
        ...

    async def mark_slot_fulfilled(
        self, batch_id: str, internal_essay_id: str, text_storage_id: str
    ) -> Any | None:  # BatchEssaysReady | None
        """Mark a slot as fulfilled and check if batch is complete."""
        ...

    async def check_batch_completion(
        self, batch_id: str
    ) -> tuple[Any, UUID] | None:  # tuple[BatchEssaysReady, UUID] | None
        """Check if batch is complete and return ready event with correlation ID if so."""
        ...

    async def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        """Get current status of a batch."""
        ...

    async def list_active_batches(self) -> list[str]:
        """Get list of currently tracked batch IDs."""
        ...

    def register_event_callback(
        self, event_type: str, callback: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Register callback for batch coordination events."""
        ...

    async def handle_validation_failure(
        self, event_data: Any
    ) -> Any | None:  # EssayValidationFailedV1 -> BatchEssaysReady | None
        """Handle validation failure event for batch coordination."""
        ...

    async def get_user_id_for_essay(self, essay_id: str) -> str | None:
        """Look up user_id for a given essay by searching through batch expectations."""
        ...

    async def persist_slot_assignment(
        self,
        batch_id: str,
        internal_essay_id: str,
        text_storage_id: str,
        original_file_name: str,
        session: AsyncSession | None = None,
    ) -> None:
        """Persist slot assignment to database."""
        ...

    async def remove_batch_from_database(self, batch_id: str) -> None:
        """Remove completed batch from database."""
        ...

    async def process_pending_content_for_batch(self, batch_id: str) -> int:
        """
        Process any pending content for a newly registered batch.

        Returns:
            Number of pending content items processed
        """
        ...


class MetricsCollector(Protocol):
    """Protocol for collecting service metrics."""

    def record_state_transition(self, from_status: EssayStatus, to_status: EssayStatus) -> None:
        """Record a state transition metric."""
        ...

    def record_processing_time(self, operation: str, duration_ms: float) -> None:
        """Record processing time for an operation."""
        ...

    def increment_counter(self, metric_name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        ...


class KafkaConsumerHealthMonitor(Protocol):
    """Protocol for monitoring Kafka consumer health and self-healing."""

    async def record_message_processed(self) -> None:
        """Record successful message processing."""
        ...

    async def record_processing_failure(self) -> None:
        """Record message processing failure."""
        ...

    def is_healthy(self) -> bool:
        """Check if consumer is healthy based on recent activity and failure rate."""
        ...

    def should_check_health(self) -> bool:
        """Check if it's time to perform a health check."""
        ...

    def get_health_metrics(self) -> dict[str, Any]:
        """Get current health metrics for observability."""
        ...


class ConsumerRecoveryManager(Protocol):
    """Protocol for managing Kafka consumer recovery and self-healing."""

    async def initiate_recovery(self, consumer: Any) -> bool:  # AIOKafkaConsumer
        """
        Initiate graduated recovery process for unhealthy consumer.

        First attempts soft recovery (seek operations), then hard recovery
        (consumer recreation) if soft recovery fails.

        Args:
            consumer: The Kafka consumer to recover

        Returns:
            True if recovery was successful, False otherwise
        """
        ...

    def is_recovery_in_progress(self) -> bool:
        """Check if a recovery operation is currently in progress."""
        ...

    def get_recovery_status(self) -> dict[str, Any]:
        """Get current recovery status and metrics for observability."""
        ...

    async def record_recovery_attempt(self, recovery_type: str, success: bool) -> None:
        """Record recovery attempt for metrics and circuit breaker management."""
        ...
