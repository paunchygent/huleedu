"""Teacher notification projector for File Service.

Projects internal file management events to teacher notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import KafkaPublisherProtocol

logger = create_service_logger("file_service.notification_projector")


class FileServiceNotificationProjector:
    """Projects internal file management events to teacher notifications."""

    def __init__(
        self,
        kafka_publisher: KafkaPublisherProtocol,
    ) -> None:
        self.kafka_publisher = kafka_publisher

    async def handle_batch_file_added(self, event: BatchFileAddedV1) -> None:
        """Project file addition to teacher notification."""
        # BatchFileAddedV1 has user_id field directly
        notification = TeacherNotificationRequestedV1(
            teacher_id=event.user_id,
            notification_type="batch_files_uploaded",
            category=WebSocketEventCategory.FILE_OPERATIONS,
            priority=NotificationPriority.STANDARD,
            payload={
                "batch_id": event.batch_id,
                "file_upload_id": event.file_upload_id,
                "filename": event.filename,
                "message": f"File '{event.filename}' uploaded successfully",
                "upload_status": "completed",
            },
            action_required=False,
            correlation_id=str(event.correlation_id),
            batch_id=event.batch_id,
        )

        await self._publish_notification(notification)

    async def handle_batch_file_removed(self, event: BatchFileRemovedV1) -> None:
        """Project file removal to teacher notification."""
        # BatchFileRemovedV1 has user_id field directly
        notification = TeacherNotificationRequestedV1(
            teacher_id=event.user_id,
            notification_type="batch_file_removed",
            category=WebSocketEventCategory.FILE_OPERATIONS,
            priority=NotificationPriority.STANDARD,
            payload={
                "batch_id": event.batch_id,
                "file_upload_id": event.file_upload_id,
                "filename": event.filename,
                "message": f"File '{event.filename}' removed from batch",
            },
            action_required=False,
            correlation_id=str(event.correlation_id),
            batch_id=event.batch_id,
        )

        await self._publish_notification(notification)

    async def handle_essay_validation_failed(
        self, event: EssayValidationFailedV1, user_id: str
    ) -> None:
        """Project validation failure to teacher notification.

        Note: EssayValidationFailedV1 doesn't have user_id, so it must be provided
        by the caller (e.g., from the batch context or file upload context).
        """
        notification = TeacherNotificationRequestedV1(
            teacher_id=user_id,
            notification_type="batch_validation_failed",
            category=WebSocketEventCategory.SYSTEM_ALERTS,
            priority=NotificationPriority.IMMEDIATE,
            payload={
                "batch_id": event.entity_id,  # entity_id is batch_id in this context
                "file_upload_id": event.file_upload_id,
                "filename": event.original_file_name,
                "validation_error": event.validation_error_code.value,
                "error_message": event.validation_error_detail.message,
                "message": (
                    f"File '{event.original_file_name}' failed validation: "
                    f"{event.validation_error_detail.message}"
                ),
            },
            action_required=True,
            correlation_id=str(event.correlation_id),
            batch_id=event.entity_id,
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
                source_service="file_service",
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
            raise
