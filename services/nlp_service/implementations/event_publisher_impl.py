"""Default implementation of NlpEventPublisherProtocol using outbox pattern."""

from __future__ import annotations

from uuid import UUID

from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import BatchAuthorMatchesSuggestedV1, EssayMatchResult
from common_core.metadata_models import EntityReference
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

    async def publish_batch_author_match_results(
        self,
        kafka_bus: KafkaPublisherProtocol,
        batch_id: str,
        class_id: str,
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

        # Create entity reference for the batch
        entity_ref = EntityReference(
            entity_id=batch_id,
            entity_type="batch",
        )

        # Create the batch event data
        event_data = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            entity_ref=entity_ref,
            batch_id=batch_id,
            class_id=class_id,
            match_results=match_results,
            processing_summary=processing_summary,
        )

        # Create event envelope
        event_envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type="batch.author.matches.suggested.v1",
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
                event_type="batch.author.matches.suggested.v1",
                event_data=event_envelope,
                topic=self.output_topic,
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
