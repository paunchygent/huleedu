"""Default implementation of NlpEventPublisherProtocol using outbox pattern."""

from __future__ import annotations

from uuid import UUID

from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import EssayAuthorMatchSuggestedV1, StudentMatchSuggestion
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from datetime import UTC, datetime

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
        """Publish author match results to Kafka via outbox pattern.
        
        Args:
            kafka_bus: Kafka publisher (not used directly due to outbox pattern)
            essay_id: ID of the essay that was analyzed
            suggestions: List of student match suggestions
            match_status: Overall match status (HIGH_CONFIDENCE, NEEDS_REVIEW, NO_MATCH)
            correlation_id: Request correlation ID for tracing
            
        Note:
            The kafka_bus parameter is maintained for interface compatibility but
            not used directly. Publishing happens via the outbox pattern.
        """
        logger.debug(
            f"Publishing author match result for essay {essay_id} via outbox",
            extra={
                "correlation_id": str(correlation_id),
                "essay_id": essay_id,
                "match_status": match_status,
                "suggestion_count": len(suggestions),
            },
        )
        
        # Create entity reference for the essay
        entity_ref = EntityReference(
            entity_id=essay_id,
            entity_type="essay",
        )
        
        # Determine essay status based on match result
        if match_status == "HIGH_CONFIDENCE":
            essay_status = EssayStatus.NLP_AUTHOR_MATCHED
        elif match_status == "NEEDS_REVIEW":
            essay_status = EssayStatus.NLP_AUTHOR_REVIEW_NEEDED
        else:  # NO_MATCH
            essay_status = EssayStatus.NLP_AUTHOR_NOT_FOUND
        
        # Create system metadata
        system_metadata = SystemProcessingMetadata(
            entity=entity_ref,
            timestamp=datetime.now(UTC),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED.value,
            started_at=datetime.now(UTC),  # Would be tracked from processing start
            completed_at=datetime.now(UTC),
        )
        
        # Create the event data
        event_data = EssayAuthorMatchSuggestedV1(
            event_name=ProcessingEvent.ESSAY_AUTHOR_MATCH_SUGGESTED,
            entity_ref=entity_ref,
            timestamp=datetime.now(UTC),
            status=essay_status,
            system_metadata=system_metadata,
            essay_id=essay_id,
            suggestions=suggestions,
            match_status=match_status,
        )
        
        # Create event envelope
        event_envelope = EventEnvelope[EssayAuthorMatchSuggestedV1](
            event_type="essay.author.match.suggested.v1",
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )
        
        # Inject trace context if available
        inject_trace_context(event_envelope.metadata)
        
        try:
            # Publish via outbox pattern
            await self.outbox_manager.publish_to_outbox(
                aggregate_type="essay",
                aggregate_id=essay_id,
                event_type="essay.author.match.suggested.v1",
                event_data=event_envelope,
                topic=self.output_topic,
            )
            
            logger.info(
                f"Successfully stored author match result in outbox for essay {essay_id}",
                extra={
                    "correlation_id": str(correlation_id),
                    "essay_id": essay_id,
                    "match_status": match_status,
                    "topic": self.output_topic,
                },
            )
            
        except Exception as e:
            logger.error(
                f"Failed to publish author match result for essay {essay_id}: {e}",
                exc_info=True,
                extra={
                    "correlation_id": str(correlation_id),
                    "essay_id": essay_id,
                    "topic": self.output_topic,
                },
            )
            # Re-raise - structured error will be handled by OutboxManager
            raise