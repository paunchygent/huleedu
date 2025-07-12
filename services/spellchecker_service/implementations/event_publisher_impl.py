"""Default implementation of SpellcheckEventPublisherProtocol."""

from __future__ import annotations

from uuid import UUID

from huleedu_service_libs.protocols import KafkaPublisherProtocol

from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from services.spellchecker_service.protocols import SpellcheckEventPublisherProtocol


class DefaultSpellcheckEventPublisher(SpellcheckEventPublisherProtocol):
    """Default implementation of SpellcheckEventPublisherProtocol."""

    def __init__(self, kafka_event_type: str, source_service_name: str, kafka_output_topic: str):
        self.kafka_event_type = kafka_event_type
        self.source_service_name = source_service_name
        self.kafka_output_topic = kafka_output_topic

    async def publish_spellcheck_result(
        self,
        kafka_bus: KafkaPublisherProtocol,
        event_data: SpellcheckResultDataV1,
        correlation_id: UUID,
    ) -> None:
        """Publish spellcheck result event to Kafka."""
        from huleedu_service_libs.observability import inject_trace_context

        result_envelope = EventEnvelope[SpellcheckResultDataV1](
            event_type=self.kafka_event_type,
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject current trace context into the envelope metadata
        if result_envelope.metadata is not None:
            inject_trace_context(result_envelope.metadata)

        # Use entity_id as the key for partitioning
        key = str(event_data.entity_ref.entity_id)

        # Publish using KafkaBus which handles serialization
        await kafka_bus.publish(topic=self.kafka_output_topic, envelope=result_envelope, key=key)

        # Add logging to track successful event publishing
        from huleedu_service_libs.logging_utils import create_service_logger

        logger = create_service_logger("spellchecker_service.event_publisher_impl")
        logger.info(
            f"Published spellcheck completion event for essay {event_data.entity_ref.entity_id}",
        )
