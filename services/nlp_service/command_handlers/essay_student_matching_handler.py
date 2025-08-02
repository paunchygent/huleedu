"""Essay-level student matching command handler for NLP Service Phase 1.

This handler processes individual essay student matching requests from ELS
during Phase 1 batch preparation (before BATCH_ESSAYS_READY).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

import aiohttp
from aiokafka import ConsumerRecord
from common_core.events.envelope import EventEnvelope
from common_core.events.essay_lifecycle_events import BatchStudentMatchingRequestedV1
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import KafkaPublisherProtocol

from services.nlp_service.event_processor import determine_match_status
from services.nlp_service.protocols import (
    ClassManagementClientProtocol,
    CommandHandlerProtocol,
    ContentClientProtocol,
    NlpEventPublisherProtocol,
    RosterCacheProtocol,
    StudentMatcherProtocol,
)

logger = create_service_logger("nlp_service.command_handlers.essay_student_matching")


class EssayStudentMatchingHandler(CommandHandlerProtocol):
    """Handler for processing Phase 1 essay student matching requests."""

    def __init__(
        self,
        content_client: ContentClientProtocol,
        class_management_client: ClassManagementClientProtocol,
        roster_cache: RosterCacheProtocol,
        student_matcher: StudentMatcherProtocol,
        event_publisher: NlpEventPublisherProtocol,
        outbox_repository: OutboxRepositoryProtocol,
        kafka_bus: KafkaPublisherProtocol,
        tracer: "Tracer | None" = None,
    ) -> None:
        """Initialize with all required dependencies.

        Args:
            content_client: Client for fetching essay content
            class_management_client: Client for fetching class rosters
            roster_cache: Cache for class rosters
            student_matcher: Student matching implementation
            event_publisher: Publisher for result events
            outbox_repository: Outbox repository for reliable publishing
            kafka_bus: Kafka bus for publishing events
            tracer: Optional tracer for distributed tracing
        """
        self.content_client = content_client
        self.class_management_client = class_management_client
        self.roster_cache = roster_cache
        self.student_matcher = student_matcher
        self.event_publisher = event_publisher
        self.outbox_repository = outbox_repository
        self.kafka_bus = kafka_bus
        self.tracer = tracer

    async def can_handle(self, event_type: str) -> bool:
        """Check if this handler can process the given event type.

        Args:
            event_type: The event type string to check

        Returns:
            True if this handler can process batch student matching requests
        """
        return event_type == "huleedu.batch.student.matching.requested.v1"

    async def handle(
        self,
        msg: ConsumerRecord,
        envelope: EventEnvelope,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        span: "Span | None" = None,
    ) -> bool:
        """Process the essay student matching request.

        Args:
            msg: The Kafka message to process
            envelope: Already parsed event envelope
            http_session: HTTP session for external service calls
            correlation_id: Correlation ID for tracking
            span: Optional span for tracing

        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            # Parse the command data
            command_data = BatchStudentMatchingRequestedV1.model_validate(envelope.data)

            logger.info(
                f"Processing Phase 1 student matching for batch {command_data.batch_id} "
                f"with {len(command_data.essays_to_process)} essays",
                extra={
                    "batch_id": command_data.batch_id,
                    "class_id": command_data.class_id,
                    "essay_count": len(command_data.essays_to_process),
                    "correlation_id": str(correlation_id),
                },
            )

            # Get roster once for all essays in the batch (with caching)
            roster = await self.roster_cache.get_roster(command_data.class_id)
            if not roster:
                roster = await self.class_management_client.get_class_roster(
                    class_id=command_data.class_id,
                    http_session=http_session,
                    correlation_id=correlation_id,
                )
                await self.roster_cache.set_roster(command_data.class_id, roster)

            # Process each essay in the batch and collect results
            from common_core.events.nlp_events import EssayMatchResult

            match_results: list[EssayMatchResult] = []
            processed_count = 0
            matched_count = 0

            for essay_ref in command_data.essays_to_process:
                try:
                    logger.info(
                        f"Processing essay {essay_ref.essay_id} in batch {command_data.batch_id}",
                        extra={
                            "essay_id": essay_ref.essay_id,
                            "batch_id": command_data.batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Fetch essay content
                    essay_text = await self.content_client.fetch_content(
                        storage_id=essay_ref.text_storage_id,
                        http_session=http_session,
                        correlation_id=correlation_id,
                    )

                    # Perform student matching
                    suggestions = await self.student_matcher.find_matches(
                        essay_text=essay_text,
                        roster=roster,
                        correlation_id=correlation_id,
                    )

                    # Determine match status
                    match_status = determine_match_status(suggestions)

                    # Create match result for this essay
                    match_result = EssayMatchResult(
                        essay_id=essay_ref.essay_id,
                        text_storage_id=essay_ref.text_storage_id,
                        filename=getattr(essay_ref, "filename", ""),
                        suggestions=suggestions,
                        no_match_reason=None if suggestions else "No matches found",
                        extraction_metadata={
                            "match_status": match_status,
                            "confidence_scores": (
                                [s.confidence_score for s in suggestions] 
                                if suggestions else []
                            )
                        },
                    )
                    match_results.append(match_result)

                    processed_count += 1
                    if suggestions:
                        matched_count += 1

                    logger.info(
                        "Successfully processed Phase 1 student matching for essay %s",
                        essay_ref.essay_id,
                        extra={
                            "essay_id": essay_ref.essay_id,
                            "batch_id": command_data.batch_id,
                            "match_status": match_status,
                            "suggestion_count": len(suggestions),
                            "correlation_id": str(correlation_id),
                        },
                    )

                except Exception as essay_error:
                    logger.error(
                        f"Failed to process essay {essay_ref.essay_id} in batch "
                        f"{command_data.batch_id}: {essay_error}",
                        extra={
                            "essay_id": essay_ref.essay_id,
                            "batch_id": command_data.batch_id,
                            "error": str(essay_error),
                            "correlation_id": str(correlation_id),
                        },
                        exc_info=True,
                    )
                    # Add a failed result for this essay
                    match_result = EssayMatchResult(
                        essay_id=essay_ref.essay_id,
                        text_storage_id=essay_ref.text_storage_id,
                        filename=getattr(essay_ref, "filename", ""),
                        suggestions=[],
                        no_match_reason=f"Processing error: {str(essay_error)}",
                        extraction_metadata={
                            "error": str(essay_error),
                            "match_status": "ERROR"
                        },
                    )
                    match_results.append(match_result)
                    # Continue processing other essays instead of failing the entire batch
                    continue

            # Publish batch results to Class Management Service
            if match_results:
                processing_summary = {
                    "total_essays": len(command_data.essays_to_process),
                    "processed": processed_count,
                    "matched": matched_count,
                    "unmatched": processed_count - matched_count,
                    "failed": len(command_data.essays_to_process) - processed_count,
                }

                await self.event_publisher.publish_batch_author_match_results(
                    kafka_bus=self.kafka_bus,
                    batch_id=command_data.batch_id,
                    class_id=command_data.class_id,
                    match_results=match_results,
                    processing_summary=processing_summary,
                    correlation_id=correlation_id,
                )

                logger.info(
                    "Published batch author matches for batch %s to Class Management",
                    command_data.batch_id,
                    extra={
                        "batch_id": command_data.batch_id,
                        "class_id": command_data.class_id,
                        "total_results": len(match_results),
                        "processing_summary": processing_summary,
                        "correlation_id": str(correlation_id),
                    },
                )

            logger.info(
                f"Completed Phase 1 student matching for batch {command_data.batch_id}: "
                f"{processed_count}/{len(command_data.essays_to_process)} essays processed",
                extra={
                    "batch_id": command_data.batch_id,
                    "processed_count": processed_count,
                    "total_count": len(command_data.essays_to_process),
                    "correlation_id": str(correlation_id),
                },
            )

            return (
                processed_count > 0
            )  # Return True if at least one essay was processed successfully

        except HuleEduError:
            # Re-raise HuleEdu errors as-is
            raise
        except Exception as e:
            logger.error(
                f"Error processing Phase 1 student matching: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise
