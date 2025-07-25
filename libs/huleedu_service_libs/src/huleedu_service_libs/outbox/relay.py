"""
Event Relay Worker for processing events from the transactional outbox.

This module provides a generic, configurable worker that polls the outbox table
and reliably delivers events to Kafka. It handles retries, error tracking, and
graceful shutdown.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from common_core.events.envelope import EventEnvelope

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import KafkaPublisherProtocol

    from .protocols import EventTypeMapperProtocol, OutboxEvent, OutboxRepositoryProtocol

from huleedu_service_libs.logging_utils import create_service_logger

from .monitoring import OutboxMetrics

logger = create_service_logger("outbox.event_relay_worker")


@dataclass
class OutboxSettings:
    """
    Configuration settings for the outbox relay worker.

    Attributes:
        poll_interval_seconds: How often to poll for new events
        batch_size: Maximum number of events to process per poll
        max_retries: Maximum retry attempts before marking event as failed
        error_retry_interval_seconds: How long to wait after an error
        enable_metrics: Whether to collect Prometheus metrics
    """

    poll_interval_seconds: float = 5.0
    batch_size: int = 100
    max_retries: int = 5
    error_retry_interval_seconds: float = 30.0
    enable_metrics: bool = True


class EventRelayWorker:
    """
    Worker that polls the outbox table and publishes events to Kafka.

    This worker implements the relay component of the Transactional Outbox Pattern,
    ensuring reliable event delivery even when Kafka is temporarily unavailable.
    """

    def __init__(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_bus: KafkaPublisherProtocol,
        settings: OutboxSettings,
        service_name: str,
        event_mapper: EventTypeMapperProtocol | None = None,
    ) -> None:
        """
        Initialize the event relay worker.

        Args:
            outbox_repository: Repository for outbox operations
            kafka_bus: Kafka publisher for sending events
            settings: Worker configuration settings
            service_name: Name of the service (for event envelope)
            event_mapper: Optional mapper for event type to topic mapping
        """
        self.outbox_repository = outbox_repository
        self.kafka_bus = kafka_bus
        self.settings = settings
        self.service_name = service_name
        self.event_mapper = event_mapper
        self._running = False
        self._task: asyncio.Task[None] | None = None

        # Initialize metrics if enabled
        self.metrics = OutboxMetrics() if settings.enable_metrics else None

    async def start(self) -> None:
        """Start the event relay worker background task."""
        if self._running:
            logger.warning("Event relay worker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(
            "Event relay worker started",
            extra={
                "service": self.service_name,
                "poll_interval": self.settings.poll_interval_seconds,
                "batch_size": self.settings.batch_size,
                "max_retries": self.settings.max_retries,
            },
        )

    async def stop(self) -> None:
        """Stop the event relay worker gracefully."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Event relay worker stopped", extra={"service": self.service_name})

    async def _run(self) -> None:
        """Main worker loop that processes events from the outbox."""
        logger.info(
            "Event relay worker starting main loop",
            extra={
                "service": self.service_name,
                "poll_interval": self.settings.poll_interval_seconds,
                "batch_size": self.settings.batch_size,
                "max_retries": self.settings.max_retries,
            },
        )

        while self._running:
            try:
                # Fetch unpublished events from outbox
                events = await self.outbox_repository.get_unpublished_events(
                    limit=self.settings.batch_size
                )

                if events:
                    logger.info(
                        f"Processing {len(events)} unpublished events from outbox",
                        extra={"event_count": len(events), "service": self.service_name},
                    )

                    # Update metrics
                    if self.metrics:
                        self.metrics.set_queue_depth(len(events))

                    # Process each event
                    for event in events:
                        await self._process_event(event)

                # Sleep before next poll
                await asyncio.sleep(self.settings.poll_interval_seconds)

            except asyncio.CancelledError:
                # Worker is being stopped
                break
            except Exception as e:
                logger.error(
                    "Error in event relay worker main loop",
                    extra={"error": str(e), "service": self.service_name},
                    exc_info=True,
                )

                # Record error in metrics
                if self.metrics:
                    self.metrics.increment_errors()

                # Continue running but with a longer delay after error
                await asyncio.sleep(self.settings.error_retry_interval_seconds)

    async def _process_event(self, event: OutboxEvent) -> None:
        """
        Process a single event from the outbox.

        Args:
            event: The outbox event to process
        """
        try:
            # Check if event has exceeded max retries
            if event.retry_count >= self.settings.max_retries:
                logger.error(
                    "Event exceeded max retries, marking as failed",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "aggregate_id": event.aggregate_id,
                        "retry_count": event.retry_count,
                        "last_error": event.last_error,
                        "service": self.service_name,
                    },
                )
                # Mark as failed
                await self.outbox_repository.mark_event_failed(
                    event_id=event.id,
                    error=f"Exceeded max retries ({self.settings.max_retries})",
                )

                # Update metrics
                if self.metrics:
                    self.metrics.increment_failed_events()

                return

            # Extract topic from event data
            topic = event.event_data.get("topic")
            if not topic:
                # Try to get topic from event mapper if available
                if self.event_mapper:
                    try:
                        topic = self.event_mapper.get_topic_for_event(event.event_type)
                    except ValueError:
                        logger.error(
                            f"No topic mapping found for event type {event.event_type}",
                            extra={"event_type": event.event_type, "service": self.service_name},
                        )
                        topic = "unknown.events"  # Fallback topic
                else:
                    logger.warning(
                        f"No topic found in event data and no mapper provided for "
                        f"{event.event_type}",
                        extra={"event_type": event.event_type, "service": self.service_name},
                    )
                    topic = "unknown.events"  # Fallback topic

            # Prepare the event envelope for publishing
            envelope_data = event.event_data.copy()
            # Remove internal fields that shouldn't be published
            envelope_data.pop("topic", None)

            logger.info(
                "Publishing event from outbox to Kafka",
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "topic": topic,
                    "aggregate_id": event.aggregate_id,
                    "retry_count": event.retry_count,
                    "service": self.service_name,
                },
            )

            # Create event envelope
            envelope = EventEnvelope[Any](
                event_type=event.event_type,
                source_service=envelope_data.get("source_service", self.service_name),
                correlation_id=envelope_data.get("correlation_id", event.id),
                data=envelope_data.get("data", envelope_data),
                metadata=envelope_data.get("metadata", {}),
            )

            # Publish to Kafka
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=event.event_key,
            )

            # Mark event as published
            await self.outbox_repository.mark_event_published(event.id)

            logger.info(
                "Successfully published event from outbox",
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "topic": topic,
                    "service": self.service_name,
                },
            )

            # Update metrics
            if self.metrics:
                self.metrics.increment_published_events()

        except Exception as e:
            error_message = f"Failed to publish event to Kafka: {e}"
            logger.error(
                error_message,
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "aggregate_id": event.aggregate_id,
                    "retry_count": event.retry_count,
                    "error": str(e),
                    "service": self.service_name,
                },
                exc_info=True,
            )

            # Update retry count and error in outbox
            await self.outbox_repository.increment_retry_count(
                event_id=event.id,
                error=error_message,
            )

            # Update metrics
            if self.metrics:
                self.metrics.increment_errors()
