"""
Teacher notification handler for WebSocket Service.

Handles TeacherNotificationRequestedV1 events and publishes them to Redis
for real-time WebSocket delivery. This is a pure forwarder with NO business logic.
"""

from __future__ import annotations

from common_core.events.notification_events import TeacherNotificationRequestedV1
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.websocket_service.protocols import NotificationHandlerProtocol

logger = create_service_logger("websocket.notification_handler")


class NotificationHandler(NotificationHandlerProtocol):
    """Handler for forwarding teacher notifications to Redis."""

    def __init__(self, redis_client: AtomicRedisClientProtocol) -> None:
        """Initialize the notification handler."""
        self.redis_client = redis_client

    async def handle_teacher_notification(self, event: TeacherNotificationRequestedV1) -> None:
        """
        Handle TeacherNotificationRequestedV1 event and publish to Redis.

        This is a pure forwarding function - NO business logic, NO authorization.
        The emitting service has already verified the teacher owns the resources.
        """
        try:
            # Build notification payload for WebSocket delivery
            notification_data = {
                **event.payload,  # Include all service-provided data
                "category": event.category.value,
                "priority": event.priority.value,
                "action_required": event.action_required,
                "deadline": event.deadline_timestamp.isoformat()
                if event.deadline_timestamp
                else None,
                "batch_id": event.batch_id,
                "class_id": event.class_id,
                "correlation_id": event.correlation_id,
                "timestamp": event.timestamp.isoformat(),
            }

            # Publish to Redis for WebSocket delivery
            # Note: We trust the teacher_id from the event (services are trusted)
            await self.redis_client.publish_user_notification(
                user_id=event.teacher_id,
                event_type=event.notification_type,
                data=notification_data,
            )

            logger.info(
                "Published teacher notification to Redis",
                extra={
                    "teacher_id": event.teacher_id,
                    "notification_type": event.notification_type,
                    "category": event.category.value,
                    "priority": event.priority.value,
                    "action_required": event.action_required,
                    "batch_id": event.batch_id,
                    "class_id": event.class_id,
                    "correlation_id": event.correlation_id,
                },
            )

        except Exception as e:
            logger.error(
                f"Error publishing teacher notification to Redis: {e}",
                exc_info=True,
                extra={
                    "teacher_id": event.teacher_id,
                    "notification_type": event.notification_type,
                    "correlation_id": event.correlation_id,
                },
            )
            raise
