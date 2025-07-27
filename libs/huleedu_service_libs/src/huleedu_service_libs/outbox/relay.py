"""
Event Relay Worker for processing events from the transactional outbox.

This module provides a generic, configurable worker that processes the outbox table
and reliably delivers events to Kafka. It uses Redis BLPOP for instant wake-up
notifications and implements adaptive polling for efficiency.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from common_core.events.envelope import EventEnvelope

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import KafkaPublisherProtocol, AtomicRedisClientProtocol

    from .protocols import EventTypeMapperProtocol, OutboxEvent, OutboxRepositoryProtocol

from huleedu_service_libs.logging_utils import create_service_logger

from .monitoring import OutboxMetrics

logger = create_service_logger("outbox.event_relay_worker")


@dataclass
class OutboxSettings:
    """
    Configuration settings for the outbox relay worker.

    Attributes:
        poll_interval_seconds: Maximum time to wait for Redis wake-up notification
        batch_size: Maximum number of events to process per poll
        max_retries: Maximum retry attempts before marking event as failed
        error_retry_interval_seconds: How long to wait after an error
        enable_metrics: Whether to collect Prometheus metrics
        enable_wake_notifications: Whether to use Redis BLPOP for instant wake-up
    """

    poll_interval_seconds: float = 5.0
    batch_size: int = 100
    max_retries: int = 5
    error_retry_interval_seconds: float = 30.0
    enable_metrics: bool = True
    enable_wake_notifications: bool = True


class EventRelayWorker:
    """
    Worker that processes the outbox table and publishes events to Kafka.

    This worker implements the relay component of the Transactional Outbox Pattern,
    ensuring reliable event delivery even when Kafka is temporarily unavailable.
    
    Key improvements:
    - Uses Redis BLPOP for instant wake-up when events are added
    - Adaptive polling to reduce unnecessary database queries
    - Immediate retry on active workload
    """

    def __init__(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_bus: KafkaPublisherProtocol,
        settings: OutboxSettings,
        service_name: str,
        redis_client: AtomicRedisClientProtocol | None = None,
        event_mapper: EventTypeMapperProtocol | None = None,
    ) -> None:
        """
        Initialize the event relay worker.

        Args:
            outbox_repository: Repository for outbox operations
            kafka_bus: Kafka publisher for sending events
            settings: Worker configuration settings
            service_name: Name of the service (for event envelope and Redis key)
            redis_client: Optional Redis client for wake-up notifications
            event_mapper: Optional mapper for event type to topic mapping
        """
        self.outbox_repository = outbox_repository
        self.kafka_bus = kafka_bus
        self.settings = settings
        self.service_name = service_name
        self.redis_client = redis_client
        self.event_mapper = event_mapper
        self._running = False
        self._task: asyncio.Task[None] | None = None
        
        # Redis key for wake-up notifications
        self.wake_key = f"outbox:wake:{service_name}"

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
                "wake_notifications": self.settings.enable_wake_notifications and self.redis_client is not None,
            },
        )

    async def stop(self) -> None:
        """Stop the event relay worker gracefully."""
        if not self._running:
            return

        self._running = False
        
        # Send a wake-up to ensure the worker exits promptly
        if self.redis_client and self.settings.enable_wake_notifications:
            try:
                await self.redis_client.lpush(self.wake_key, "stop")
            except Exception:
                pass  # Ignore errors during shutdown
                
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
                "wake_key": self.wake_key,
            },
        )

        consecutive_empty_polls = 0
        
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

                    # Reset empty poll counter on activity
                    consecutive_empty_polls = 0
                    
                    # Immediately check for more events (no delay)
                    continue
                    
                else:
                    # No events found
                    consecutive_empty_polls += 1
                    
                    # Adaptive polling based on activity
                    if consecutive_empty_polls < 3:
                        # Recent activity - check frequently
                        poll_interval = 0.1
                    elif consecutive_empty_polls < 10:
                        # Some time since activity - moderate polling
                        poll_interval = 1.0
                    else:
                        # Extended idle - use configured interval
                        poll_interval = self.settings.poll_interval_seconds
                
                # Wait for wake-up notification or timeout
                if self.redis_client and self.settings.enable_wake_notifications:
                    try:
                        # BLPOP blocks until an item is available or timeout
                        result = await self.redis_client.blpop(
                            keys=[self.wake_key],
                            timeout=poll_interval
                        )
                        if result:
                            # We were woken up - process immediately
                            logger.debug(
                                "Worker woken up by Redis notification",
                                extra={"service": self.service_name}
                            )
                            continue
                    except Exception as e:
                        logger.warning(
                            "Redis BLPOP failed, falling back to sleep",
                            extra={"error": str(e), "service": self.service_name},
                        )
                        await asyncio.sleep(poll_interval)
                else:
                    # No Redis or wake notifications disabled - use simple sleep
                    await asyncio.sleep(poll_interval)

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