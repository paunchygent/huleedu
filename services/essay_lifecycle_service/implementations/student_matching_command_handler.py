"""
Student matching command handler for Essay Lifecycle Service.

Handles student matching initiation commands from BOS for Phase 1 REGULAR batch processing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.batch_service_models import BatchServiceStudentMatchingInitiateCommandDataV1
    from sqlalchemy.ext.asyncio import async_sessionmaker

from common_core.events.essay_lifecycle_events import BatchStudentMatchingRequestedV1
from huleedu_service_libs.error_handling import raise_processing_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    EssayRepositoryProtocol,
    OutboxManagerProtocol,
)

logger = create_service_logger("student_matching_command_handler")


class StudentMatchingCommandHandler:
    """
    Handles BATCH_STUDENT_MATCHING_INITIATE_COMMAND from BOS.

    This handler processes Phase 1 student matching commands for REGULAR batches,
    updating essay states and dispatching matching requests to the NLP Service.
    """

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_tracker: BatchEssayTracker,
        outbox_manager: OutboxManagerProtocol,
        session_factory: async_sessionmaker,
    ) -> None:
        self.repository = repository
        self.batch_tracker = batch_tracker
        self.outbox_manager = outbox_manager
        self.session_factory = session_factory

    async def handle_student_matching_command(
        self,
        command_data: BatchServiceStudentMatchingInitiateCommandDataV1,
        correlation_id: UUID,
    ) -> None:
        """
        Process student matching initiation command from Batch Orchestrator Service.

        This handler acts as a stateless event router during Phase 1.
        It simply transforms the command into an event for the NLP Service.

        1. Validate command data
        2. Create BatchStudentMatchingRequestedV1 event
        3. Publish to NLP Service via outbox
        """
        if not command_data.entity_id:
            raise_processing_error(
                service="essay_lifecycle_service",
                operation="handle_student_matching_command",
                message="Missing batch_id in student matching command",
                correlation_id=correlation_id,
            )
        batch_id = command_data.entity_id

        logger.info(
            "Processing student matching initiation command from BOS",
            extra={
                "batch_id": batch_id,
                "class_id": command_data.class_id,
                "essays_count": len(command_data.essays_to_process),
                "correlation_id": str(correlation_id),
            },
        )

        # START UNIT OF WORK
        async with self.session_factory() as session:
            async with session.begin():
                try:
                    # Create BatchStudentMatchingRequestedV1 event for NLP Service
                    batch_matching_request = BatchStudentMatchingRequestedV1(
                        event="batch.student.matching.requested",
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                        batch_id=batch_id,
                        essays_to_process=command_data.essays_to_process,
                        class_id=command_data.class_id,
                        course_code=command_data.course_code,
                    )

                    # Publish via outbox for reliable delivery
                    from common_core.event_enums import ProcessingEvent, topic_name
                    from common_core.events.envelope import EventEnvelope

                    # Get the correct topic name
                    topic = topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED)

                    envelope = EventEnvelope[BatchStudentMatchingRequestedV1](
                        event_type=topic,  # Use the correct topic name
                        source_service="essay_lifecycle_service",
                        correlation_id=correlation_id,
                        data=batch_matching_request,
                        metadata={},
                    )

                    await self.outbox_manager.publish_to_outbox(
                        aggregate_id=batch_id,
                        aggregate_type="batch",
                        event_type=envelope.event_type,
                        event_data=envelope,
                        topic=topic,
                        session=session,
                    )

                    logger.info(
                        f"Published BatchStudentMatchingRequestedV1 for batch {batch_id} to outbox",
                        extra={
                            "batch_id": batch_id,
                            "class_id": command_data.class_id,
                            "essays_count": len(command_data.essays_to_process),
                            "topic": topic,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    logger.info(
                        f"Successfully routed student matching command for batch {batch_id} to NLP Service",
                        extra={
                            "batch_id": batch_id,
                            "class_id": command_data.class_id,
                            "correlation_id": str(correlation_id),
                        },
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to process student matching command for batch {batch_id}",
                        extra={
                            "error": str(e),
                            "batch_id": batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )
                    raise_processing_error(
                        service="essay_lifecycle_service",
                        operation="handle_student_matching_command",
                        message=f"Failed to process student matching command: {str(e)}",
                        correlation_id=correlation_id,
                        batch_id=batch_id,
                        error_type=type(e).__name__,
                    )
                # Transaction commits here
