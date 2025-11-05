"""NLP initiator implementation for batch processing.

Publishes NLP processing commands to Kafka topics consumed by the NLP Service.
Supports both Phase 1 (student matching) and Phase 2 (text analysis) operations.
"""

from __future__ import annotations

from uuid import UUID

from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV2
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
    NLPInitiatorProtocol,
)

from .utils import _infer_language_from_course_code

logger = create_service_logger("bos.nlp.initiator")


class NLPInitiatorImpl(NLPInitiatorProtocol):
    """
    Default implementation for initiating NLP operations.

    Publishes NLP commands to Kafka topics for consumption by the NLP Service.
    Handles both Phase 1 student matching and Phase 2 text analysis workflows.
    """

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
        Initiate NLP phase for a batch with the given context.

        This implements the standardized PipelinePhaseInitiatorProtocol interface
        for NLP operations.

        TODO: The published command will be queued until NLP Service is implemented.
        """
        try:
            logger.info(
                f"Initiating NLP processing for batch {batch_id}",
                extra={"correlation_id": str(correlation_id)},
            )

            # Validate that this is the correct phase
            if phase_to_initiate != PhaseName.NLP:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="nlp_initiation",
                    field="phase_to_initiate",
                    message=f"NLPInitiatorImpl received incorrect phase: {phase_to_initiate}",
                    correlation_id=correlation_id,
                    expected_phase="NLP",
                    received_phase=phase_to_initiate.value,
                )

            # Validate required data
            if not essays_for_processing:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="nlp_initiation",
                    field="essays_for_processing",
                    message=f"No essays provided for NLP initiation in batch {batch_id}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                )

            # Get language from course code
            language = _infer_language_from_course_code(batch_context.course_code).value

            # Construct NLP command
            nlp_command = BatchServiceNLPInitiateCommandDataV2(
                event_name=ProcessingEvent.BATCH_NLP_INITIATE_COMMAND_V2,
                entity_id=batch_id,
                entity_type="batch",
                essays_to_process=essays_for_processing,
                language=language,
                student_prompt_ref=batch_context.student_prompt_ref,
            )

            # Create EventEnvelope for NLP command
            command_envelope = EventEnvelope[BatchServiceNLPInitiateCommandDataV2](
                event_type=topic_name(ProcessingEvent.BATCH_NLP_INITIATE_COMMAND_V2),
                source_service="batch-orchestrator-service",
                correlation_id=correlation_id,
                data=nlp_command,
                metadata={
                    "user_id": batch_context.user_id,  # Identity from batch context
                    "org_id": batch_context.org_id,  # Org from batch context
                },
            )

            # Publish NLP command
            await self.event_publisher.publish_batch_event(command_envelope)

            logger.info(
                f"Published NLP initiate command for batch {batch_id}, "
                f"event_id {command_envelope.event_id}",
                extra={"correlation_id": str(correlation_id)},
            )

        except Exception as e:
            logger.error(
                f"Error initiating NLP for batch {batch_id}: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise
