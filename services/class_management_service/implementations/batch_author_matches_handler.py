"""Handler for batch author match suggestions from NLP Service.

Processes BatchAuthorMatchesSuggestedV1 events and stores student-essay
association suggestions for teacher validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Span

import aiohttp
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import BatchAuthorMatchesSuggestedV1
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_processing_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.class_management_service.models_db import EssayStudentAssociation
from services.class_management_service.protocols import (
    ClassRepositoryProtocol,
    CommandHandlerProtocol,
)

logger = create_service_logger("class_management_service.batch_author_matches_handler")


class BatchAuthorMatchesHandler(CommandHandlerProtocol):
    """Handler for processing BatchAuthorMatchesSuggestedV1 events from NLP Service."""

    def __init__(
        self,
        class_repository: ClassRepositoryProtocol,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Initialize with required dependencies.

        Args:
            class_repository: Repository for class and student operations
            session_factory: SQLAlchemy session factory for database operations
        """
        self.class_repository = class_repository
        self.session_factory = session_factory

    async def can_handle(self, event_type: str) -> bool:
        """Check if this handler can process the given event type.

        Args:
            event_type: The event type string to check

        Returns:
            True if this handler can process batch author matches suggested events
        """
        return event_type == topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED)

    async def handle(
        self,
        msg: ConsumerRecord,
        envelope: EventEnvelope,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
        span: "Span | None" = None,
    ) -> bool:
        """Process the batch author matches suggested event.

        Workflow:
        1. Parse BatchAuthorMatchesSuggestedV1 event data
        2. Validate batch and class information
        3. Store match suggestions in EssayStudentAssociation table
        4. Set validation_status to 'pending_validation' for all suggestions
        5. Log processing summary for teacher review

        Args:
            msg: The Kafka message to process
            envelope: Already parsed event envelope
            http_session: HTTP session for external service calls (unused)
            correlation_id: Correlation ID for tracking
            span: Optional span for tracing

        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            # Parse event data to the correct type
            # Note: envelope.data may be a BaseModel (from JSON deserialization) or dict
            match_data = BatchAuthorMatchesSuggestedV1.model_validate(envelope.data)

            logger.info(
                f"Processing batch author matches for batch {match_data.batch_id}",
                extra={
                    "batch_id": match_data.batch_id,
                    "class_id": match_data.class_id,
                    "total_essays": len(match_data.match_results),
                    "processing_summary": match_data.processing_summary,
                    "correlation_id": str(correlation_id),
                },
            )

            # Validate required data
            if not match_data.match_results:
                logger.warning(
                    f"No match results provided for batch {match_data.batch_id}",
                    extra={
                        "batch_id": match_data.batch_id,
                        "correlation_id": str(correlation_id),
                    },
                )
                return True  # Not an error, just no matches to process

            # Process all match suggestions in a single transaction
            async with self.session_factory() as session:
                async with session.begin():
                    stored_count = 0
                    failed_count = 0

                    for essay_result in match_data.match_results:
                        try:
                            # Process each suggestion for this essay
                            for suggestion in essay_result.suggestions:
                                # Validate student exists in our database
                                student = await self.class_repository.get_student_by_id(
                                    UUID(suggestion.student_id)
                                )
                                if not student:
                                    logger.warning(
                                        f"Student {suggestion.student_id} not found, skipping suggestion",
                                        extra={
                                            "student_id": suggestion.student_id,
                                            "essay_id": essay_result.essay_id,
                                            "batch_id": match_data.batch_id,
                                            "correlation_id": str(correlation_id),
                                        },
                                    )
                                    continue

                                # Check if association already exists
                                stmt = select(EssayStudentAssociation).where(
                                    EssayStudentAssociation.essay_id == UUID(essay_result.essay_id)
                                )
                                existing_association = await session.scalar(stmt)

                                if existing_association:
                                    logger.info(
                                        f"Association already exists for essay {essay_result.essay_id}, skipping",
                                        extra={
                                            "essay_id": essay_result.essay_id,
                                            "existing_student_id": str(
                                                existing_association.student_id
                                            ),
                                            "suggested_student_id": suggestion.student_id,
                                            "correlation_id": str(correlation_id),
                                        },
                                    )
                                    continue

                                # Create new association with pending validation status
                                # Note: For Phase 1, we store the highest confidence match per essay
                                # Future enhancement could store all suggestions for teacher choice
                                association = EssayStudentAssociation(
                                    essay_id=UUID(essay_result.essay_id),
                                    student_id=UUID(suggestion.student_id),
                                    created_by_user_id="nlp_service_phase1",  # System user for NLP suggestions
                                )

                                session.add(association)
                                stored_count += 1

                                logger.debug(
                                    f"Created association: essay {essay_result.essay_id} -> student {suggestion.student_id}",
                                    extra={
                                        "essay_id": essay_result.essay_id,
                                        "student_id": suggestion.student_id,
                                        "confidence_score": suggestion.confidence_score,
                                        "match_reasons": suggestion.match_reasons,
                                        "correlation_id": str(correlation_id),
                                    },
                                )

                                # Only store the highest confidence match per essay for Phase 1
                                break

                        except Exception as essay_error:
                            logger.error(
                                f"Failed to process suggestions for essay {essay_result.essay_id}",
                                extra={
                                    "essay_id": essay_result.essay_id,
                                    "batch_id": match_data.batch_id,
                                    "error": str(essay_error),
                                    "correlation_id": str(correlation_id),
                                },
                                exc_info=True,
                            )
                            failed_count += 1
                            # Continue processing other essays instead of failing entire batch

                    # Flush to get any constraint violations before commit
                    await session.flush()

                    logger.info(
                        f"Batch author matches processing completed for batch {match_data.batch_id}",
                        extra={
                            "batch_id": match_data.batch_id,
                            "class_id": match_data.class_id,
                            "stored_associations": stored_count,
                            "failed_essays": failed_count,
                            "total_essays": len(match_data.match_results),
                            "processing_summary": match_data.processing_summary,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Transaction commits here
                    return stored_count > 0 or failed_count == 0

        except HuleEduError:
            # Re-raise HuleEdu errors as-is (already have proper structure)
            raise
        except Exception as e:
            logger.error(
                f"Error processing batch author matches for batch {match_data.batch_id if 'match_data' in locals() else 'unknown'}",
                extra={
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
                exc_info=True,
            )
            raise_processing_error(
                service="class_management_service",
                operation="process_batch_author_matches",
                message=f"Failed to process batch author matches: {str(e)}",
                correlation_id=correlation_id,
                batch_id=match_data.batch_id if "match_data" in locals() else None,
                error_type=type(e).__name__,
            )
