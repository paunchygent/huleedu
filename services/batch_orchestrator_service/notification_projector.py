"""Teacher notification projector for Batch Orchestrator Service.

Projects batch orchestration events to teacher notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchPipelineCompletedV1
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.pipeline_models import PhaseName
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from services.batch_orchestrator_service.protocols import (
        BatchEventPublisherProtocol,
        BatchRepositoryProtocol,
    )

logger = create_service_logger("bos.notification_projector")


class NotificationProjector:
    """Projects batch orchestration events to teacher notifications."""

    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
        event_publisher: BatchEventPublisherProtocol,
    ) -> None:
        self.batch_repo = batch_repo
        self.event_publisher = event_publisher

    async def handle_batch_processing_started(
        self,
        batch_id: str,
        requested_pipeline: str,
        resolved_pipeline: list[PhaseName],
        user_id: str,
        correlation_id: UUID,
    ) -> None:
        """Project batch processing start to teacher notification.

        Called ONLY from ClientPipelineRequestHandler when teacher explicitly
        triggers pipeline via "Start Processing" button. Provides immediate
        feedback that their action was received and processing has begun.
        """
        # Convert resolved pipeline to human-readable format
        pipeline_phases = [phase.value for phase in resolved_pipeline]

        # Determine the first phase being initiated
        first_phase = pipeline_phases[0] if pipeline_phases else "unknown"

        # Create notification with immediate feedback
        notification = TeacherNotificationRequestedV1(
            teacher_id=user_id,
            notification_type="batch_processing_started",
            category=WebSocketEventCategory.BATCH_PROGRESS,
            priority=NotificationPriority.LOW,  # Per task spec: LOW priority for progress tracking
            payload={
                "batch_id": batch_id,
                "requested_pipeline": requested_pipeline,
                "resolved_pipeline": pipeline_phases,
                "first_phase": first_phase,
                "total_phases": len(pipeline_phases),
                "message": f"Processing started: Initiating {first_phase} phase",
            },
            action_required=False,
            correlation_id=str(correlation_id),
            batch_id=batch_id,
        )

        await self._publish_notification(notification)

        logger.info(
            "Published batch_processing_started notification",
            extra={
                "batch_id": batch_id,
                "teacher_id": user_id,
                "requested_pipeline": requested_pipeline,
                "resolved_pipeline": pipeline_phases,
                "correlation_id": str(correlation_id),
            },
        )

    async def handle_batch_pipeline_completed(
        self,
        event: BatchPipelineCompletedV1,
    ) -> None:
        """Project pipeline completion to teacher notification."""

        # Get batch to extract teacher_id from processing_metadata
        batch = await self.batch_repo.get_batch_by_id(event.batch_id)
        if not batch:
            logger.warning(
                f"Batch {event.batch_id} not found for pipeline completion notification",
                extra={"batch_id": event.batch_id, "correlation_id": str(event.correlation_id)},
            )
            return

        # Extract user_id from processing_metadata JSON field
        processing_metadata = batch.get("processing_metadata", {})
        user_id = processing_metadata.get("user_id")
        if not user_id:
            logger.warning(
                f"No user_id found in batch {event.batch_id} processing_metadata",
                extra={"batch_id": event.batch_id, "correlation_id": str(event.correlation_id)},
            )
            return

        # Determine priority based on failures
        priority = (
            NotificationPriority.IMMEDIATE
            if event.failed_essay_count > 0
            else NotificationPriority.HIGH
        )
        action_required = event.failed_essay_count > 0

        # Create pipeline completion message
        if event.failed_essay_count > 0:
            message = (
                f"Pipeline completed with {event.failed_essay_count} failures: {event.final_status}"
            )
        else:
            message = f"Pipeline completed successfully: {event.final_status}"

        notification = TeacherNotificationRequestedV1(
            teacher_id=user_id,
            notification_type="pipeline_completed",
            category=WebSocketEventCategory.BATCH_PROGRESS,
            priority=priority,
            payload={
                "batch_id": event.batch_id,
                "final_status": event.final_status,
                "completed_phases": event.completed_phases,
                "successful_essays": event.successful_essay_count,
                "failed_essays": event.failed_essay_count,
                "duration_seconds": event.processing_duration_seconds,
                "message": message,
            },
            action_required=action_required,
            correlation_id=str(event.correlation_id),
            batch_id=event.batch_id,
        )

        await self._publish_notification(notification)

        logger.info(
            "Published pipeline_completed notification",
            extra={
                "batch_id": event.batch_id,
                "teacher_id": user_id,
                "final_status": event.final_status,
                "failed_essays": event.failed_essay_count,
                "correlation_id": str(event.correlation_id),
            },
        )

    async def _publish_notification(self, notification: TeacherNotificationRequestedV1) -> None:
        """Publish notification event to Kafka via outbox pattern."""
        try:
            # Create event envelope
            envelope: EventEnvelope = EventEnvelope(
                event_id=uuid4(),
                event_type=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
                event_timestamp=notification.timestamp,
                source_service="batch_orchestrator_service",
                correlation_id=UUID(notification.correlation_id),
                data=notification,
            )

            # Publish using the batch event publisher (which uses outbox pattern)
            await self.event_publisher.publish_batch_event(envelope)

            logger.debug(
                "Published teacher notification via outbox",
                extra={
                    "teacher_id": notification.teacher_id,
                    "notification_type": notification.notification_type,
                    "priority": notification.priority,
                    "correlation_id": notification.correlation_id,
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to publish teacher notification: {e}",
                exc_info=True,
                extra={
                    "teacher_id": notification.teacher_id,
                    "notification_type": notification.notification_type,
                },
            )
            # Don't raise - notification failure shouldn't stop pipeline processing
