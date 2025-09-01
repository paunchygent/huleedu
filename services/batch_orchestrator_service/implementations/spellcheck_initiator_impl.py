"""Spellcheck initiator implementation for batch processing."""

from __future__ import annotations

from uuid import UUID

from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1
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
    SpellcheckInitiatorProtocol,
)

from .utils import _infer_language_from_course_code

logger = create_service_logger("bos.spellcheck.initiator")


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
        correlation_id: UUID,
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
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="spellcheck_initiation",
                    field="phase_to_initiate",
                    message=(
                        f"SpellcheckInitiatorImpl received incorrect phase: {phase_to_initiate}"
                    ),
                    correlation_id=correlation_id,
                    expected_phase="SPELLCHECK",
                    received_phase=phase_to_initiate.value,
                )

            # Validate required data
            if not essays_for_processing:
                raise_validation_error(
                    service="batch_orchestrator_service",
                    operation="spellcheck_initiation",
                    field="essays_for_processing",
                    message=f"No essays provided for spellcheck initiation in batch {batch_id}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                )

            # Get language from course code
            language = _infer_language_from_course_code(batch_context.course_code).value

            # Construct spellcheck command with primitive parameters
            # EntityReference removed - using primitive parameters

            spellcheck_command = BatchServiceSpellcheckInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
                essays_to_process=essays_for_processing,
                language=language,
            )

            # Create EventEnvelope for spellcheck command
            from huleedu_service_libs.observability import inject_trace_context

            command_envelope = EventEnvelope[BatchServiceSpellcheckInitiateCommandDataV1](
                event_type=topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
                source_service="batch-orchestrator-service",
                correlation_id=correlation_id,
                data=spellcheck_command,
                metadata={
                    "user_id": batch_context.user_id,  # Identity from batch context
                    "org_id": batch_context.org_id,  # Org from batch context
                },
            )

            # Inject current trace context into the envelope metadata
            if command_envelope.metadata is not None:
                inject_trace_context(command_envelope.metadata)

            # Publish spellcheck command
            await self.event_publisher.publish_batch_event(command_envelope, key=batch_id)

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
