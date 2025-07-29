"""
Event publisher implementation using composition of domain-focused classes.

Provides the same interface as the original DefaultEventPublisher but
with internal composition of specialized domain classes for better
separation of concerns and maintainability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.metadata_models import EntityReference
    from common_core.status_enums import EssayStatus
    from huleedu_service_libs.outbox import OutboxRepositoryProtocol
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.essay_lifecycle_service.config import Settings
    from services.essay_lifecycle_service.protocols import BatchEssayTracker

from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)
from services.essay_lifecycle_service.implementations.batch_progress_publisher import (
    BatchProgressPublisher,
)
from services.essay_lifecycle_service.implementations.essay_status_publisher import (
    EssayStatusPublisher,
)
from services.essay_lifecycle_service.implementations.outbox_manager import OutboxManager

logger = create_service_logger("essay_lifecycle_service.default_event_publisher_v2")


class DefaultEventPublisher:
    """
    Event publisher implementation using composition of domain classes.

    Implements EventPublisher protocol through specialized domain classes:
    - EssayStatusPublisher: Handles individual essay status updates
    - BatchProgressPublisher: Manages batch progress and conclusion events
    - BatchLifecyclePublisher: Handles major batch lifecycle milestones
    - OutboxManager: Provides outbox pattern and relay worker coordination

    This maintains the same interface as the original DefaultEventPublisher
    while providing better internal organization and maintainability.
    """

    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
        batch_tracker: BatchEssayTracker,
        outbox_repository: OutboxRepositoryProtocol,
    ) -> None:
        self.kafka_bus = kafka_bus
        self.settings = settings
        self.redis_client = redis_client
        self.batch_tracker = batch_tracker
        self.outbox_repository = outbox_repository

        # Initialize domain-focused components
        self._outbox_manager = OutboxManager(outbox_repository, redis_client, settings)
        self._essay_status_publisher = EssayStatusPublisher(
            kafka_bus, settings, redis_client, batch_tracker
        )
        self._batch_progress_publisher = BatchProgressPublisher(kafka_bus, settings)
        self._batch_lifecycle_publisher = BatchLifecyclePublisher(
            kafka_bus, settings, self._outbox_manager
        )

    # Essay Status Events (delegate to EssayStatusPublisher)
    async def publish_status_update(
        self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID
    ) -> None:
        """Publish essay status update event to both Kafka and Redis."""
        # TRUE OUTBOX PATTERN: No exception handling needed
        # Events are always stored in outbox for transactional safety
        await self._essay_status_publisher.publish_status_update(
            essay_ref, status, correlation_id
        )

    # Batch Progress Events (delegate to BatchProgressPublisher)
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
        # TRUE OUTBOX PATTERN: No exception handling needed
        # Events are always stored in outbox for transactional safety
        await self._batch_progress_publisher.publish_batch_phase_progress(
            batch_id,
            phase,
            completed_count,
            failed_count,
            total_essays_in_phase,
            correlation_id,
        )

    async def publish_batch_phase_concluded(
        self,
        batch_id: str,
        phase: str,
        status: str,
        details: dict[str, Any],
        correlation_id: UUID,
    ) -> None:
        """Report the final conclusion of a phase for a batch to BS."""
        # TRUE OUTBOX PATTERN: No exception handling needed
        # Events are always stored in outbox for transactional safety
        await self._batch_progress_publisher.publish_batch_phase_concluded(
            batch_id, phase, status, details, correlation_id
        )

    # Batch Lifecycle Events (delegate to BatchLifecyclePublisher)
    async def publish_excess_content_provisioned(
        self,
        event_data: Any,  # ExcessContentProvisionedV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Publish ExcessContentProvisionedV1 event when no slots are available."""
        # TRUE OUTBOX PATTERN: No exception handling needed
        # Events are always stored in outbox for transactional safety
        await self._batch_lifecycle_publisher.publish_excess_content_provisioned(
            event_data, correlation_id, session
        )

    async def publish_batch_essays_ready(
        self,
        event_data: Any,  # BatchEssaysReady
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Publish BatchEssaysReady event when batch is complete."""
        # TRUE OUTBOX PATTERN: No exception handling needed
        # Events are always stored in outbox for transactional safety
        await self._batch_lifecycle_publisher.publish_batch_essays_ready(
            event_data, correlation_id, session
        )

    async def publish_essay_slot_assigned(
        self,
        event_data: Any,  # EssaySlotAssignedV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Publish EssaySlotAssignedV1 event when content is assigned to a slot."""
        # TRUE OUTBOX PATTERN: No exception handling needed
        # Events are always stored in outbox for transactional safety
        await self._batch_lifecycle_publisher.publish_essay_slot_assigned(
            event_data, correlation_id, session
        )

    async def publish_els_batch_phase_outcome(
        self,
        event_data: Any,  # ELSBatchPhaseOutcomeV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Publish ELSBatchPhaseOutcomeV1 event when batch phase is complete."""
        # TRUE OUTBOX PATTERN: No exception handling needed
        # Events are always stored in outbox for transactional safety
        await self._batch_lifecycle_publisher.publish_els_batch_phase_outcome(
            event_data, correlation_id, session
        )

    # Direct Outbox Interface (for protocol compliance)
    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,
        topic: str,
        session: AsyncSession | None = None,
    ) -> None:
        """Direct outbox publishing interface matching EventPublisher protocol."""
        await self._outbox_manager.publish_to_outbox(
            aggregate_type, aggregate_id, event_type, event_data, topic
        )
