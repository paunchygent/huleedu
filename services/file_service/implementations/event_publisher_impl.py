"""Event publisher implementation for File Service."""

from __future__ import annotations

import uuid

from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol

from services.file_service.config import Settings
from services.file_service.protocols import EventPublisherProtocol

logger = create_service_logger("file_service.implementations.event_publisher")


class DefaultEventPublisher(EventPublisherProtocol):
    """Default implementation of EventPublisherProtocol with Kafka and Redis support."""

    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
    ):
        self.kafka_bus = kafka_bus
        self.settings = settings
        self.redis_client = redis_client

    async def publish_essay_content_provisioned(
        self,
        event_data: EssayContentProvisionedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish EssayContentProvisionedV1 event to Kafka."""
        try:
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

            # Publish to Kafka using KafkaBus
            await self.kafka_bus.publish(
                topic=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
                envelope=envelope,
            )

            logger.info(
                f"Published EssayContentProvisionedV1 event for file: "
                f"{event_data.original_file_name}",
            )

        except Exception as e:
            logger.error(f"Error publishing EssayContentProvisionedV1 event: {e}")
            raise

    async def publish_essay_validation_failed(
        self,
        event_data: EssayValidationFailedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish EssayValidationFailedV1 event to Kafka."""
        try:
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

            # Publish to Kafka using KafkaBus
            await self.kafka_bus.publish(
                topic=self.settings.ESSAY_VALIDATION_FAILED_TOPIC,
                envelope=envelope,
            )

            logger.info(
                f"Published EssayValidationFailedV1 event for file: "
                f"{event_data.original_file_name}",
            )

        except Exception as e:
            logger.error(f"Error publishing EssayValidationFailedV1 event: {e}")
            raise

    async def publish_batch_file_added_v1(
        self,
        event_data: BatchFileAddedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish BatchFileAddedV1 event to both Kafka and Redis."""
        try:
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

            # Publish to Kafka using KafkaBus
            await self.kafka_bus.publish(
                topic=self.settings.BATCH_FILE_ADDED_TOPIC,
                envelope=envelope,
            )

            logger.info(
                f"Published BatchFileAddedV1 event for batch {event_data.batch_id}, "
                f"file {event_data.file_upload_id}, filename: {event_data.filename}",
            )

            # Publish to Redis for real-time updates
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
            logger.error(f"Error publishing BatchFileAddedV1 event: {e}")
            raise

    async def publish_batch_file_removed_v1(
        self,
        event_data: BatchFileRemovedV1,
        correlation_id: uuid.UUID,
    ) -> None:
        """Publish BatchFileRemovedV1 event to both Kafka and Redis."""
        try:
            # Construct EventEnvelope
            envelope = EventEnvelope[BatchFileRemovedV1](
                event_type=self.settings.BATCH_FILE_REMOVED_TOPIC,
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
            )

            # Publish to Kafka using KafkaBus
            await self.kafka_bus.publish(
                topic=self.settings.BATCH_FILE_REMOVED_TOPIC,
                envelope=envelope,
            )

            logger.info(
                f"Published BatchFileRemovedV1 event for batch {event_data.batch_id}, "
                f"file {event_data.file_upload_id}, filename: {event_data.filename}",
            )

            # Publish to Redis for real-time updates
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
            logger.error(f"Error publishing BatchFileRemovedV1 event: {e}")
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
