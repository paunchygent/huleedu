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
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol

    from services.essay_lifecycle_service.config import Settings

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
    ) -> None:
        self.kafka_bus = kafka_bus
        self.settings = settings
        self.redis_client = redis_client
        self.batch_tracker = batch_tracker

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

        # Publish to Kafka using KafkaBus.publish()
        topic = "essay.status.events"
        await self.kafka_bus.publish(topic, envelope)

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
            user_id = self.batch_tracker.get_user_id_for_essay(essay_ref.entity_id)

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
            logger.error(
                f"Error publishing essay status to Redis: {e}",
                extra={
                    "essay_id": essay_ref.entity_id,
                    "correlation_id": str(correlation_id),
                },
                exc_info=True,
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

        # Publish to Batch Service topic
        topic = "batch.phase.progress.events"
        await self.kafka_bus.publish(topic, envelope)

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

        # Publish to Batch Service topic
        topic = "batch.phase.concluded.events"
        await self.kafka_bus.publish(topic, envelope)

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

        # Publish to the correct topic
        topic = topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED)
        await self.kafka_bus.publish(topic, envelope)

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

        # Publish to the correct topic
        topic = topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
        await self.kafka_bus.publish(topic, envelope)

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
            event_type="huleedu.els.batch_phase.outcome.v1",
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

        # Publish to the correct topic
        topic = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
        await self.kafka_bus.publish(topic, envelope)
