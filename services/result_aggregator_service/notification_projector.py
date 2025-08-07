"""Teacher notification projector for Result Aggregator Service.

Projects internal result aggregation events to teacher notifications.
Follows the CANONICAL NOTIFICATION PATTERN - direct invocation after domain event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from common_core.events.result_events import BatchAssessmentCompletedV1, BatchResultsReadyV1

    from services.result_aggregator_service.config import Settings
    from services.result_aggregator_service.protocols import OutboxManagerProtocol

logger = create_service_logger("result_aggregator_service.notification_projector")


class ResultNotificationProjector:
    """Projects internal result aggregation events to teacher notifications.

    Follows the CANONICAL NOTIFICATION PATTERN - direct invocation after domain event.
    Uses TRUE OUTBOX PATTERN - stores notifications in outbox for reliable delivery.
    """

    def __init__(
        self,
        outbox_manager: OutboxManagerProtocol,
        settings: Settings,
    ) -> None:
        self.outbox_manager = outbox_manager
        self.settings = settings

    async def handle_batch_results_ready(self, event: BatchResultsReadyV1, correlation_id: UUID) -> None:
        """Project batch completion to high-priority teacher notification.

        Creates TeacherNotificationRequestedV1 and stores in outbox for reliable delivery.
        Priority: HIGH (batch completion is important to teachers).
        """
        # Create teacher notification with high priority
        notification = TeacherNotificationRequestedV1(
            teacher_id=event.user_id,
            notification_type="batch_results_ready",
            category=WebSocketEventCategory.PROCESSING_RESULTS,
            priority=NotificationPriority.HIGH,  # Batch completion is high priority
            payload={
                "batch_id": event.batch_id,
                "total_essays": event.total_essays,
                "completed_essays": event.completed_essays,
                "overall_status": event.overall_status.value,
                "processing_duration_seconds": event.processing_duration_seconds,
                "phase_results": {
                    phase_name: {
                        "status": summary.status,
                        "completed_count": summary.completed_count,
                        "failed_count": summary.failed_count,
                        "processing_time_seconds": summary.processing_time_seconds,
                    }
                    for phase_name, summary in event.phase_results.items()
                },
                "message": f"Batch {event.batch_id} processing completed with {event.completed_essays}/{event.total_essays} essays",
            },
            action_required=False,
            correlation_id=str(correlation_id),
            batch_id=event.batch_id,
        )

        await self._publish_notification(notification)

        logger.info(
            "Published batch_results_ready notification",
            extra={
                "batch_id": event.batch_id,
                "teacher_id": event.user_id,
                "total_essays": event.total_essays,
                "completed_essays": event.completed_essays,
                "correlation_id": str(correlation_id),
            },
        )

    async def handle_batch_assessment_completed(self, event: BatchAssessmentCompletedV1, correlation_id: UUID) -> None:
        """Project CJ assessment completion to teacher notification.

        Creates TeacherNotificationRequestedV1 and stores in outbox for reliable delivery.
        Priority: STANDARD (assessment is valuable but not as urgent as batch completion).
        """
        # Create teacher notification with standard priority
        notification = TeacherNotificationRequestedV1(
            teacher_id=event.user_id,
            notification_type="batch_assessment_completed",
            category=WebSocketEventCategory.PROCESSING_RESULTS,
            priority=NotificationPriority.STANDARD,  # Assessment completion is standard priority
            payload={
                "batch_id": event.batch_id,
                "assessment_job_id": event.assessment_job_id,
                "rankings_available": len(event.rankings_summary) > 0,
                "rankings_count": len(event.rankings_summary),
                "message": f"Comparative judgment assessment completed for batch {event.batch_id}",
            },
            action_required=False,
            correlation_id=str(correlation_id),
            batch_id=event.batch_id,
        )

        await self._publish_notification(notification)

        logger.info(
            "Published batch_assessment_completed notification",
            extra={
                "batch_id": event.batch_id,
                "teacher_id": event.user_id,
                "assessment_job_id": event.assessment_job_id,
                "rankings_count": len(event.rankings_summary),
                "correlation_id": str(correlation_id),
            },
        )

    async def _publish_notification(self, notification: TeacherNotificationRequestedV1) -> None:
        """Publish notification event using TRUE OUTBOX PATTERN.

        Stores notification in outbox for reliable delivery via relay worker.
        NO direct Kafka publishing - maintains transactional safety.
        """
        try:
            # Create event envelope
            envelope = EventEnvelope[TeacherNotificationRequestedV1](
                event_type=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
                source_service=self.settings.SERVICE_NAME,
                correlation_id=uuid4(),
                data=notification,
            )

            # TRUE OUTBOX PATTERN: Store in outbox for reliable delivery
            topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
            await self.outbox_manager.publish_to_outbox(
                aggregate_type="teacher_notification",
                aggregate_id=notification.teacher_id,
                event_type=topic,
                event_data=envelope,
                topic=topic,
            )

            logger.debug(
                "Teacher notification stored in outbox",
                extra={
                    "teacher_id": notification.teacher_id,
                    "notification_type": notification.notification_type,
                    "priority": notification.priority,
                    "correlation_id": notification.correlation_id,
                    "topic": topic,
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to store teacher notification in outbox: {e}",
                exc_info=True,
                extra={
                    "teacher_id": notification.teacher_id,
                    "notification_type": notification.notification_type,
                },
            )
            raise
