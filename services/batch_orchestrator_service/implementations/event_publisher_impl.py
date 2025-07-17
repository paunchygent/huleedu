"""Batch event publisher implementation for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any

from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.observability import inject_trace_context
from huleedu_service_libs.protocols import KafkaPublisherProtocol

from services.batch_orchestrator_service.protocols import BatchEventPublisherProtocol


class DefaultBatchEventPublisherImpl(BatchEventPublisherProtocol):
    """Default implementation of BatchEventPublisherProtocol."""

    def __init__(self, kafka_bus: KafkaPublisherProtocol) -> None:
        """Initialize with Kafka bus dependency."""
        self.kafka_bus = kafka_bus

    async def publish_batch_event(
        self, event_envelope: EventEnvelope[Any], key: str | None = None
    ) -> None:
        """Publish batch event to Kafka with trace context propagation."""
        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if event_envelope.metadata is None:
                event_envelope.metadata = {}
            inject_trace_context(event_envelope.metadata)

        topic = event_envelope.event_type
        await self.kafka_bus.publish(topic, event_envelope, key=key)
