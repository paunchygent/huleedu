"""Event publisher implementation for File Service."""

from __future__ import annotations

import json
import uuid
from typing import Optional

from aiokafka import AIOKafkaProducer
from huleedu_service_libs.logging_utils import create_service_logger

from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1, EssayValidationFailedV1
from services.file_service.config import Settings
from services.file_service.protocols import EventPublisherProtocol

logger = create_service_logger("file_service.implementations.event_publisher")


class DefaultEventPublisher(EventPublisherProtocol):
    """Default implementation of EventPublisherProtocol."""

    def __init__(self, producer: AIOKafkaProducer, settings: Settings):
        self.producer = producer
        self.settings = settings

    async def publish_essay_content_provisioned(
        self, event_data: EssayContentProvisionedV1, correlation_id: Optional[uuid.UUID]
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

            # Serialize to JSON
            message_bytes = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

            # Publish to Kafka
            await self.producer.send(self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC, message_bytes)

            logger.info(
                f"Published EssayContentProvisionedV1 event for file: "
                f"{event_data.original_file_name}"
            )

        except Exception as e:
            logger.error(f"Error publishing EssayContentProvisionedV1 event: {e}")
            raise

    async def publish_essay_validation_failed(
        self, event_data: EssayValidationFailedV1, correlation_id: Optional[uuid.UUID]
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

            # Serialize to JSON
            message_bytes = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

            # Publish to Kafka
            await self.producer.send(self.settings.ESSAY_VALIDATION_FAILED_TOPIC, message_bytes)

            logger.info(
                f"Published EssayValidationFailedV1 event for file: "
                f"{event_data.original_file_name} (error: {event_data.validation_error_code})"
            )

        except Exception as e:
            logger.error(f"Error publishing EssayValidationFailedV1 event: {e}")
            raise
