"""CJ Assessment initiator implementation for batch processing."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from api_models import BatchRegistrationRequestV1
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
)

from common_core.batch_service_models import BatchServiceCJAssessmentInitiateCommandDataV1
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, EssayProcessingInputRefV1

logger = create_service_logger("bos.cj.initiator")


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
    elif course_code_upper.startswith("NO"):
        return "no"  # Norwegian
    elif course_code_upper.startswith("DA"):
        return "da"  # Danish
    else:
        # Default to English if course code is unrecognized
        logger.warning(f"Unknown course code '{course_code}', defaulting to English")
        return "en"


class DefaultCJAssessmentInitiator:
    """Default implementation for initiating CJ assessment operations."""

    def __init__(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> None:
        self.event_publisher = event_publisher
        self.batch_repo = batch_repo

    async def initiate_cj_assessment(
        self,
        batch_id: str,
        batch_context: BatchRegistrationRequestV1,
        correlation_id: str,
        essays_to_process: list[EssayProcessingInputRefV1] | None = None,
    ) -> None:
        """
        Initiate CJ assessment for a batch with the given context.

        This implements the core logic for sub-task 2.1.2.
        """
        try:
            logger.info(f"Initiating CJ assessment for batch {batch_id}")

            # Get language from course code
            language = _infer_language_from_course_code(batch_context.course_code)

            # Construct CJ assessment command
            batch_entity_ref = EntityReference(entity_id=batch_id, entity_type="batch")

            # Use provided essays or empty list (TODO: coordinate with ELS for actual data)
            if essays_to_process is None:
                essays_to_process = []
                logger.warning(
                    f"No essays_to_process provided for CJ assessment batch {batch_id}. "
                    f"This needs coordination with ELS implementation."
                )

            cj_command = BatchServiceCJAssessmentInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND,
                entity_ref=batch_entity_ref,
                essays_to_process=essays_to_process,
                language=language,
                course_code=batch_context.course_code,
                class_designation=batch_context.class_designation,
                essay_instructions=batch_context.essay_instructions,
            )

            # Create EventEnvelope for CJ command
            command_envelope = EventEnvelope[BatchServiceCJAssessmentInitiateCommandDataV1](
                event_type=topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND),
                source_service="batch-orchestrator-service",
                correlation_id=UUID(correlation_id) if correlation_id else None,
                data=cj_command,
            )

            # Publish CJ assessment command
            await self.event_publisher.publish_batch_event(command_envelope)

            # Update pipeline state to mark CJ assessment as initiated
            await self._update_cj_assessment_status(batch_id, "DISPATCH_INITIATED")

            logger.info(
                f"Published CJ assessment initiate command for batch {batch_id}, "
                f"event_id {command_envelope.event_id}",
                extra={"correlation_id": str(correlation_id)},
            )

        except Exception as e:
            logger.error(f"Error initiating CJ assessment for batch {batch_id}: {e}", exc_info=True)
            raise

    async def can_initiate_cj_assessment(
        self,
        batch_context: BatchRegistrationRequestV1,
        current_pipeline_state: dict,
    ) -> bool:
        """Check if CJ assessment can be initiated for the given batch context."""
        # Check if CJ assessment is enabled in batch context
        if not batch_context.enable_cj_assessment:
            return False

        # Check if CJ assessment hasn't been initiated yet
        cj_status = self._get_cj_status(current_pipeline_state)
        return cj_status not in ["DISPATCH_INITIATED", "IN_PROGRESS", "COMPLETED", "FAILED"]

    async def _update_cj_assessment_status(self, batch_id: str, status: str) -> None:
        """Update CJ assessment status in pipeline state."""
        current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
        if not current_pipeline_state:
            logger.error(f"No pipeline state found for batch {batch_id}")
            return

        # Handle both dict and ProcessingPipelineState object cases
        if hasattr(current_pipeline_state, "model_dump"):
            updated_pipeline_state = current_pipeline_state.model_dump()
        else:
            updated_pipeline_state = current_pipeline_state.copy()

        updated_pipeline_state.update({
            "cj_assessment_status": status,
            "cj_assessment_initiated_at": datetime.now(timezone.utc).isoformat(),
        })
        await self.batch_repo.save_processing_pipeline_state(batch_id, updated_pipeline_state)

    def _get_cj_status(self, pipeline_state: dict) -> str | None:
        """Extract CJ assessment status from pipeline state."""
        if hasattr(pipeline_state, "cj_assessment"):  # Pydantic object
            cj_obj = getattr(pipeline_state, "cj_assessment")
            return getattr(cj_obj, "status", None) if cj_obj else None
        else:  # Dictionary
            return pipeline_state.get("cj_assessment_status")
