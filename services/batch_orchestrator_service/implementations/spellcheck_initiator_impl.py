"""Spellcheck initiator implementation for batch processing."""

from __future__ import annotations

from uuid import UUID

from api_models import BatchRegistrationRequestV1
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    BatchEventPublisherProtocol,
    DataValidationError,
    SpellcheckInitiatorProtocol,
)

from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName

logger = create_service_logger("bos.spellcheck.initiator")


def _infer_language_from_course_code(course_code: str) -> str:
    """
    Infer language from course code for pipeline processing.

    Args:
        course_code: Course code (e.g., "SV1", "ENG5")

    Returns:
        Language code (e.g., "sv", "en")
    """
    # Simple mapping logic - can be enhanced as needed
    course_code_upper = course_code.upper()

    if course_code_upper.startswith("SV"):
        return "sv"  # Swedish
    elif course_code_upper.startswith("ENG"):
        return "en"  # English
    else:
        # Default to English if course code is unrecognized
        logger.warning(f"Unknown course code '{course_code}', defaulting to English")
        return "en"


class SpellcheckInitiatorImpl(SpellcheckInitiatorProtocol):
    """Default implementation for initiating spellcheck operations."""

    def __init__(
        self,
        event_publisher: BatchEventPublisherProtocol,
    ) -> None:
        self.event_publisher = event_publisher

    async def initiate_phase(
        self,
        batch_id: str,
        phase_to_initiate: PhaseName,
        correlation_id: UUID | None,
        essays_for_processing: list[EssayProcessingInputRefV1],
        batch_context: BatchRegistrationRequestV1,
    ) -> None:
        """
        Initiate spellcheck phase for a batch with the given context.

        This implements the standardized PipelinePhaseInitiatorProtocol interface
        for spellcheck operations.
        """
        try:
            logger.info(
                f"Initiating spellcheck for batch {batch_id}",
                extra={"correlation_id": str(correlation_id)},
            )

            # Validate that this is the correct phase
            if phase_to_initiate != PhaseName.SPELLCHECK:
                raise DataValidationError(
                    f"SpellcheckInitiatorImpl received incorrect phase: {phase_to_initiate}"
                )

            # Validate required data
            if not essays_for_processing:
                raise DataValidationError(
                    f"No essays provided for spellcheck initiation in batch {batch_id}"
                )

            # Get language from course code
            language = _infer_language_from_course_code(batch_context.course_code)

            # Construct spellcheck command
            batch_entity_ref = EntityReference(entity_id=batch_id, entity_type="batch")

            spellcheck_command = BatchServiceSpellcheckInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
                entity_ref=batch_entity_ref,
                essays_to_process=essays_for_processing,
                language=language,
            )

            # Create EventEnvelope for spellcheck command
            command_envelope = EventEnvelope[BatchServiceSpellcheckInitiateCommandDataV1](
                event_type=topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
                source_service="batch-orchestrator-service",
                correlation_id=correlation_id,
                data=spellcheck_command,
            )

            # Publish spellcheck command
            await self.event_publisher.publish_batch_event(command_envelope)

            logger.info(
                f"Published spellcheck initiate command for batch {batch_id}, "
                f"event_id {command_envelope.event_id}",
                extra={"correlation_id": str(correlation_id)},
            )

        except Exception as e:
            logger.error(
                f"Error initiating spellcheck for batch {batch_id}: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise
