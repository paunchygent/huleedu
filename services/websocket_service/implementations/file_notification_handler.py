"""
File notification handler for WebSocket Service.

Handles file events from Kafka and publishes notifications to Redis
for real-time WebSocket delivery.
"""

from __future__ import annotations

from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.websocket_service.protocols import FileNotificationHandlerProtocol

logger = create_service_logger("websocket.file_notification_handler")


class FileNotificationHandler(FileNotificationHandlerProtocol):
    """Handler for converting file events to Redis notifications."""

    def __init__(self, redis_client: AtomicRedisClientProtocol) -> None:
        """Initialize the notification handler."""
        self.redis_client = redis_client

    async def handle_batch_file_added(self, event: BatchFileAddedV1) -> None:
        """Handle BatchFileAddedV1 event and publish notification to Redis."""
        try:
            # Convert event to notification format matching File Service's current format
            notification_data = {
                "batch_id": event.batch_id,
                "file_upload_id": event.file_upload_id,
                "filename": event.filename,
                "timestamp": event.timestamp.isoformat(),
            }

            # Publish to Redis using the same format as File Service
            await self.redis_client.publish_user_notification(
                user_id=event.user_id,
                event_type="batch_file_added",
                data=notification_data,
            )

            logger.info(
                f"Published batch_file_added notification for user {event.user_id}",
                extra={
                    "user_id": event.user_id,
                    "batch_id": event.batch_id,
                    "file_upload_id": event.file_upload_id,
                },
            )

        except Exception as e:
            logger.error(
                f"Error publishing batch_file_added notification: {e}",
                exc_info=True,
                extra={
                    "user_id": event.user_id,
                    "batch_id": event.batch_id,
                    "file_upload_id": event.file_upload_id,
                },
            )
            raise

    async def handle_batch_file_removed(self, event: BatchFileRemovedV1) -> None:
        """Handle BatchFileRemovedV1 event and publish notification to Redis."""
        try:
            # Convert event to notification format matching File Service's current format
            notification_data = {
                "batch_id": event.batch_id,
                "file_upload_id": event.file_upload_id,
                "filename": event.filename,
                "timestamp": event.timestamp.isoformat(),
            }

            # Publish to Redis using the same format as File Service
            await self.redis_client.publish_user_notification(
                user_id=event.user_id,
                event_type="batch_file_removed",
                data=notification_data,
            )

            logger.info(
                f"Published batch_file_removed notification for user {event.user_id}",
                extra={
                    "user_id": event.user_id,
                    "batch_id": event.batch_id,
                    "file_upload_id": event.file_upload_id,
                },
            )

        except Exception as e:
            logger.error(
                f"Error publishing batch_file_removed notification: {e}",
                exc_info=True,
                extra={
                    "user_id": event.user_id,
                    "batch_id": event.batch_id,
                    "file_upload_id": event.file_upload_id,
                },
            )
            raise
