"""Batch NLP command handler for NLP Service Phase 2.

This handler processes batch NLP initiate commands during Phase 2 pipeline processing
to perform NLP analysis on essays (after student matching is already complete).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Span, Tracer

import aiohttp
from aiokafka import ConsumerRecord
from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV1
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from pydantic import ValidationError

from services.nlp_service.event_processor import determine_match_status
from services.nlp_service.protocols import (
    ClassManagementClientProtocol,
    CommandHandlerProtocol,
    ContentClientProtocol,
    NlpEventPublisherProtocol,
    RosterCacheProtocol,
    StudentMatcherProtocol,
)

logger = create_service_logger("nlp_service.command_handlers.student_matching")


class StudentMatchingHandler(CommandHandlerProtocol):
    """Handler for processing student matching commands."""

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
            True if this handler can process Phase 2 batch NLP initiate commands
        """
        return event_type == "huleedu.batch.nlp.initiate.command.v1"

    async def handle(
        self,
        msg: ConsumerRecord,
        envelope: EventEnvelope,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        span: "Span | None" = None,
    ) -> bool:
        """Process the student matching command.

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
            # Validate the data is the expected type
            request_data = BatchServiceNLPInitiateCommandDataV1.model_validate(envelope.data)

            # Log about the event we received
            log_event_processing(
                logger=logger,
                message="Received NLP batch initiate command",
                envelope=envelope,
                current_processing_event="batch.nlp.initiate",
                essay_count=len(request_data.essays_to_process),
            )

            # Process each essay in the batch
            for essay_ref in request_data.essays_to_process:
                essay_id = essay_ref.essay_id

                logger.info(
                    f"Step 1: Fetching content for essay {essay_id}",
                    extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                )

                # Fetch essay content
                try:
                    essay_text = await self.content_client.fetch_content(
                        storage_id=essay_ref.text_storage_id,
                        http_session=http_session,
                        correlation_id=correlation_id,
                    )
                    logger.info(
                        f"Step 2: Content fetched successfully for essay {essay_id}",
                        extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                    )
                except HuleEduError:
                    # Already structured error from content client - re-raise
                    raise
                except Exception as e:
                    logger.error(
                        f"Failed to fetch content for essay {essay_id}: {e}",
                        exc_info=True,
                        extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                    )
                    # Continue with next essay
                    continue

                if not essay_text:
                    logger.warning(
                        f"Empty content for essay {essay_id}, skipping",
                        extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                    )
                    continue

                # Extract class_id from essay_ref - need to determine where this comes from
                # For now, assuming it's part of the metadata or we need to extract it
                # This would need to be provided in the actual implementation
                class_id = getattr(essay_ref, "class_id", None)

                if not class_id:
                    logger.warning(
                        f"No class_id available for essay {essay_id}, skipping matching",
                        extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                    )
                    # Still publish a NO_MATCH result
                    await self.event_publisher.publish_author_match_result(
                        kafka_bus=self.kafka_bus,
                        essay_id=essay_id,
                        suggestions=[],
                        match_status="NO_MATCH",
                        correlation_id=correlation_id,
                    )
                    continue

                logger.info(
                    f"Step 3: Fetching roster for class {class_id}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "essay_id": essay_id,
                        "class_id": class_id,
                    },
                )

                # Get roster (with caching)
                roster = await self.roster_cache.get_roster(class_id)
                if not roster:
                    # Cache miss - fetch from service
                    try:
                        roster = await self.class_management_client.get_class_roster(
                            class_id=class_id,
                            http_session=http_session,
                            correlation_id=correlation_id,
                        )
                        # Cache the roster
                        await self.roster_cache.set_roster(class_id, roster)
                    except HuleEduError:
                        # Already structured error - re-raise
                        raise
                    except Exception as e:
                        logger.error(
                            f"Failed to fetch roster for class {class_id}: {e}",
                            exc_info=True,
                            extra={"correlation_id": str(correlation_id), "class_id": class_id},
                        )
                        # Continue with next essay
                        continue

                if not roster:
                    logger.warning(
                        f"Empty roster for class {class_id}, cannot match students",
                        extra={"correlation_id": str(correlation_id), "class_id": class_id},
                    )
                    # Publish NO_MATCH result
                    await self.event_publisher.publish_author_match_result(
                        kafka_bus=self.kafka_bus,
                        essay_id=essay_id,
                        suggestions=[],
                        match_status="NO_MATCH",
                        correlation_id=correlation_id,
                    )
                    continue

                logger.info(
                    f"Step 4: Performing student matching for essay {essay_id}",
                    extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                )

                # Perform student matching
                suggestions = await self.student_matcher.find_matches(
                    essay_text=essay_text,
                    roster=roster,
                    correlation_id=correlation_id,
                )

                # Determine overall match status
                match_status = determine_match_status(suggestions)

                logger.info(
                    f"Step 5: Publishing match result for essay {essay_id}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "essay_id": essay_id,
                        "match_status": match_status,
                        "suggestion_count": len(suggestions),
                    },
                )

                # Publish result via outbox
                await self.event_publisher.publish_author_match_result(
                    kafka_bus=self.kafka_bus,
                    essay_id=essay_id,
                    suggestions=suggestions,
                    match_status=match_status,
                    correlation_id=correlation_id,
                )

            logger.info(
                f"Completed processing NLP batch with {len(request_data.essays_to_process)} essays",
                extra={"correlation_id": str(correlation_id)},
            )
            return True

        except ValidationError as e:
            # Use structured error handling for validation errors
            logger.error(
                f"Invalid message format: {e.errors()}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            # Re-raise to let error handler deal with it
            raise

        except HuleEduError:
            # Already structured error - re-raise
            raise

        except Exception as e:
            logger.error(
                f"Unhandled error processing NLP batch: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            # Re-raise for caller to handle
            raise
