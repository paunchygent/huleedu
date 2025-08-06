"""Teacher notification projector for Class Management Service.

Projects internal class management events to teacher notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.class_events import ClassCreatedV1, StudentCreatedV1
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.events.validation_events import (
    StudentAssociationsConfirmedV1,
    ValidationTimeoutProcessedV1,
)
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from services.class_management_service.protocols import (
        ClassEventPublisherProtocol,
        ClassRepositoryProtocol,
    )

logger = create_service_logger("class_management.notification_projector")


class NotificationProjector:
    """Projects internal class management events to teacher notifications."""

    def __init__(
        self,
        class_repository: ClassRepositoryProtocol,
        event_publisher: ClassEventPublisherProtocol,
    ) -> None:
        self.class_repository = class_repository
        self.event_publisher = event_publisher

    async def handle_class_created(self, event: ClassCreatedV1) -> None:
        """Project class creation to teacher notification."""
        # ClassCreatedV1 already has user_id (teacher_id)
        notification = TeacherNotificationRequestedV1(
            teacher_id=event.user_id,
            notification_type="class_created",
            category=WebSocketEventCategory.CLASS_MANAGEMENT,
            priority=NotificationPriority.STANDARD,
            payload={
                "class_id": event.class_id,
                "class_designation": event.class_designation,
                "course_codes": [code.value for code in event.course_codes],
                "message": f"Class '{event.class_designation}' created successfully",
            },
            action_required=False,
            correlation_id=str(event.event_id) if hasattr(event, "event_id") else event.class_id,
            class_id=event.class_id,
        )

        await self._publish_notification(notification)

    async def handle_student_created(self, event: StudentCreatedV1) -> None:
        """Project student creation to teacher notification."""
        # StudentCreatedV1 has class_ids list, use the first one
        if not event.class_ids:
            logger.warning(f"No class IDs for student creation: {event.student_id}")
            return

        # Use the first class_id from the list
        from uuid import UUID

        class_id = UUID(event.class_ids[0])

        # Need to fetch class to get teacher_id
        class_entity = await self.class_repository.get_class_by_id(class_id)
        if not class_entity:
            logger.warning(f"No class found for student creation: {event.student_id}")
            return

        notification = TeacherNotificationRequestedV1(
            teacher_id=class_entity.user_id,
            notification_type="student_added_to_class",
            category=WebSocketEventCategory.CLASS_MANAGEMENT,
            priority=NotificationPriority.LOW,
            payload={
                "student_id": event.student_id,
                "student_name": f"{event.first_name} {event.last_name}",
                "class_id": str(class_id),
                "class_designation": class_entity.class_designation,
                "message": (
                    f"Student '{event.first_name} {event.last_name}' "
                    f"added to class '{class_entity.class_designation}'"
                ),
            },
            action_required=False,
            correlation_id=str(event.event_id) if hasattr(event, "event_id") else event.student_id,
            class_id=str(class_id),
        )

        await self._publish_notification(notification)

    async def handle_validation_timeout_processed(
        self, event: ValidationTimeoutProcessedV1
    ) -> None:
        """Project validation timeout to teacher notification."""
        auto_confirmed_count = len(event.auto_confirmed_associations)

        notification = TeacherNotificationRequestedV1(
            teacher_id=event.user_id,
            notification_type="validation_timeout_processed",
            category=WebSocketEventCategory.STUDENT_WORKFLOW,
            priority=NotificationPriority.IMMEDIATE,
            payload={
                "batch_id": event.batch_id,
                "auto_confirmed_count": auto_confirmed_count,
                "timeout_hours": event.timeout_hours,
                "message": (
                    f"Validation timeout: {auto_confirmed_count} student matches "
                    f"auto-confirmed after {event.timeout_hours} hours"
                ),
                "auto_confirmed_associations": [
                    {
                        "essay_id": assoc.essay_id,
                        "student_name": f"{assoc.student_first_name} {assoc.student_last_name}",
                        "confidence_score": assoc.confidence_score,
                        "is_confirmed": assoc.is_confirmed,
                    }
                    for assoc in event.auto_confirmed_associations
                ],
            },
            action_required=False,  # Already auto-confirmed
            correlation_id=str(event.event_id) if hasattr(event, "event_id") else event.batch_id,
            batch_id=event.batch_id,
        )

        await self._publish_notification(notification)

    async def handle_student_associations_confirmed(
        self, event: StudentAssociationsConfirmedV1
    ) -> None:
        """Project manual student confirmations to teacher notification.

        Note: This event doesn't have user_id, so we need to fetch it from the class.
        """
        confirmed_count = len(event.associations)

        # Get teacher_id from class
        from uuid import UUID

        class_entity = await self.class_repository.get_class_by_id(UUID(event.class_id))
        if not class_entity:
            logger.warning(f"No class found for associations confirmation: {event.class_id}")
            return

        notification = TeacherNotificationRequestedV1(
            teacher_id=class_entity.user_id,
            notification_type="student_associations_confirmed",
            category=WebSocketEventCategory.STUDENT_WORKFLOW,
            priority=NotificationPriority.HIGH,
            payload={
                "batch_id": event.batch_id,
                "confirmed_count": confirmed_count,
                "message": f"Successfully confirmed {confirmed_count} student associations",
                "associations": [
                    {
                        "essay_id": assoc.essay_id,
                        "student_id": assoc.student_id,
                        "validation_method": assoc.validation_method.value,
                        "confidence_score": assoc.confidence_score,
                    }
                    for assoc in event.associations
                ],
                "validation_summary": event.validation_summary,
                "timeout_triggered": event.timeout_triggered,
            },
            action_required=False,
            correlation_id=str(event.event_id) if hasattr(event, "event_id") else event.batch_id,
            batch_id=event.batch_id,
            class_id=event.class_id,
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
                source_service="class_management_service",
                correlation_id=uuid4(),  # Could use notification.correlation_id if it's a UUID
                data=notification,
            )

            await self.event_publisher.publish_class_event(envelope)

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
