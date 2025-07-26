"""
Event publisher implementation for Essay Lifecycle Service.

Implements EventPublisher protocol for Kafka event publishing operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from common_core.metadata_models import EntityReference
    from common_core.status_enums import EssayStatus
    from huleedu_service_libs.outbox import OutboxRepositoryProtocol
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol

    from services.essay_lifecycle_service.config import Settings

from huleedu_service_libs.error_handling import (
    raise_external_service_error,
    raise_kafka_publish_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.essay_lifecycle_service.protocols import BatchEssayTracker, EventPublisher

logger = create_service_logger("essay_lifecycle_service.event_publisher")


class DefaultEventPublisher(EventPublisher):
    """Default implementation of EventPublisher protocol."""

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

    async def publish_status_update(
        self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID
    ) -> None:
        """Publish essay status update event to both Kafka and Redis."""
        from datetime import UTC, datetime
        from uuid import uuid4

        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import SystemProcessingMetadata

        # Create status update event data as a dict that's JSON serializable
        event_data = {
            "event_name": "essay.status.updated.v1",
            "entity_ref": essay_ref.model_dump(),
            "status": status.value,
            "system_metadata": SystemProcessingMetadata(
                entity=essay_ref,
                timestamp=datetime.now(UTC),
            ).model_dump(),
        }

        # Create event envelope (using Any type for now)
        envelope = EventEnvelope[Any](
            event_type="essay.status.updated.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # Publish to outbox for reliable delivery
        try:
            topic = "essay.status.events"
            await self.publish_to_outbox(
                aggregate_type="essay",
                aggregate_id=str(essay_ref.entity_id),
                event_type="essay.status.updated.v1",
                event_data=envelope,
                topic=topic,
            )
        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="essay_lifecycle_service",
                    operation="publish_status_update",
                    message=f"Failed to publish essay status update to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    topic=topic,
                    essay_id=essay_ref.entity_id,
                    status=status.value,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

        # Publish to Redis for real-time updates
        await self._publish_essay_status_to_redis(essay_ref, status, correlation_id)

    async def _publish_essay_status_to_redis(
        self,
        essay_ref: EntityReference,
        status: EssayStatus,
        correlation_id: UUID,
    ) -> None:
        """Publish essay status update to Redis for real-time UI notifications."""
        try:
            from datetime import UTC, datetime

            # Look up the user_id for this essay from batch context
            user_id = await self.batch_tracker.get_user_id_for_essay(essay_ref.entity_id)

            if user_id:
                # Publish real-time notification to user-specific Redis channel
                await self.redis_client.publish_user_notification(
                    user_id=user_id,
                    event_type="essay_status_updated",
                    data={
                        "essay_id": essay_ref.entity_id,
                        "status": status.value,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "correlation_id": str(correlation_id),
                    },
                )

                logger.info(
                    f"Published real-time essay status notification to Redis for user {user_id}",
                    extra={
                        "essay_id": essay_ref.entity_id,
                        "user_id": user_id,
                        "status": status.value,
                        "correlation_id": str(correlation_id),
                    },
                )
            else:
                logger.warning(
                    "Cannot publish Redis notification: user_id not found for essay",
                    extra={
                        "essay_id": essay_ref.entity_id,
                        "status": status.value,
                        "correlation_id": str(correlation_id),
                    },
                )

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="_publish_essay_status_to_redis",
                    external_service="Redis",
                    message=f"Failed to publish essay status to Redis: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    essay_id=essay_ref.entity_id,
                    user_id=user_id if "user_id" in locals() else None,
                    status=status.value,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

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
        from datetime import UTC, datetime
        from uuid import uuid4

        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import EntityReference

        # Create batch progress event data
        batch_ref = EntityReference(entity_id=batch_id, entity_type="batch")

        event_data = {
            "event_name": "batch.phase.progress.v1",
            "entity_ref": batch_ref.model_dump(),
            "phase": phase,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "total_essays_in_phase": total_essays_in_phase,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch_phase.progress.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # Publish to outbox for reliable delivery
        try:
            topic = "batch.phase.progress.events"
            await self.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id=batch_id,
                event_type="huleedu.els.batch_phase.progress.v1",
                event_data=envelope,
                topic=topic,
            )
        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="essay_lifecycle_service",
                    operation="publish_batch_phase_progress",
                    message=f"Failed to publish batch phase progress to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    topic=topic,
                    batch_id=batch_id,
                    phase=phase,
                    completed_count=completed_count,
                    failed_count=failed_count,
                    total_essays_in_phase=total_essays_in_phase,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
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
        from datetime import UTC, datetime
        from uuid import uuid4

        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import EntityReference

        # Create batch conclusion event data
        batch_ref = EntityReference(entity_id=batch_id, entity_type="batch")

        event_data = {
            "event_name": "batch.phase.concluded.v1",
            "entity_ref": batch_ref.model_dump(),
            "phase": phase,
            "status": status,
            "details": details,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch_phase.concluded.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # Publish to outbox for reliable delivery
        try:
            topic = "batch.phase.concluded.events"
            await self.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id=batch_id,
                event_type="huleedu.els.batch_phase.concluded.v1",
                event_data=envelope,
                topic=topic,
            )
        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="essay_lifecycle_service",
                    operation="publish_batch_phase_concluded",
                    message=f"Failed to publish batch phase conclusion to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    topic=topic,
                    batch_id=batch_id,
                    phase=phase,
                    status=status,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    def _get_topic_for_event_type(self, event_type: str) -> str:
        """Map event type to appropriate Kafka topic."""
        if "spellcheck" in event_type:
            return "essay.spellcheck.requests"
        elif "nlp" in event_type:
            return "essay.nlp.requests"
        elif "ai_feedback" in event_type:
            return "essay.ai_feedback.requests"
        else:
            return "essay.processing.requests"

    async def publish_excess_content_provisioned(
        self,
        event_data: Any,  # ExcessContentProvisionedV1
        correlation_id: UUID,
    ) -> None:
        """Publish ExcessContentProvisionedV1 event when no slots are available."""
        from uuid import uuid4

        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.excess.content.provisioned.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # Publish to outbox for reliable delivery
        try:
            topic = topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED)
            await self.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id=getattr(event_data, "batch_id", "unknown"),
                event_type="huleedu.els.excess.content.provisioned.v1",
                event_data=envelope,
                topic=topic,
            )
        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="essay_lifecycle_service",
                    operation="publish_excess_content_provisioned",
                    message=f"Failed to publish excess content provisioned event to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    topic=topic,
                    batch_id=getattr(event_data, "batch_id", "unknown"),
                    text_storage_id=getattr(event_data, "text_storage_id", "unknown"),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def publish_batch_essays_ready(
        self,
        event_data: Any,  # BatchEssaysReady
        correlation_id: UUID,
    ) -> None:
        """Publish BatchEssaysReady event when batch is complete."""
        from uuid import uuid4

        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch.essays.ready.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # Publish to outbox for reliable delivery
        try:
            topic = topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
            await self.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id=getattr(event_data, "batch_id", "unknown"),
                event_type="huleedu.els.batch.essays.ready.v1",
                event_data=envelope,
                topic=topic,
            )
        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="essay_lifecycle_service",
                    operation="publish_batch_essays_ready",
                    message=f"Failed to publish batch essays ready event to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    topic=topic,
                    batch_id=getattr(event_data, "batch_id", "unknown"),
                    ready_count=len(getattr(event_data, "ready_essays", [])),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def publish_essay_slot_assigned(
        self,
        event_data: Any,  # EssaySlotAssignedV1
        correlation_id: UUID,
    ) -> None:
        """Publish EssaySlotAssignedV1 event when content is assigned to a slot."""
        from uuid import uuid4

        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.essay.slot.assigned.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
            metadata={},
        )

        # Inject current trace context
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # Publish to outbox for reliable delivery
        topic = topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED)
        try:
            await self.publish_to_outbox(
                aggregate_type="essay",
                aggregate_id=getattr(event_data, "essay_id", "unknown"),
                event_type="huleedu.els.essay.slot.assigned.v1",
                event_data=envelope,
                topic=topic,
            )
            logger.info(
                "Published EssaySlotAssignedV1 event to outbox",
                extra={
                    "batch_id": getattr(event_data, "batch_id", "unknown"),
                    "essay_id": getattr(event_data, "essay_id", "unknown"),
                    "file_upload_id": getattr(event_data, "file_upload_id", "unknown"),
                    "correlation_id": str(correlation_id),
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to publish EssaySlotAssignedV1 event: {e}",
                extra={"correlation_id": str(correlation_id)},
                exc_info=True,
            )
            # Use structured error handling if available
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="essay_lifecycle_service",
                    operation="publish_essay_slot_assigned",
                    message=f"Failed to publish essay slot assigned event to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    topic=topic,
                    batch_id=getattr(event_data, "batch_id", "unknown"),
                    essay_id=getattr(event_data, "essay_id", "unknown"),
                    file_upload_id=getattr(event_data, "file_upload_id", "unknown"),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def publish_els_batch_phase_outcome(
        self,
        event_data: Any,  # ELSBatchPhaseOutcomeV1
        correlation_id: UUID,
    ) -> None:
        """Publish ELSBatchPhaseOutcomeV1 event when phase is complete."""
        from uuid import uuid4

        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch.phase.outcome.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # Publish to outbox for reliable delivery
        try:
            topic = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
            await self.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id=getattr(event_data, "batch_id", "unknown"),
                event_type="huleedu.els.batch.phase.outcome.v1",
                event_data=envelope,
                topic=topic,
            )
        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="essay_lifecycle_service",
                    operation="publish_els_batch_phase_outcome",
                    message=f"Failed to publish ELS batch phase outcome event to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    topic=topic,
                    batch_id=getattr(event_data, "batch_id", "unknown"),
                    phase=getattr(event_data, "phase", "unknown"),
                    outcome=getattr(event_data, "outcome", "unknown"),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

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

        This implements the Transactional Outbox Pattern, decoupling business
        operations from Kafka availability. Events are stored in the database
        and published asynchronously by the relay worker.

        Args:
            aggregate_type: Type of aggregate (e.g., "essay", "batch")
            aggregate_id: ID of the aggregate that produced the event
            event_type: Type of event being published
            event_data: Complete event envelope to publish
            topic: Kafka topic to publish to

        Raises:
            HuleEduError: If outbox repository is not configured
            DatabaseError: If storing to outbox fails
        """
        if not self.outbox_repository:
            raise_external_service_error(
                service="essay_lifecycle_service",
                operation="publish_to_outbox",
                external_service="outbox_repository",
                message="Outbox repository not configured for transactional publishing",
                correlation_id=event_data.correlation_id
                if hasattr(event_data, "correlation_id")
                else UUID("00000000-0000-0000-0000-000000000000"),
                aggregate_id=aggregate_id,
                event_type=event_type,
            )

        try:
            # Serialize the envelope to JSON for storage
            # Using model_dump(mode="json") to handle UUID and datetime serialization
            serialized_data = event_data.model_dump(mode="json")

            # Add topic to the event data for relay worker
            serialized_data["topic"] = topic

            # Determine Kafka key from envelope metadata or aggregate ID
            event_key = None
            if hasattr(event_data, "metadata") and event_data.metadata:
                event_key = event_data.metadata.get("partition_key", aggregate_id)
            else:
                event_key = aggregate_id

            # Store in outbox
            outbox_id = await self.outbox_repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                event_data=serialized_data,
                topic=topic,
                event_key=event_key,
            )

            logger.info(
                "Event stored in outbox for reliable delivery",
                extra={
                    "outbox_id": str(outbox_id),
                    "event_type": event_type,
                    "aggregate_id": aggregate_id,
                    "aggregate_type": aggregate_type,
                    "topic": topic,
                    "correlation_id": str(event_data.correlation_id)
                    if hasattr(event_data, "correlation_id")
                    else None,
                },
            )

        except Exception as e:
            # Re-raise HuleEduError as-is, wrap others
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="publish_to_outbox",
                    external_service="outbox_repository",
                    message=f"Failed to store event in outbox: {e.__class__.__name__}",
                    correlation_id=event_data.correlation_id
                    if hasattr(event_data, "correlation_id")
                    else UUID("00000000-0000-0000-0000-000000000000"),
                    aggregate_id=aggregate_id,
                    event_type=event_type,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )
