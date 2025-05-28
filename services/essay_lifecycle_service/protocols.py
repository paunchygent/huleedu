"""
Protocol interfaces for the Essay Lifecycle Service.

This module defines typing.Protocol interfaces for all ELS dependencies to enable
proper dependency injection and testability.
"""

from __future__ import annotations

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


class EssayStateStore(Protocol):
    """Protocol for essay state persistence operations."""

    async def get_essay_state(self, essay_id: str) -> EssayState | None:
        """Retrieve essay state by ID."""
        ...

    async def update_essay_state(
        self, essay_id: str, new_status: EssayStatus, metadata: dict[str, Any]
    ) -> None:
        """Update essay state with new status and metadata."""
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


class SpecializedServiceRequestDispatcher(Protocol):
    """Protocol for dispatching individual essay processing requests to Specialized Services."""

    async def dispatch_spellcheck_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: str,
        batch_correlation_id: UUID | None = None,
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
