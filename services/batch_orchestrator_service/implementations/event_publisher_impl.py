"""Batch event publisher implementation for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any

from aiokafka import AIOKafkaProducer
from protocols import BatchEventPublisherProtocol

from common_core.events.envelope import EventEnvelope


class DefaultBatchEventPublisherImpl(BatchEventPublisherProtocol):
    """Default implementation of BatchEventPublisherProtocol."""

    def __init__(self, producer: AIOKafkaProducer) -> None:
        """Initialize with Kafka producer dependency."""
        self.producer = producer

    async def publish_batch_event(self, event_envelope: EventEnvelope[Any]) -> None:
        """Publish batch event to Kafka."""
        topic = event_envelope.event_type
        # Use Pydantic's model_dump_json() to properly serialize the EventEnvelope
        message = event_envelope.model_dump_json().encode("utf-8")

        await self.producer.send_and_wait(topic, message)
