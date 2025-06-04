"""
Event publisher implementation for Essay Lifecycle Service.

Implements EventPublisher protocol for Kafka event publishing operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from aiokafka import AIOKafkaProducer
    from common_core.enums import EssayStatus
    from common_core.metadata_models import EntityReference

    from config import Settings

from services.essay_lifecycle_service.protocols import EventPublisher


class DefaultEventPublisher(EventPublisher):
    """Default implementation of EventPublisher protocol."""

    def __init__(self, producer: AIOKafkaProducer, settings: Settings) -> None:
        self.producer = producer
        self.settings = settings

    async def publish_status_update(
        self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID | None = None
    ) -> None:
        """Publish essay status update event."""
        import json
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

        # Publish to Kafka
        topic = "essay.status.events"
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)

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
        import json
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

        # Publish to Batch Service topic
        topic = "batch.phase.progress.events"
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)

    async def publish_batch_phase_concluded(
        self,
        batch_id: str,
        phase: str,
        status: str,
        details: dict[str, Any],
        correlation_id: UUID | None = None,
    ) -> None:
        """Report the final conclusion of a phase for a batch to BS."""
        import json
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

        # Publish to Batch Service topic
        topic = "batch.phase.concluded.events"
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)

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
        correlation_id: UUID | None = None,
    ) -> None:
        """Publish ExcessContentProvisionedV1 event when no slots are available."""
        import json
        from uuid import uuid4

        from common_core.enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.excess.content.provisioned.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Publish to the correct topic
        topic = topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED)
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)

    async def publish_batch_essays_ready(
        self,
        event_data: Any,  # BatchEssaysReady
        correlation_id: UUID | None = None,
    ) -> None:
        """Publish BatchEssaysReady event when batch is complete."""
        import json
        from uuid import uuid4

        from common_core.enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch.essays.ready.v1",
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Publish to the correct topic for BatchEssaysReady
        topic = topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)

    async def publish_els_batch_phase_outcome(
        self,
        event_data: Any,  # ELSBatchPhaseOutcomeV1
        correlation_id: UUID | None = None,
    ) -> None:
        """Publish ELSBatchPhaseOutcomeV1 event when batch phase is complete."""
        import json
        from uuid import uuid4

        from common_core.enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type=topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Publish to the correct topic for ELSBatchPhaseOutcomeV1
        topic = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
        message = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        await self.producer.send_and_wait(topic, message)
