"""Default implementation of SpellcheckEventPublisherProtocol."""

from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from aiokafka import AIOKafkaProducer

from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from services.spell_checker_service.protocols import SpellcheckEventPublisherProtocol


class DefaultSpellcheckEventPublisher(SpellcheckEventPublisherProtocol):
    """Default implementation of SpellcheckEventPublisherProtocol."""

    def __init__(self, kafka_event_type: str, source_service_name: str, kafka_output_topic: str):
        self.kafka_event_type = kafka_event_type
        self.source_service_name = source_service_name
        self.kafka_output_topic = kafka_output_topic

    async def publish_spellcheck_result(
        self,
        producer: AIOKafkaProducer,
        event_data: SpellcheckResultDataV1,
        correlation_id: Optional[UUID],
    ) -> None:
        """Publish spellcheck result event to Kafka."""
        result_envelope = EventEnvelope[SpellcheckResultDataV1](
            event_type=self.kafka_event_type,
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            data=event_data,
        )

        key_to_encode = event_data.entity_ref.entity_id
        if not isinstance(key_to_encode, str):
            key_to_encode = str(key_to_encode)

        encoded_key = key_to_encode.encode("utf-8")
        encoded_message = json.dumps(result_envelope.model_dump(mode="json")).encode("utf-8")

        await producer.send_and_wait(self.kafka_output_topic, encoded_message, key=encoded_key)

        # Add logging to track successful event publishing
        from huleedu_service_libs.logging_utils import create_service_logger

        logger = create_service_logger("spell_checker_service.event_publisher_impl")
        logger.info(
            f"Published spellcheck completion event for essay {event_data.entity_ref.entity_id}"
        )
