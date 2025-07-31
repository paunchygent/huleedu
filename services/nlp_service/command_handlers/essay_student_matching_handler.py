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
            True if this handler can process essay student matching requests
        """
        return event_type == "huleedu.essay.student.matching.requested.v1"

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
                f"Processing Phase 1 student matching for essay {command_data.essay_id}",
                extra={
                    "essay_id": command_data.essay_id,
                    "class_id": command_data.class_id,
                    "correlation_id": str(correlation_id),
                },
            )

            # Fetch essay content
            essay_text = await self.content_client.fetch_content(
                storage_id=command_data.text_storage_id,
                http_session=http_session,
                correlation_id=correlation_id,
            )

            # Get roster (with caching)
            roster = await self.roster_cache.get_roster(command_data.class_id)
            if not roster:
                roster = await self.class_management_client.get_class_roster(
                    class_id=command_data.class_id,
                    http_session=http_session,
                    correlation_id=correlation_id,
                )
                await self.roster_cache.set_roster(command_data.class_id, roster)

            # Perform student matching
            suggestions = await self.student_matcher.find_matches(
                essay_text=essay_text,
                roster=roster,
                correlation_id=correlation_id,
            )

            # Determine match status
            match_status = determine_match_status(suggestions)

            # Publish match result event
            await self.event_publisher.publish_author_match_result(
                kafka_bus=self.kafka_bus,
                essay_id=command_data.essay_id,
                suggestions=suggestions,
                match_status=match_status,
                correlation_id=correlation_id,
            )

            # Process and publish any pending outbox events
            async with self.outbox_repository.get_connection() as session:
                pending_events = await self.outbox_repository.get_pending_events(
                    session=session, limit=10
                )
                for event_id, event_data in pending_events:
                    try:
                        await self.kafka_bus.publish(
                            topic=event_data["topic"],
                            envelope=event_data["envelope"],
                        )
                        await self.outbox_repository.mark_event_published(event_id=event_id)
                    except Exception as e:
                        logger.error(
                            f"Failed to publish outbox event {event_id}: {e}",
                            extra={"event_id": event_id},
                        )

            logger.info(
                f"Successfully processed Phase 1 student matching for essay {command_data.essay_id}",
                extra={
                    "essay_id": command_data.essay_id,
                    "match_status": match_status,
                    "suggestion_count": len(suggestions),
                    "correlation_id": str(correlation_id),
                },
            )

            return True

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
