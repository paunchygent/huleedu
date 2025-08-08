"""Default implementation of SpellcheckEventPublisherProtocol using TRUE OUTBOX PATTERN."""

from __future__ import annotations

from uuid import UUID

from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.spellchecker_service.implementations.outbox_manager import OutboxManager
from services.spellchecker_service.protocols import SpellcheckEventPublisherProtocol

logger = create_service_logger("spellchecker_service.event_publisher_impl")


class DefaultSpellcheckEventPublisher(SpellcheckEventPublisherProtocol):
    """Default implementation using TRUE OUTBOX PATTERN for transactional safety."""

    def __init__(
        self, 
        kafka_event_type: str, 
        source_service_name: str, 
        kafka_output_topic: str,
        outbox_manager: OutboxManager,
    ) -> None:
        self.kafka_event_type = kafka_event_type
        self.source_service_name = source_service_name
        self.kafka_output_topic = kafka_output_topic
        self.outbox_manager = outbox_manager

    async def publish_spellcheck_result(
        self,
        event_data: SpellcheckResultDataV1,
        correlation_id: UUID,
    ) -> None:
        """Publish spellcheck result event via outbox pattern for transactional safety.

        Args:
            event_data: Spellcheck result data to publish
            correlation_id: Request correlation ID for tracing

        Raises:
            HuleEduError: On any failure to store event in outbox
        """
        entity_id = event_data.entity_id

        logger.debug(
            f"Publishing spellcheck result event for essay {entity_id} via outbox pattern",
            extra={
                "correlation_id": str(correlation_id),
                "entity_id": entity_id,
                "event_type": self.kafka_event_type,
                "topic": self.kafka_output_topic,
            },
        )

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

        # Add partition key to metadata for Kafka routing
        result_envelope.metadata["partition_key"] = str(entity_id)

        # Store in outbox for transactional safety - NO DIRECT KAFKA
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id=str(entity_id),
            event_type=self.kafka_event_type,
            event_data=result_envelope,
            topic=self.kafka_output_topic,
        )

        logger.info(
            f"Spellcheck result event stored in outbox for essay {entity_id}",
            extra={
                "correlation_id": str(correlation_id),
                "entity_id": entity_id,
                "event_type": self.kafka_event_type,
                "topic": self.kafka_output_topic,
            },
        )
