"""CJ Assessment initiator implementation for batch processing."""

from __future__ import annotations

from uuid import UUID

from api_models import BatchRegistrationRequestV1
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    CJAssessmentInitiatorProtocol,
    DataValidationError,
)

from common_core.batch_service_models import BatchServiceCJAssessmentInitiateCommandDataV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName

from .utils import _infer_language_from_course_code

logger = create_service_logger("bos.cj.initiator")


class DefaultCJAssessmentInitiator(CJAssessmentInitiatorProtocol):
    """Default implementation for initiating CJ assessment operations."""

    def __init__(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> None:
        self.event_publisher = event_publisher
        self.batch_repo = batch_repo

    async def initiate_phase(
        self,
        batch_id: str,
        phase_to_initiate: PhaseName,
        correlation_id: UUID | None,
        essays_for_processing: list[EssayProcessingInputRefV1],
        batch_context: BatchRegistrationRequestV1,
    ) -> None:
        """
        Initiate CJ assessment phase for a batch with the given context.

        This implements the standardized PipelinePhaseInitiatorProtocol interface
        for CJ assessment operations.
        """
        try:
            logger.info(
                f"Initiating CJ assessment for batch {batch_id}",
                extra={"correlation_id": str(correlation_id)},
            )

            # Validate that this is the correct phase
            if phase_to_initiate != PhaseName.CJ_ASSESSMENT:
                raise DataValidationError(
                    f"DefaultCJAssessmentInitiator received incorrect phase: {phase_to_initiate}",
                )

            # Validate required data
            if not essays_for_processing:
                raise DataValidationError(
                    f"No essays provided for CJ assessment initiation in batch {batch_id}",
                )

            # Get language from course code
            language = _infer_language_from_course_code(batch_context.course_code).value

            # Construct CJ assessment command
            batch_entity_ref = EntityReference(entity_id=batch_id, entity_type="batch")

            cj_command = BatchServiceCJAssessmentInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
                entity_ref=batch_entity_ref,
                essays_to_process=essays_for_processing,
                language=language,
                # Orchestration context (from BOS lean registration)
                course_code=batch_context.course_code,
                essay_instructions=batch_context.essay_instructions,
                # Educational context (TODO: Get from enhanced BatchEssaysReady event)
                # For now, using GUEST class type until Class Management Service integration
                class_type="GUEST",
            )

            # Create EventEnvelope for CJ command
            command_envelope = EventEnvelope[BatchServiceCJAssessmentInitiateCommandDataV1](
                event_type=topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND),
                source_service="batch-orchestrator-service",
                correlation_id=correlation_id,
                data=cj_command,
            )

            # Publish CJ assessment command
            await self.event_publisher.publish_batch_event(command_envelope)

            logger.info(
                f"Published CJ assessment initiate command for batch {batch_id}, "
                f"event_id {command_envelope.event_id}",
                extra={"correlation_id": str(correlation_id)},
            )

        except Exception as e:
            logger.error(
                f"Error initiating CJ assessment for batch {batch_id}: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise
