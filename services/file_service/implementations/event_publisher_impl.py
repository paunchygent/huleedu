"""Event publisher implementation for File Service."""

from __future__ import annotations

import uuid

from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.file_service.config import Settings
from services.file_service.implementations.outbox_manager import OutboxManager
from services.file_service.protocols import EventPublisherProtocol

logger = create_service_logger("file_service.implementations.event_publisher")


class DefaultEventPublisher(EventPublisherProtocol):
    """Default implementation of EventPublisherProtocol using TRUE OUTBOX PATTERN."""

    def __init__(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
    ):
        self.outbox_manager = outbox_manager
        self.settings = settings
        self.redis_client = redis_client

    async def publish_essay_content_provisioned(
        self,
        event_data: EssayContentProvisionedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish EssayContentProvisionedV1 event using TRUE OUTBOX PATTERN."""
        # Construct EventEnvelope
        from huleedu_service_libs.observability import inject_trace_context

        envelope = EventEnvelope[EssayContentProvisionedV1](
            event_type=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject current trace context into the envelope metadata
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC
        aggregate_id = event_data.file_upload_id

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="file_upload",
            aggregate_id=aggregate_id,
            event_type=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
            event_data=envelope,
            topic=topic,
        )

        logger.info(
            "EssayContentProvisionedV1 event stored in outbox for reliable delivery",
            extra={
                "file_upload_id": event_data.file_upload_id,
                "original_file_name": event_data.original_file_name,
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

    async def publish_essay_validation_failed(
        self,
        event_data: EssayValidationFailedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish EssayValidationFailedV1 event using TRUE OUTBOX PATTERN."""
        # Construct EventEnvelope
        from huleedu_service_libs.observability import inject_trace_context

        envelope = EventEnvelope[EssayValidationFailedV1](
            event_type=self.settings.ESSAY_VALIDATION_FAILED_TOPIC,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject current trace context into the envelope metadata
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = self.settings.ESSAY_VALIDATION_FAILED_TOPIC
        aggregate_id = event_data.file_upload_id

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="file_upload",
            aggregate_id=aggregate_id,
            event_type=self.settings.ESSAY_VALIDATION_FAILED_TOPIC,
            event_data=envelope,
            topic=topic,
        )

        logger.info(
            "EssayValidationFailedV1 event stored in outbox for reliable delivery",
            extra={
                "file_upload_id": event_data.file_upload_id,
                "original_file_name": event_data.original_file_name,
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

    async def publish_batch_file_added_v1(
        self,
        event_data: BatchFileAddedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish BatchFileAddedV1 event using TRUE OUTBOX PATTERN and Redis UI notifications."""
        # Construct EventEnvelope
        from huleedu_service_libs.observability import inject_trace_context

        envelope = EventEnvelope[BatchFileAddedV1](
            event_type=self.settings.BATCH_FILE_ADDED_TOPIC,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject current trace context into the envelope metadata
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = self.settings.BATCH_FILE_ADDED_TOPIC
        aggregate_id = event_data.batch_id

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=aggregate_id,
            event_type=self.settings.BATCH_FILE_ADDED_TOPIC,
            event_data=envelope,
            topic=topic,
        )

        logger.info(
            "BatchFileAddedV1 event stored in outbox for reliable delivery",
            extra={
                "batch_id": event_data.batch_id,
                "file_upload_id": event_data.file_upload_id,
                "filename": event_data.filename,
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

        # Redis publication for real-time UI updates (separate from event bus)
        try:
            # Publish to Redis for real-time updates (maintained as-is)
            await self._publish_file_event_to_redis(
                event_data.user_id,
                "batch_file_added",
                {
                    "batch_id": event_data.batch_id,
                    "file_upload_id": event_data.file_upload_id,
                    "filename": event_data.filename,
                    "timestamp": event_data.timestamp.isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error publishing BatchFileAddedV1 Redis notification: {e}")
            raise

    async def publish_batch_file_removed_v1(
        self,
        event_data: BatchFileRemovedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish BatchFileRemovedV1 event using TRUE OUTBOX PATTERN and Redis UI notifications."""
        # Construct EventEnvelope
        from huleedu_service_libs.observability import inject_trace_context

        envelope = EventEnvelope[BatchFileRemovedV1](
            event_type=self.settings.BATCH_FILE_REMOVED_TOPIC,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject current trace context into the envelope metadata
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = self.settings.BATCH_FILE_REMOVED_TOPIC
        aggregate_id = event_data.batch_id

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=aggregate_id,
            event_type=self.settings.BATCH_FILE_REMOVED_TOPIC,
            event_data=envelope,
            topic=topic,
        )

        logger.info(
            "BatchFileRemovedV1 event stored in outbox for reliable delivery",
            extra={
                "batch_id": event_data.batch_id,
                "file_upload_id": event_data.file_upload_id,
                "filename": event_data.filename,
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

        # Redis publication for real-time UI updates (separate from event bus)
        try:
            # Publish to Redis for real-time updates (maintained as-is)
            await self._publish_file_event_to_redis(
                event_data.user_id,
                "batch_file_removed",
                {
                    "batch_id": event_data.batch_id,
                    "file_upload_id": event_data.file_upload_id,
                    "filename": event_data.filename,
                    "timestamp": event_data.timestamp.isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error publishing BatchFileRemovedV1 Redis notification: {e}")
            raise

    async def _publish_file_event_to_redis(
        self,
        user_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """Publish file event to Redis for real-time UI notifications."""
        try:
            await self.redis_client.publish_user_notification(
                user_id=user_id, event_type=event_type, data=data
            )

            logger.info(
                f"Published {event_type} notification to Redis for user {user_id}",
                extra={"user_id": user_id, "event_type": event_type},
            )

        except Exception as e:
            logger.error(
                f"Error publishing {event_type} to Redis: {e}",
                extra={"user_id": user_id, "event_type": event_type},
                exc_info=True,
            )
            # Don't fail the entire event publishing if Redis fails
