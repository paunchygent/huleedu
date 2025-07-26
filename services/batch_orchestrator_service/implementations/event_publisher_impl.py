"""Batch event publisher implementation for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any

from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import raise_kafka_publish_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import KafkaPublisherProtocol

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.protocols import BatchEventPublisherProtocol

logger = create_service_logger("bos.event_publisher")


class DefaultBatchEventPublisherImpl(BatchEventPublisherProtocol):
    """Default implementation of BatchEventPublisherProtocol with outbox pattern."""

    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        settings: Settings,
    ) -> None:
        """Initialize with Kafka bus and outbox repository dependencies."""
        self.kafka_bus = kafka_bus
        self.outbox_repository = outbox_repository
        self.settings = settings

    async def publish_batch_event(
        self, event_envelope: EventEnvelope[Any], key: str | None = None
    ) -> None:
        """Publish batch event via transactional outbox pattern."""
        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if event_envelope.metadata is None:
                event_envelope.metadata = {}
            inject_trace_context(event_envelope.metadata)

        # Determine aggregate information from event
        aggregate_id = key or str(event_envelope.correlation_id)
        aggregate_type = self._determine_aggregate_type(event_envelope.event_type)

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_envelope.event_type,
                event_data=event_envelope,
                topic=event_envelope.event_type,  # BOS uses event_type as topic
                event_key=key,
            )

            logger.info(
                "Event stored in outbox for reliable delivery",
                extra={
                    "event_type": event_envelope.event_type,
                    "aggregate_id": aggregate_id,
                    "correlation_id": str(event_envelope.correlation_id),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_kafka_publish_error(
                    service="batch_orchestrator_service",
                    operation="publish_batch_event",
                    message=f"Failed to store event in outbox: {e.__class__.__name__}",
                    correlation_id=event_envelope.correlation_id,
                    topic=event_envelope.event_type,
                    event_type=event_envelope.event_type,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def _publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: EventEnvelope[Any],
        topic: str,
        event_key: str | None = None,
    ) -> None:
        """
        Store event in outbox for reliable delivery.

        This implements the Transactional Outbox Pattern, decoupling business
        operations from Kafka availability.
        """
        # Serialize the envelope to JSON for storage
        serialized_data = event_data.model_dump(mode="json")

        # Store topic in the data for relay worker
        serialized_data["topic"] = topic

        # Store in outbox
        outbox_id = await self.outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            event_data=serialized_data,
            topic=topic,
            event_key=event_key,
        )

        logger.debug(
            "Event stored in outbox",
            extra={
                "outbox_id": str(outbox_id),
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "aggregate_type": aggregate_type,
            },
        )

    def _determine_aggregate_type(self, event_type: str) -> str:
        """Determine aggregate type from event type."""
        if "batch" in event_type.lower():
            return "batch"
        elif "pipeline" in event_type.lower():
            return "pipeline"
        else:
            return "unknown"
