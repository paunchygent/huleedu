"""Teacher notification projector for Essay Lifecycle Service.

Projects internal batch phase outcome events to teacher notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import KafkaPublisherProtocol

logger = create_service_logger("essay_lifecycle_service.notification_projector")


class ELSNotificationProjector:
    """Projects internal batch phase outcome events to teacher notifications."""

    def __init__(
        self,
        kafka_publisher: KafkaPublisherProtocol,
    ) -> None:
        self.kafka_publisher = kafka_publisher

    async def handle_phase_outcome(self, event: ELSBatchPhaseOutcomeV1, teacher_id: str) -> None:
        """Project batch phase outcome to teacher notification.

        Args:
            event: The batch phase outcome event
            teacher_id: Teacher ID resolved from batch context
        """
        # Map phase names to notification types and priorities
        # Note: AI_FEEDBACK phase not yet implemented, so only handling SPELLCHECK and CJ_ASSESSMENT
        notification_mapping = {
            PhaseName.SPELLCHECK: {
                "type": "batch_spellcheck_completed",
                "priority": NotificationPriority.LOW,
                "message_template": "Spellcheck completed for batch",
            },
            PhaseName.CJ_ASSESSMENT: {
                "type": "batch_cj_assessment_completed",
                "priority": NotificationPriority.STANDARD,
                "message_template": "CJ assessment completed for batch",
            },
        }

        # Get notification details for this phase
        notification_details = notification_mapping.get(event.phase_name)
        if not notification_details:
            logger.warning(
                f"Unknown phase name for notification: {event.phase_name}",
                extra={
                    "phase_name": event.phase_name,
                    "batch_id": event.batch_id,
                    "teacher_id": teacher_id,
                },
            )
            return

        # Build status message based on outcome
        success_count = len(event.processed_essays)
        failed_count = len(event.failed_essay_ids)
        total_count = success_count + failed_count

        if event.phase_status == BatchStatus.COMPLETED_SUCCESSFULLY:
            status_detail = f"All {total_count} essays completed successfully"
        elif event.phase_status == BatchStatus.COMPLETED_WITH_FAILURES:
            status_detail = f"{success_count} of {total_count} essays completed successfully"
        else:
            status_detail = f"Processing failed for {failed_count} essays"

        # Create notification payload
        notification = TeacherNotificationRequestedV1(
            teacher_id=teacher_id,
            notification_type=notification_details["type"],
            category=WebSocketEventCategory.BATCH_PROGRESS,
            priority=notification_details["priority"],
            payload={
                "batch_id": event.batch_id,
                "phase_name": event.phase_name.value,
                "phase_status": event.phase_status.value,
                "success_count": success_count,
                "failed_count": failed_count,
                "total_count": total_count,
                "message": f"{notification_details['message_template']}: {status_detail}",
            },
            action_required=False,
            correlation_id=str(event.correlation_id),
            batch_id=event.batch_id,
        )

        await self._publish_notification(notification)

    async def _publish_notification(self, notification: TeacherNotificationRequestedV1) -> None:
        """Publish notification event to Kafka."""
        try:
            # Create event envelope
            envelope: EventEnvelope = EventEnvelope(
                event_id=uuid4(),
                event_type=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
                event_timestamp=notification.timestamp,
                source_service="essay_lifecycle_service",
                correlation_id=uuid4(),  # Could use notification.correlation_id if it's a UUID
                data=notification,
            )

            # Publish to Kafka
            topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
            await self.kafka_publisher.publish(
                topic=topic,
                envelope=envelope,
                key=notification.teacher_id,
            )

            logger.info(
                "Published teacher notification",
                extra={
                    "teacher_id": notification.teacher_id,
                    "notification_type": notification.notification_type,
                    "priority": notification.priority,
                    "phase_name": notification.payload.get("phase_name"),
                    "batch_id": notification.batch_id,
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
                    "phase_name": notification.payload.get("phase_name"),
                    "batch_id": notification.batch_id,
                },
            )
            raise
