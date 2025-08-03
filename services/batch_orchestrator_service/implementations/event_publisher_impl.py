"""Batch event publisher implementation for Batch Orchestrator Service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.protocols import BatchEventPublisherProtocol

if TYPE_CHECKING:
    from services.batch_orchestrator_service.implementations.outbox_manager import OutboxManager

logger = create_service_logger("bos.event_publisher")


class DefaultBatchEventPublisherImpl(BatchEventPublisherProtocol):
    """Default implementation of BatchEventPublisherProtocol using TRUE OUTBOX PATTERN."""

    def __init__(
        self,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> None:
        """Initialize with outbox manager for TRUE OUTBOX PATTERN."""
        self.outbox_manager = outbox_manager
        self.settings = settings

    async def publish_batch_event(
        self,
        event_envelope: EventEnvelope[Any],
        key: str | None = None,
        session: Any | None = None,  # AsyncSession | None
    ) -> None:
        """Publish batch event using TRUE OUTBOX PATTERN."""
        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if event_envelope.metadata is None:
                event_envelope.metadata = {}
            inject_trace_context(event_envelope.metadata)

        # Determine topic using the topic_name function to get the proper Kafka topic
        # Convert event_type to ProcessingEvent enum and get the Kafka topic name
        try:
            processing_event = ProcessingEvent(event_envelope.event_type)
            topic = topic_name(processing_event)
        except ValueError:
            # If event_type doesn't match any ProcessingEvent, use it as-is
            logger.warning(
                f"Event type '{event_envelope.event_type}' not found in ProcessingEvent enum, "
                "using as topic name directly"
            )
            topic = event_envelope.event_type
            
        aggregate_id = key or str(event_envelope.correlation_id)
        aggregate_type = self._determine_aggregate_type(event_envelope.event_type)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        await self.outbox_manager.publish_to_outbox(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_envelope.event_type,
            event_data=event_envelope,  # Pass original Pydantic envelope
            topic=topic,
            session=session,  # Pass session for transactional atomicity
        )

        logger.info(
            "Event stored in outbox for reliable delivery",
            extra={
                "event_type": event_envelope.event_type,
                "aggregate_id": aggregate_id,
                "correlation_id": str(event_envelope.correlation_id),
                "topic": topic,
            },
        )

    def _determine_aggregate_type(self, event_type: str) -> str:
        """Determine aggregate type from event type.
        
        Now checks both the ProcessingEvent enum value and the full topic name
        to handle both patterns during transition.
        """
        event_lower = event_type.lower()
        
        # Check for batch-related patterns in both enum values and topic names
        # Only match complete words/segments to avoid false positives
        batch_patterns = [
            ".batch.", "batch.", ".spellcheck.", "spellcheck.",
            ".cj_assessment.", "cj_assessment.", ".nlp.", "nlp.",
            ".els.", "els."
        ]
        if any(pattern in event_lower for pattern in batch_patterns):
            return "batch"
        elif ".pipeline." in event_lower or "pipeline." in event_lower:
            return "pipeline"
        else:
            return "unknown"
