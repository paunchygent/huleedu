"""Batch event publisher implementation for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.kafka_client import KafkaBus
from services.batch_orchestrator_service.protocols import BatchEventPublisherProtocol

from common_core.events.envelope import EventEnvelope


class DefaultBatchEventPublisherImpl(BatchEventPublisherProtocol):
    """Default implementation of BatchEventPublisherProtocol."""

    def __init__(self, kafka_bus: KafkaBus) -> None:
        """Initialize with Kafka bus dependency."""
        self.kafka_bus = kafka_bus

    async def publish_batch_event(
        self, event_envelope: EventEnvelope[Any], key: str | None = None
    ) -> None:
        """Publish batch event to Kafka."""
        topic = event_envelope.event_type
        # Use KafkaBus.publish() which handles EventEnvelope serialization
        await self.kafka_bus.publish(topic, event_envelope, key=key)
