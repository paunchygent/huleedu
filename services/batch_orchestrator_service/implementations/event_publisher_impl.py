"""Batch event publisher implementation for Batch Orchestrator Service."""

from __future__ import annotations

from typing import Any

from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import raise_outbox_storage_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import KafkaPublisherProtocol, AtomicRedisClientProtocol

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.protocols import BatchEventPublisherProtocol

logger = create_service_logger("bos.event_publisher")


class DefaultBatchEventPublisherImpl(BatchEventPublisherProtocol):
    """Default implementation of BatchEventPublisherProtocol with outbox pattern."""

    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> None:
        """Initialize with Kafka bus, outbox repository, and Redis dependencies."""
        self.kafka_bus = kafka_bus
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client
        self.settings = settings

    async def publish_batch_event(
        self, event_envelope: EventEnvelope[Any], key: str | None = None
    ) -> None:
        """Publish batch event with immediate Kafka attempt and outbox fallback."""
        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if event_envelope.metadata is None:
                event_envelope.metadata = {}
            inject_trace_context(event_envelope.metadata)

        # Determine topic (BOS uses event_type as topic)
        topic = event_envelope.event_type
        
        # Try immediate Kafka publishing first
        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=event_envelope,
                key=key,
            )
            
            logger.info(
                "Event published directly to Kafka",
                extra={
                    "event_type": event_envelope.event_type,
                    "correlation_id": str(event_envelope.correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!
            
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise
            
            logger.warning(
                "Kafka publish failed, falling back to outbox",
                extra={
                    "event_type": event_envelope.event_type,
                    "correlation_id": str(event_envelope.correlation_id),
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

        # Kafka failed - use outbox pattern as fallback
        aggregate_id = key or str(event_envelope.correlation_id)
        aggregate_type = self._determine_aggregate_type(event_envelope.event_type)

        # Store in outbox for reliable delivery
        try:
            await self._publish_to_outbox(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_envelope.event_type,
                event_data=event_envelope,
                topic=topic,
                event_key=key,
            )
            
            # Wake up the relay worker immediately
            await self._notify_relay_worker()

            logger.info(
                "Event stored in outbox and relay worker notified",
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
                raise_outbox_storage_error(
                    service="batch_orchestrator_service",
                    operation="publish_batch_event",
                    message=f"{e.__class__.__name__}: {str(e)}",
                    correlation_id=event_envelope.correlation_id,
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type=event_envelope.event_type,
                    topic=topic,
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
    
    async def _notify_relay_worker(self) -> None:
        """Notify the relay worker that new events are available in the outbox."""
        try:
            # Use LPUSH to add a notification to the wake-up list
            # The relay worker will use BLPOP to wait for this
            await self.redis_client.lpush("outbox:wake:batch_orchestrator_service", "1")
            logger.debug("Relay worker notified via Redis")
        except Exception as e:
            # Log but don't fail - the relay worker will still poll eventually
            logger.warning(
                "Failed to notify relay worker via Redis",
                extra={"error": str(e)},
            )

    def _determine_aggregate_type(self, event_type: str) -> str:
        """Determine aggregate type from event type."""
        if "batch" in event_type.lower():
            return "batch"
        elif "pipeline" in event_type.lower():
            return "pipeline"
        else:
            return "unknown"