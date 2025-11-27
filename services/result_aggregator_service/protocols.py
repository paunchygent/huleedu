"""Service protocols for Result Aggregator Service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID

from common_core.events import (
    BatchEssaysRegistered,
    ELSBatchPhaseOutcomeV1,
    EventEnvelope,
    SpellcheckResultV1,
)
from common_core.events.batch_coordination_events import BatchPipelineCompletedV1
from common_core.events.cj_assessment_events import AssessmentResultV1
from common_core.events.result_events import BatchAssessmentCompletedV1, BatchResultsReadyV1
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import ProcessingStage

from services.result_aggregator_service.models_db import BatchResult, EssayResult


class BatchRepositoryProtocol(Protocol):
    """Protocol for batch result repository operations."""

    async def get_batch(self, batch_id: str) -> Optional[BatchResult]:
        """Get batch result by ID."""
        ...

    async def create_batch(
        self,
        batch_id: str,
        user_id: str,
        essay_count: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BatchResult:
        """Create a new batch result."""
        ...

    async def update_batch_status(
        self,
        batch_id: str,
        status: str,
        error_detail: Optional[ErrorDetail] = None,
        correlation_id: Optional[UUID] = None,
    ) -> bool:
        """Update batch status."""
        ...

    async def get_user_batches(
        self, user_id: str, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> List[BatchResult]:
        """Get batches for a user."""
        ...

    async def update_essay_spellcheck_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error_detail: Optional[ErrorDetail] = None,
    ) -> None:
        """Update essay spellcheck results."""
        ...

    async def update_essay_spellcheck_result_with_metrics(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        correction_count: Optional[int] = None,
        corrected_text_storage_id: Optional[str] = None,
        error_detail: Optional[ErrorDetail] = None,
        # Enhanced metrics from rich event
        l2_corrections: Optional[int] = None,
        spell_corrections: Optional[int] = None,
        word_count: Optional[int] = None,
        correction_density: Optional[float] = None,
        processing_duration_ms: Optional[int] = None,
    ) -> None:
        """Update essay with detailed spellcheck metrics."""
        ...

    async def update_essay_cj_assessment_result(
        self,
        essay_id: str,
        batch_id: str,
        status: ProcessingStage,
        correlation_id: UUID,
        rank: Optional[int] = None,
        score: Optional[float] = None,
        comparison_count: Optional[int] = None,
        error_detail: Optional[ErrorDetail] = None,
    ) -> None:
        """Update essay CJ assessment results."""
        ...

    async def update_batch_phase_completed(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
    ) -> None:
        """Update batch after phase completion."""
        ...

    async def set_batch_processing_started(self, batch_id: str) -> None:
        """Set the processing_started_at timestamp for a batch."""
        ...

    async def update_batch_failed(
        self, batch_id: str, error_detail: ErrorDetail, correlation_id: UUID
    ) -> None:
        """Mark batch as failed."""
        ...

    async def update_essay_file_mapping(
        self,
        essay_id: str,
        file_upload_id: str,
        text_storage_id: str,
        filename: str,
    ) -> None:
        """Update essay with file_upload_id and filename for traceability."""
        ...

    async def associate_essay_with_batch(
        self,
        essay_id: str,
        batch_id: str,
    ) -> None:
        """Associate an orphaned essay with its batch."""
        ...

    async def get_batch_essays(self, batch_id: str) -> List["EssayResult"]:
        """Get all essays for a batch."""
        ...

    async def mark_batch_completed(
        self,
        batch_id: str,
        final_status: str,
        completion_stats: dict,
    ) -> None:
        """Mark batch as completed with final statistics."""
        ...


class StateStoreProtocol(Protocol):
    """Protocol for state store operations."""

    async def get_batch_state(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get batch processing state from cache."""
        ...

    async def set_batch_state(self, batch_id: str, state: Dict[str, Any], ttl: int = 300) -> bool:
        """Set batch processing state in cache."""
        ...

    async def invalidate_batch(self, batch_id: str) -> bool:
        """Invalidate cached batch state."""
        ...


class EventProcessorProtocol(Protocol):
    """Protocol for processing events from Kafka."""

    async def process_batch_registered(
        self, envelope: EventEnvelope[BatchEssaysRegistered], data: BatchEssaysRegistered
    ) -> None:
        """Process batch registration event."""
        ...

    async def process_essay_slot_assigned(
        self,
        envelope: EventEnvelope[Any],
        data: Any,  # EssaySlotAssignedV1
    ) -> None:
        """Process essay slot assignment event for file traceability."""
        ...

    async def process_batch_phase_outcome(
        self, envelope: EventEnvelope[ELSBatchPhaseOutcomeV1], data: ELSBatchPhaseOutcomeV1
    ) -> None:
        """Process batch phase outcome event."""
        ...

    async def process_spellcheck_result(
        self, envelope: EventEnvelope[SpellcheckResultV1], data: SpellcheckResultV1
    ) -> None:
        """Process rich spellcheck result event with business metrics."""
        ...

    async def process_assessment_result(
        self, envelope: EventEnvelope[AssessmentResultV1], data: AssessmentResultV1
    ) -> None:
        """Process assessment result event with rich business data from CJ Assessment Service."""
        ...

    async def process_pipeline_completed(self, event: BatchPipelineCompletedV1) -> None:
        """Process pipeline completion for final result aggregation."""
        ...


class BatchQueryServiceProtocol(Protocol):
    """Protocol for querying batch results."""

    async def get_batch_status(self, batch_id: str) -> Optional[BatchResult]:
        """Get comprehensive batch status."""
        ...

    async def get_user_batches(
        self, user_id: str, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> List[BatchResult]:
        """Get all batches for a user."""
        ...


class SecurityServiceProtocol(Protocol):
    """Protocol for security operations."""

    async def validate_service_credentials(self, api_key: str, service_id: str) -> bool:
        """Validate service-to-service credentials."""
        ...


class CacheManagerProtocol(Protocol):
    """Protocol for cache management."""

    async def get_batch_status_json(self, batch_id: str) -> Optional[str]:
        """Get cached batch status as JSON string."""
        ...

    async def set_batch_status_json(self, batch_id: str, status_json: str, ttl: int = 300) -> None:
        """Cache batch status as JSON string."""
        ...

    async def get_user_batches_json(
        self, user_id: str, limit: int, offset: int, status: Optional[str]
    ) -> Optional[str]:
        """Get cached user batches list as JSON string."""
        ...

    async def set_user_batches_json(
        self, user_id: str, limit: int, offset: int, status: Optional[str], data_json: str, ttl: int
    ) -> None:
        """Cache user batches list as JSON string."""
        ...

    async def invalidate_batch(self, batch_id: str) -> None:
        """Invalidate cached batch data."""
        ...

    async def invalidate_user_batches(self, user_id: str) -> None:
        """Invalidate all cached user batch lists."""
        ...


class BatchOrchestratorClientProtocol(Protocol):
    """Protocol for communicating with Batch Orchestrator Service."""

    async def get_pipeline_state(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get pipeline state from BOS for batch consistency fallback."""
        ...


class OutboxManagerProtocol(Protocol):
    """Protocol for managing transactional outbox pattern."""

    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,  # EventEnvelope[Any]
        topic: str,
    ) -> None:
        """
        Store event in outbox for reliable delivery.

        Args:
            aggregate_type: Type of aggregate (e.g., "batch", "essay")
            aggregate_id: ID of the aggregate that produced the event
            event_type: Type of event being published
            event_data: Complete event envelope to publish
            topic: Kafka topic to publish to
        """
        ...


class EventPublisherProtocol(Protocol):
    """Protocol for publishing domain events from Result Aggregator Service."""

    async def publish_batch_results_ready(
        self,
        event_data: BatchResultsReadyV1,
        correlation_id: UUID,
    ) -> None:
        """
        Publish BatchResultsReadyV1 event when all phases complete.

        Args:
            event_data: The batch results ready event data
            correlation_id: Correlation ID for event tracking
        """
        ...

    async def publish_batch_assessment_completed(
        self,
        event_data: BatchAssessmentCompletedV1,
        correlation_id: UUID,
    ) -> None:
        """
        Publish BatchAssessmentCompletedV1 event when CJ assessment completes.

        Args:
            event_data: The batch assessment completed event data
            correlation_id: Correlation ID for event tracking
        """
        ...
