"""Event publisher implementation for File Service."""

from __future__ import annotations

import uuid

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger

from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from services.file_service.config import Settings
from services.file_service.protocols import EventPublisherProtocol

logger = create_service_logger("file_service.implementations.event_publisher")


class DefaultEventPublisher(EventPublisherProtocol):
    """Default implementation of EventPublisherProtocol."""

    def __init__(self, kafka_bus: KafkaBus, settings: Settings):
        self.kafka_bus = kafka_bus
        self.settings = settings

    async def publish_essay_content_provisioned(
        self,
        event_data: EssayContentProvisionedV1,
        correlation_id: uuid.UUID | None,
    ) -> None:
        """Publish EssayContentProvisionedV1 event to Kafka."""
        try:
            # Construct EventEnvelope
            envelope = EventEnvelope[EssayContentProvisionedV1](
                event_type=self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
            )

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
        correlation_id: uuid.UUID | None,
    ) -> None:
        """Publish EssayValidationFailedV1 event to Kafka."""
        try:
            # Construct EventEnvelope
            envelope = EventEnvelope[EssayValidationFailedV1](
                event_type=self.settings.ESSAY_VALIDATION_FAILED_TOPIC,
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
            )

            # Publish to Kafka using KafkaBus
            await self.kafka_bus.publish(
                topic=self.settings.ESSAY_VALIDATION_FAILED_TOPIC,
                envelope=envelope,
            )

            logger.info(
                f"Published EssayValidationFailedV1 event for file: "
                f"{event_data.original_file_name} (error: {event_data.validation_error_code})",
            )

        except Exception as e:
            logger.error(f"Error publishing EssayValidationFailedV1 event: {e}")
            raise

    async def publish_batch_file_added_v1(
        self,
        event_data: BatchFileAddedV1,
        correlation_id: uuid.UUID | None,
    ) -> None:
        """Publish BatchFileAddedV1 event to Kafka."""
        try:
            # Construct EventEnvelope
            envelope = EventEnvelope[BatchFileAddedV1](
                event_type=self.settings.BATCH_FILE_ADDED_TOPIC,
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=event_data,
            )

            # Publish to Kafka using KafkaBus
            await self.kafka_bus.publish(
                topic=self.settings.BATCH_FILE_ADDED_TOPIC,
                envelope=envelope,
            )

            logger.info(
                f"Published BatchFileAddedV1 event for batch {event_data.batch_id}, "
                f"essay {event_data.essay_id}, file: {event_data.filename}",
            )

        except Exception as e:
            logger.error(f"Error publishing BatchFileAddedV1 event: {e}")
            raise

    async def publish_batch_file_removed_v1(
        self,
        event_data: BatchFileRemovedV1,
        correlation_id: uuid.UUID | None,
    ) -> None:
        """Publish BatchFileRemovedV1 event to Kafka."""
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
                f"essay {event_data.essay_id}, file: {event_data.filename}",
            )

        except Exception as e:
            logger.error(f"Error publishing BatchFileRemovedV1 event: {e}")
            raise
