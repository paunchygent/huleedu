"""Student matching initiator implementation for Phase 1 Student Matching Integration."""

from __future__ import annotations

from uuid import UUID

from common_core.batch_service_models import BatchServiceStudentMatchingInitiateCommandDataV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.error_handling import (
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    PipelinePhaseInitiatorProtocol,
)

logger = create_service_logger("bos.student_matching.initiator")


class StudentMatchingInitiatorImpl(PipelinePhaseInitiatorProtocol):
    """Implementation for initiating Phase 1 student matching operations."""

    def __init__(
        self,
        event_publisher: BatchEventPublisherProtocol,
    ) -> None:
        self.event_publisher = event_publisher

    async def initiate_phase(
        self,
        batch_id: str,
        phase_to_initiate: PhaseName,
        correlation_id: UUID,
        essays_for_processing: list[EssayProcessingInputRefV1],
        batch_context: BatchRegistrationRequestV1,
    ) -> None:
        """
        Initiate Phase 1 student matching for REGULAR batches.

        PHASE 1 STUDENT MATCHING INITIATION:
        ===================================
        1. Validate this is the correct phase (STUDENT_MATCHING)
        2. Validate batch is REGULAR type (has class_id)
        3. Create BatchServiceStudentMatchingInitiateCommand event
        4. Publish command to ELS for processing
        """
        try:
            logger.info(
                f"Initiating Phase 1 student matching for batch {batch_id}",
                extra={"correlation_id": str(correlation_id)},
            )

            # Validate that this is the correct phase
            if phase_to_initiate != PhaseName.STUDENT_MATCHING:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="student_matching_initiation",
                    field="phase_to_initiate",
                    message=(
                        f"StudentMatchingInitiatorImpl received incorrect phase: "
                        f"{phase_to_initiate}"
                    ),
                    correlation_id=correlation_id,
                    expected_phase="STUDENT_MATCHING",
                    received_phase=phase_to_initiate.value,
                )

            # Validate batch is REGULAR type (has class_id for student matching)
            if batch_context.class_id is None:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="student_matching_initiation",
                    field="class_id",
                    message=(
                        f"Student matching initiated for GUEST batch {batch_id}. "
                        "Student matching requires REGULAR batch with class_id."
                    ),
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    batch_type="GUEST",
                )

            # Validate required essay data
            if not essays_for_processing:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="student_matching_initiation",
                    field="essays_for_processing",
                    message=(
                        f"No essays provided for student matching initiation in batch {batch_id}"
                    ),
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                )

            # Create student matching command data
            command_data = BatchServiceStudentMatchingInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND,
                entity_id=batch_id,
                entity_type="batch",
                essays_to_process=essays_for_processing,
                class_id=batch_context.class_id,
                course_code=batch_context.course_code,
            )

            logger.info(
                f"Created student matching command for batch {batch_id} with "
                f"class_id {batch_context.class_id} and {len(essays_for_processing)} essays",
                extra={"correlation_id": str(correlation_id)},
            )

            # Create event envelope with the full topic name as event_type
            envelope = EventEnvelope[BatchServiceStudentMatchingInitiateCommandDataV1](
                event_type=topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND),
                source_service="batch_orchestrator_service",
                correlation_id=correlation_id,
                data=command_data,
                metadata={
                    "user_id": batch_context.user_id,  # Identity from batch context
                    "org_id": batch_context.org_id,  # Org from batch context
                },
            )

            # Determine target topic for ELS
            topic = topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND)

            # Publish command event to ELS using outbox pattern
            await self.event_publisher.publish_batch_event(
                event_envelope=envelope,
                key=batch_id,  # Use batch_id as the partition key
            )

            logger.info(
                f"Successfully published student matching initiate command for batch {batch_id} "
                f"to topic {topic}",
                extra={"correlation_id": str(correlation_id)},
            )

        except Exception as e:
            logger.error(
                f"Failed to initiate student matching for batch {batch_id}: {e}",
                extra={"correlation_id": str(correlation_id)},
            )
            raise
