"""
Event Relay Worker for processing events from the transactional outbox.

This worker implements the relay component of the Transactional Outbox Pattern,
polling for unpublished events and reliably delivering them to Kafka.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from common_core.events.envelope import EventEnvelope

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import KafkaPublisherProtocol

    from services.essay_lifecycle_service.config import Settings
    from services.essay_lifecycle_service.protocols import OutboxEvent, OutboxRepositoryProtocol

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("essay_lifecycle_service.event_relay_worker")


class EventRelayWorker:
    """
    Worker that polls the outbox table and publishes events to Kafka.

    Implements the relay component of the Transactional Outbox Pattern,
    ensuring reliable event delivery even when Kafka is temporarily unavailable.
    """

    def __init__(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
    ) -> None:
        """
        Initialize the event relay worker.

        Args:
            outbox_repository: Repository for outbox operations
            kafka_bus: Kafka publisher for sending events
            settings: Service configuration settings
        """
        self.outbox_repository = outbox_repository
        self.kafka_bus = kafka_bus
        self.settings = settings
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the event relay worker background task."""
        if self._running:
            logger.warning("Event relay worker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("Event relay worker started")

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

        logger.info("Event relay worker stopped")

    async def _run(self) -> None:
        """Main worker loop that processes events from the outbox."""
        logger.info(
            "Event relay worker starting",
            extra={
                "poll_interval": self.settings.OUTBOX_POLL_INTERVAL_SECONDS,
                "batch_size": self.settings.OUTBOX_BATCH_SIZE,
                "max_retries": self.settings.OUTBOX_MAX_RETRIES,
            },
        )

        while self._running:
            try:
                # Fetch unpublished events from outbox
                events = await self.outbox_repository.get_unpublished_events(
                    limit=self.settings.OUTBOX_BATCH_SIZE
                )

                if events:
                    logger.info(
                        f"Processing {len(events)} unpublished events from outbox",
                        extra={"event_count": len(events)},
                    )

                    # Process each event
                    for event in events:
                        await self._process_event(event)

                # Sleep before next poll
                await asyncio.sleep(self.settings.OUTBOX_POLL_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                # Worker is being stopped
                break
            except Exception as e:
                logger.error(
                    "Error in event relay worker main loop",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                # Continue running but with a longer delay after error
                await asyncio.sleep(self.settings.OUTBOX_ERROR_RETRY_INTERVAL_SECONDS)

    async def _process_event(self, event: OutboxEvent) -> None:
        """
        Process a single event from the outbox.

        Args:
            event: The outbox event to process
        """
        try:
            # Check if event has exceeded max retries
            if event.retry_count >= self.settings.OUTBOX_MAX_RETRIES:
                logger.error(
                    "Event exceeded max retries, marking as failed",
                    extra={
                        "event_id": str(event.id),
                        "event_type": event.event_type,
                        "aggregate_id": event.aggregate_id,
                        "retry_count": event.retry_count,
                        "last_error": event.last_error,
                    },
                )
                # Mark as failed (published_at remains None)
                await self.outbox_repository.mark_event_failed(
                    event_id=event.id,
                    error=f"Exceeded max retries ({self.settings.OUTBOX_MAX_RETRIES})",
                )
                return

            # Extract topic from event data
            topic = event.event_data.get("topic")
            if not topic:
                # Fallback: try to determine topic from event type
                topic = self._get_topic_for_event_type(event.event_type)

            # Prepare the event envelope for publishing
            envelope_data = event.event_data
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
                },
            )

            # Publish to Kafka
            # Create a mock EventEnvelope for KafkaPublisherProtocol
            mock_envelope = EventEnvelope[Any](
                event_type=event.event_type,
                source_service="essay-lifecycle-service",
                correlation_id=envelope_data.get("correlation_id", event.id),
                data=envelope_data.get("data", envelope_data),
            )

            await self.kafka_bus.publish(topic=topic, envelope=mock_envelope)

            # Mark event as published
            await self.outbox_repository.mark_event_published(event.id)

            logger.info(
                "Successfully published event from outbox",
                extra={
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "topic": topic,
                },
            )

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
                },
                exc_info=True,
            )

            # Update retry count and error in outbox
            await self.outbox_repository.increment_retry_count(
                event_id=event.id,
                error=error_message,
            )

    def _get_topic_for_event_type(self, event_type: str) -> str:
        """
        Map event type to Kafka topic.

        This is a fallback mechanism when topic is not stored in event data.

        Args:
            event_type: The event type to map

        Returns:
            The Kafka topic name
        """
        # Map of event types to topics (based on existing patterns)
        event_topic_map = {
            "essay.status.updated.v1": "essay.status.events",
            "huleedu.els.batch_phase.progress.v1": "batch.phase.progress.events",
            "huleedu.els.batch_phase.concluded.v1": "batch.phase.concluded.events",
            # Add more mappings as needed
        }

        # Try direct mapping first
        if event_type in event_topic_map:
            return event_topic_map[event_type]

        # Try to use common_core topic mapping
        try:
            from common_core.event_enums import ProcessingEvent, topic_name

            # Map event types to ProcessingEvent enum values
            event_enum_map = {
                "huleedu.els.excess.content.provisioned.v1": ProcessingEvent.EXCESS_CONTENT_PROVISIONED,
                "huleedu.els.batch.essays.ready.v1": ProcessingEvent.BATCH_ESSAYS_READY,
                "huleedu.els.essay.slot.assigned.v1": ProcessingEvent.ESSAY_SLOT_ASSIGNED,
                "huleedu.els.batch.phase.outcome.v1": ProcessingEvent.ELS_BATCH_PHASE_OUTCOME,
                topic_name(
                    ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED
                ): ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
                topic_name(
                    ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED
                ): ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED,
            }

            if event_type in event_enum_map:
                return topic_name(event_enum_map[event_type])

        except ImportError:
            logger.warning(
                "Could not import common_core event enums for topic mapping",
                extra={"event_type": event_type},
            )

        # Default fallback - use a generic topic
        logger.warning(
            f"No topic mapping found for event type {event_type}, using default",
            extra={"event_type": event_type},
        )
        return "essay.lifecycle.events"  # Generic fallback topic
