"""Default implementation of SpellcheckEventPublisherProtocol."""

from __future__ import annotations

from uuid import UUID

from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from huleedu_service_libs.error_handling import raise_kafka_publish_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context
from huleedu_service_libs.protocols import KafkaPublisherProtocol

from services.spellchecker_service.protocols import SpellcheckEventPublisherProtocol

logger = create_service_logger("spellchecker_service.event_publisher_impl")


class DefaultSpellcheckEventPublisher(SpellcheckEventPublisherProtocol):
    """Default implementation of SpellcheckEventPublisherProtocol with structured error handling."""

    def __init__(
        self, kafka_event_type: str, source_service_name: str, kafka_output_topic: str
    ) -> None:
        self.kafka_event_type = kafka_event_type
        self.source_service_name = source_service_name
        self.kafka_output_topic = kafka_output_topic

    async def publish_spellcheck_result(
        self,
        kafka_bus: KafkaPublisherProtocol,
        event_data: SpellcheckResultDataV1,
        correlation_id: UUID,
    ) -> None:
        """Publish spellcheck result event to Kafka with structured error handling.

        Args:
            kafka_bus: Kafka publisher instance
            event_data: Spellcheck result data to publish
            correlation_id: Request correlation ID for tracing

        Raises:
            HuleEduError: On any failure to publish event
        """
        entity_id = event_data.entity_id

        logger.debug(
            f"Publishing spellcheck result event for essay {entity_id} "
            f"to topic {self.kafka_output_topic}",
            extra={
                "correlation_id": str(correlation_id),
                "entity_id": entity_id,
                "topic": self.kafka_output_topic,
            },
        )

        try:
            # Create event envelope with correlation tracking
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
            else:
                result_envelope.metadata = {}
                inject_trace_context(result_envelope.metadata)

            # Use entity_id as the key for partitioning
            key = str(entity_id)

            # Publish using KafkaBus which handles serialization
            await kafka_bus.publish(
                topic=self.kafka_output_topic, envelope=result_envelope, key=key
            )

            logger.info(
                f"Successfully published spellcheck completion event for essay {entity_id}",
                extra={
                    "correlation_id": str(correlation_id),
                    "entity_id": entity_id,
                    "topic": self.kafka_output_topic,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to publish spellcheck result event for essay {entity_id}: {e}",
                exc_info=True,
                extra={
                    "correlation_id": str(correlation_id),
                    "entity_id": entity_id,
                    "topic": self.kafka_output_topic,
                },
            )

            raise_kafka_publish_error(
                service="spellchecker_service",
                operation="publish_spellcheck_result",
                topic=self.kafka_output_topic,
                message=f"Failed to publish spellcheck result event: {str(e)}",
                correlation_id=correlation_id,
                event_type=self.kafka_event_type,
                entity_id=entity_id,
                error_type=type(e).__name__,
                kafka_key=key,
            )
