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
    raise_outbox_storage_error,
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

        # Try immediate Kafka publishing first
        topic = "essay.status.events"
        key = str(essay_ref.entity_id)
        
        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )
            logger.info(
                "Essay status update published directly to Kafka",
                extra={
                    "essay_id": essay_ref.entity_id,
                    "status": status.value,
                    "correlation_id": str(correlation_id),
                },
            )
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise
            
            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "essay_id": essay_ref.entity_id,
                    "status": status.value,
                    "error": str(kafka_error),
                },
            )
            
            # Kafka failed - use outbox pattern as fallback
            try:
                await self._publish_to_outbox(
                    aggregate_type="essay",
                    aggregate_id=str(essay_ref.entity_id),
                    event_type="essay.status.updated.v1",
                    event_data=envelope,
                    topic=topic,
                )
                # Wake up the relay worker immediately
                await self._notify_relay_worker()
            except Exception as e:
                # Re-raise HuleEduError as-is, or wrap other exceptions
                if hasattr(e, "error_detail"):
                    raise
                else:
                    raise_outbox_storage_error(
                        service="essay_lifecycle_service",
                        operation="publish_status_update",
                        message=f"Failed to publish essay status update: {e.__class__.__name__}",
                        correlation_id=correlation_id,
                        aggregate_id=str(essay_ref.entity_id),
                        aggregate_type="essay",
                        event_type="essay.status.updated.v1",
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

        # Try immediate Kafka publishing first
        topic = "batch.phase.progress.events"
        key = batch_id
        
        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )
            
            logger.info(
                "Batch phase progress published directly to Kafka",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!
            
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise
            
            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = batch_id
        aggregate_type = "batch"

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type="huleedu.els.batch_phase.progress.v1",
                event_data=envelope,
                topic=topic,
            )
            
            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "Batch phase progress stored in outbox and relay worker notified",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_outbox_storage_error(
                    service="essay_lifecycle_service",
                    operation="publish_batch_phase_progress",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type="huleedu.els.batch_phase.progress.v1",
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

        # Try immediate Kafka publishing first
        topic = "batch.phase.concluded.events"
        key = batch_id
        
        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )
            
            logger.info(
                "Batch phase conclusion published directly to Kafka",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "status": status,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!
            
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise
            
            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = batch_id
        aggregate_type = "batch"

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type="huleedu.els.batch_phase.concluded.v1",
                event_data=envelope,
                topic=topic,
            )
            
            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "Batch phase conclusion stored in outbox and relay worker notified",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "status": status,
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_outbox_storage_error(
                    service="essay_lifecycle_service",
                    operation="publish_batch_phase_concluded",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type="huleedu.els.batch_phase.concluded.v1",
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

        # Try immediate Kafka publishing first
        topic = topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED)
        batch_id = getattr(event_data, "batch_id", "unknown")
        key = batch_id
        
        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )
            
            logger.info(
                "Excess content provisioned event published directly to Kafka",
                extra={
                    "batch_id": batch_id,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!
            
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise
            
            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "batch_id": batch_id,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = batch_id
        aggregate_type = "batch"

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type="huleedu.els.excess.content.provisioned.v1",
                event_data=envelope,
                topic=topic,
            )
            
            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "Excess content provisioned event stored in outbox and relay worker notified",
                extra={
                    "batch_id": batch_id,
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_outbox_storage_error(
                    service="essay_lifecycle_service",
                    operation="publish_excess_content_provisioned",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type="huleedu.els.excess.content.provisioned.v1",
                    topic=topic,
                    batch_id=batch_id,
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

        # Try immediate Kafka publishing first
        topic = topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
        batch_id = getattr(event_data, "batch_id", "unknown")
        key = batch_id
        
        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )
            
            logger.info(
                "Batch essays ready event published directly to Kafka",
                extra={
                    "batch_id": batch_id,
                    "ready_count": len(getattr(event_data, "ready_essays", [])),
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!
            
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise
            
            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "batch_id": batch_id,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = batch_id
        aggregate_type = "batch"

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type="huleedu.els.batch.essays.ready.v1",
                event_data=envelope,
                topic=topic,
            )
            
            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "Batch essays ready event stored in outbox and relay worker notified",
                extra={
                    "batch_id": batch_id,
                    "ready_count": len(getattr(event_data, "ready_essays", [])),
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_outbox_storage_error(
                    service="essay_lifecycle_service",
                    operation="publish_batch_essays_ready",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type="huleedu.els.batch.essays.ready.v1",
                    topic=topic,
                    batch_id=batch_id,
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

        # Try immediate Kafka publishing first
        topic = topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED)
        essay_id = getattr(event_data, "essay_id", "unknown")
        key = essay_id
        
        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )
            
            logger.info(
                "EssaySlotAssignedV1 event published directly to Kafka",
                extra={
                    "batch_id": getattr(event_data, "batch_id", "unknown"),
                    "essay_id": essay_id,
                    "file_upload_id": getattr(event_data, "file_upload_id", "unknown"),
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!
            
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise
            
            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "essay_id": essay_id,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = essay_id
        aggregate_type = "essay"

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type="huleedu.els.essay.slot.assigned.v1",
                event_data=envelope,
                topic=topic,
            )
            
            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "EssaySlotAssignedV1 event stored in outbox and relay worker notified",
                extra={
                    "batch_id": getattr(event_data, "batch_id", "unknown"),
                    "essay_id": essay_id,
                    "file_upload_id": getattr(event_data, "file_upload_id", "unknown"),
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_outbox_storage_error(
                    service="essay_lifecycle_service",
                    operation="publish_essay_slot_assigned",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type="huleedu.els.essay.slot.assigned.v1",
                    topic=topic,
                    batch_id=getattr(event_data, "batch_id", "unknown"),
                    essay_id=essay_id,
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

        # Try immediate Kafka publishing first
        topic = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
        batch_id = getattr(event_data, "batch_id", "unknown")
        key = batch_id
        
        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )
            
            logger.info(
                "ELS batch phase outcome event published directly to Kafka",
                extra={
                    "batch_id": batch_id,
                    "phase": getattr(event_data, "phase", "unknown"),
                    "outcome": getattr(event_data, "outcome", "unknown"),
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!
            
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise
            
            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "batch_id": batch_id,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = batch_id
        aggregate_type = "batch"

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type="huleedu.els.batch.phase.outcome.v1",
                event_data=envelope,
                topic=topic,
            )
            
            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "ELS batch phase outcome event stored in outbox and relay worker notified",
                extra={
                    "batch_id": batch_id,
                    "phase": getattr(event_data, "phase", "unknown"),
                    "outcome": getattr(event_data, "outcome", "unknown"),
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_outbox_storage_error(
                    service="essay_lifecycle_service",
                    operation="publish_els_batch_phase_outcome",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type="huleedu.els.batch.phase.outcome.v1",
                    topic=topic,
                    batch_id=batch_id,
                    phase=getattr(event_data, "phase", "unknown"),
                    outcome=getattr(event_data, "outcome", "unknown"),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def _publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,  # EventEnvelope[Any]
        topic: str,
    ) -> None:
        """
        Store event in outbox for reliable delivery (internal method).

        This implements the Transactional Outbox Pattern as a fallback mechanism
        when Kafka is unavailable. Events are stored in the database and
        published asynchronously by the relay worker.

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
                operation="_publish_to_outbox",
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

            logger.debug(
                "Event stored in outbox as fallback",
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
                    operation="_publish_to_outbox",
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

    async def _notify_relay_worker(self) -> None:
        """Notify the relay worker that new events are available in the outbox."""
        try:
            # Use LPUSH to add a notification to the wake-up list
            # The relay worker will use BLPOP to wait for this
            await self.redis_client.lpush("outbox:wake:essay_lifecycle_service", "1")
            logger.debug("Relay worker notified via Redis")
        except Exception as e:
            # Log but don't fail - the relay worker will still poll eventually
            logger.warning(
                "Failed to notify relay worker via Redis",
                extra={"error": str(e)},
            )
