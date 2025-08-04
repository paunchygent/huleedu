"""CJ Assessment initiator implementation for batch processing."""

from __future__ import annotations

from uuid import UUID

from common_core.batch_service_models import BatchServiceCJAssessmentInitiateCommandDataV1
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
    BatchRepositoryProtocol,
    CJAssessmentInitiatorProtocol,
)

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
        correlation_id: UUID,
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
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="cj_assessment_initiation",
                    field="phase_to_initiate",
                    message=(
                        f"DefaultCJAssessmentInitiator received incorrect phase: "
                        f"{phase_to_initiate}"
                    ),
                    correlation_id=correlation_id,
                    expected_phase="CJ_ASSESSMENT",
                    received_phase=phase_to_initiate.value,
                )

            # Validate required data
            if not essays_for_processing:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="cj_assessment_initiation",
                    field="essays_for_processing",
                    message=f"No essays provided for CJ assessment initiation in batch {batch_id}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                )

            # Get language from course code
            language = _infer_language_from_course_code(batch_context.course_code).value

            # Construct CJ assessment command
            cj_command = BatchServiceCJAssessmentInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
                entity_id=batch_id,
                entity_type="batch",
                essays_to_process=essays_for_processing,
                language=language,
                # Orchestration context (from BOS lean registration)
                course_code=batch_context.course_code,
                essay_instructions=batch_context.essay_instructions,
                # Educational context - determine from class_id presence
                # Services needing teacher context should query CMS directly
                class_type="REGULAR" if batch_context.class_id else "GUEST",
            )

            # Create EventEnvelope for CJ command
            from huleedu_service_libs.observability import inject_trace_context

            command_envelope = EventEnvelope[BatchServiceCJAssessmentInitiateCommandDataV1](
                event_type=topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND),
                source_service="batch-orchestrator-service",
                correlation_id=correlation_id,
                data=cj_command,
                metadata={},
            )

            # Inject current trace context into the envelope metadata
            if command_envelope.metadata is not None:
                inject_trace_context(command_envelope.metadata)

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
