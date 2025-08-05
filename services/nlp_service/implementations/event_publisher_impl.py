"""Default implementation of NlpEventPublisherProtocol using outbox pattern."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import (
    BatchAuthorMatchesSuggestedV1,
    EssayMatchResult,
    StudentMatchSuggestion,
)

# EntityReference removed - using primitive parameters
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context
from huleedu_service_libs.protocols import KafkaPublisherProtocol

from services.nlp_service.implementations.outbox_manager import OutboxManager
from services.nlp_service.protocols import NlpEventPublisherProtocol

logger = create_service_logger("nlp_service.event_publisher_impl")


class DefaultNlpEventPublisher(NlpEventPublisherProtocol):
    """Default implementation using outbox pattern for reliable event publishing."""

    def __init__(
        self,
        outbox_manager: OutboxManager,
        source_service_name: str,
        output_topic: str,
    ) -> None:
        """Initialize NLP event publisher.

        Args:
            outbox_manager: Outbox manager for reliable event storage
            source_service_name: Name of this service for event metadata
            output_topic: Kafka topic to publish results to
        """
        self.outbox_manager = outbox_manager
        self.source_service_name = source_service_name
        self.output_topic = output_topic

    async def publish_author_match_result(
        self,
        kafka_bus: KafkaPublisherProtocol,
        essay_id: str,
        suggestions: list[StudentMatchSuggestion],
        match_status: str,
        correlation_id: UUID,
    ) -> None:
        """Publish individual essay author match results to Kafka.

        This is a compatibility method for the essay-level handler.
        """
        # Convert to batch format with single essay
        match_result = EssayMatchResult(
            essay_id=essay_id,
            text_storage_id="",  # Not available in this context
            filename="",  # Not available in this context
            suggestions=suggestions,
            no_match_reason=None if suggestions else "No matches found",
            extraction_metadata={},
        )

        # Create a batch event with single essay using primitive parameters
        batch_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            entity_id=essay_id,
            entity_type="essay",
            parent_id="single-essay-batch",  # Placeholder for individual essay
            batch_id="single-essay-batch",  # Placeholder for individual essay
            class_id="unknown",  # Not available in this context
            course_code=CourseCode.ENG5,  # Default for legacy single-essay processing
            match_results=[match_result],
            processing_summary={"total_essays": 1, "matched": 1 if suggestions else 0},
        )

        # Create event envelope with proper metadata handling
        metadata: dict[str, Any] = {}
        inject_trace_context(metadata)
        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            data=batch_event,
            metadata=metadata,
        )

        # Store in outbox using TRUE OUTBOX PATTERN
        await self.outbox_manager.publish_to_outbox(
            aggregate_id=essay_id,
            aggregate_type="essay",
            event_type=envelope.event_type,
            event_data=envelope,  # Pass original Pydantic envelope
            topic=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
        )

    async def publish_batch_author_match_results(
        self,
        kafka_bus: KafkaPublisherProtocol,
        batch_id: str,
        class_id: str,
        course_code: CourseCode,
        match_results: list[EssayMatchResult],
        processing_summary: dict[str, int],
        correlation_id: UUID,
    ) -> None:
        """Publish batch author match results to Kafka via outbox pattern.

        Args:
            kafka_bus: Kafka publisher (not used directly due to outbox pattern)
            batch_id: ID of the batch that was processed
            class_id: Class ID for which matching was performed
            match_results: List of match results for all essays in batch
            processing_summary: Summary statistics
            correlation_id: Request correlation ID for tracing

        Note:
            The kafka_bus parameter is maintained for interface compatibility but
            not used directly. Publishing happens via the outbox pattern.
        """
        logger.debug(
            f"Publishing batch author match results for batch {batch_id} via outbox",
            extra={
                "correlation_id": str(correlation_id),
                "batch_id": batch_id,
                "class_id": class_id,
                "total_essays": processing_summary.get("total_essays", 0),
            },
        )

        # Create the batch event data using primitive parameters
        event_data = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            batch_id=batch_id,
            class_id=class_id,
            course_code=course_code,
            match_results=match_results,
            processing_summary=processing_summary,
        )

        # Create event envelope
        event_envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject trace context if available
        if event_envelope.metadata is not None:
            inject_trace_context(event_envelope.metadata)

        try:
            # Publish via outbox pattern
            await self.outbox_manager.publish_to_outbox(
                aggregate_type="batch",
                aggregate_id=batch_id,
                event_type=event_envelope.event_type,
                event_data=event_envelope,
                topic=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            )

            logger.info(
                f"Successfully stored batch author match results in outbox for batch {batch_id}",
                extra={
                    "correlation_id": str(correlation_id),
                    "batch_id": batch_id,
                    "class_id": class_id,
                    "topic": self.output_topic,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to publish batch author match results for batch {batch_id}: {e}",
                exc_info=True,
                extra={
                    "correlation_id": str(correlation_id),
                    "batch_id": batch_id,
                    "topic": self.output_topic,
                },
            )
            # Re-raise - structured error will be handled by OutboxManager
            raise
