"""
BatchEssaysReady message handler implementation for Batch Orchestrator Service.

Handles BatchEssaysReady events from ELS to initiate pipeline processing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from protocols import BatchEventPublisherProtocol, BatchRepositoryProtocol

from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference

logger = create_service_logger("bos.handlers.batch_essays_ready")


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


class BatchEssaysReadyHandler:
    """Handler for BatchEssaysReady events from ELS."""

    def __init__(
        self,
        event_publisher: BatchEventPublisherProtocol,
        batch_repo: BatchRepositoryProtocol,
    ) -> None:
        self.event_publisher = event_publisher
        self.batch_repo = batch_repo

    async def handle_batch_essays_ready(self, msg: Any) -> None:
        """
        Handle a BatchEssaysReady event to initiate the first pipeline phase (spellcheck).

        ARCHITECTURE IMPLEMENTATION:
        ===========================
        This implementation uses the new BatchEssaysReady structure with ready_essays
        that contains actual essay_id and text_storage_id mappings from ELS:

        1. File Service processes uploaded files and stores content via Content Service
        2. File Service emits EssayContentProvisionedV1 events containing text_storage_id values
        3. ELS receives and assigns internal essay_ids to provisioned content
        4. ELS emits BatchEssaysReady with ready_essays containing EssayProcessingInputRefV1 objects
        5. BOS uses the actual text_storage_id values to create
           BatchServiceSpellcheckInitiateCommandDataV1

        The BatchEssaysReady event now provides the necessary data mapping directly,
        eliminating the need for additional queries or mock values.
        """
        try:
            # Deserialize the message
            message_data = json.loads(msg.value.decode("utf-8"))
            envelope = EventEnvelope[BatchEssaysReady](**message_data)

            batch_essays_ready_data = envelope.data
            batch_id = batch_essays_ready_data.batch_id

            logger.info(
                f"Received BatchEssaysReady for batch {batch_id}",
                extra={"correlation_id": str(envelope.correlation_id)},
            )

            # 1. Idempotency Check
            current_pipeline_state = await self.batch_repo.get_processing_pipeline_state(batch_id)
            if current_pipeline_state:
                # Handle both dict and ProcessingPipelineState object cases
                if hasattr(current_pipeline_state, "spellcheck"):  # Pydantic object
                    spellcheck_obj = current_pipeline_state.spellcheck
                    spellcheck_status = (
                        spellcheck_obj.status.value
                        if spellcheck_obj and spellcheck_obj.status
                        else None
                    )
                else:  # Dictionary
                    spellcheck_status = current_pipeline_state.get("spellcheck_status")

                if spellcheck_status in [
                    "DISPATCH_INITIATED",
                    "IN_PROGRESS",
                    "COMPLETED",
                    "FAILED",
                ]:
                    logger.info(
                        f"Spellcheck already initiated for batch {batch_id}, skipping",
                        extra={"current_status": spellcheck_status},
                    )
                    return

            # 2. Retrieve stored batch context
            batch_context = await self.batch_repo.get_batch_context(batch_id)
            if not batch_context:
                logger.error(f"No batch context found for batch {batch_id}")
                return

            # 3. Infer language from course code
            language = _infer_language_from_course_code(batch_context.course_code)
            logger.info(
                f"Inferred language '{language}' from course code '{batch_context.course_code}'"
            )

            # 4. Construct spellcheck initiate command
            batch_entity_ref = EntityReference(entity_id=batch_id, entity_type="batch")

            # Extract essays_to_process from BatchEssaysReady.ready_essays
            # This contains the actual essay_id and text_storage_id mappings from ELS
            essays_to_process = batch_essays_ready_data.ready_essays

            # Validate that we received essay data
            if not essays_to_process:
                logger.error(f"BatchEssaysReady for batch {batch_id} contains no ready_essays")
                return

            logger.info(f"Processing {len(essays_to_process)} ready essays for batch {batch_id}")

            spellcheck_command = BatchServiceSpellcheckInitiateCommandDataV1(
                event_name=ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND,
                entity_ref=batch_entity_ref,
                essays_to_process=essays_to_process,
                language=language,
            )

            # 5. Create EventEnvelope for command
            command_envelope = EventEnvelope[BatchServiceSpellcheckInitiateCommandDataV1](
                event_type=topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
                source_service="batch-orchestrator-service",
                correlation_id=envelope.correlation_id,  # Maintain correlation
                data=spellcheck_command,
            )

            # 6. Publish command
            await self.event_publisher.publish_batch_event(command_envelope)
            logger.info(
                f"Published spellcheck initiate command for batch {batch_id}, "
                f"event_id {command_envelope.event_id}",
                extra={"correlation_id": str(envelope.correlation_id)},
            )

            # 7. Update pipeline state
            # Handle both dict and ProcessingPipelineState object cases
            if current_pipeline_state and hasattr(
                current_pipeline_state, "model_dump"
            ):  # Pydantic object
                updated_pipeline_state = current_pipeline_state.model_dump()
            else:  # Dictionary or None
                updated_pipeline_state = current_pipeline_state or {}

            updated_pipeline_state.update(
                {
                    "spellcheck_status": "DISPATCH_INITIATED",
                    "spellcheck_initiated_at": datetime.now(timezone.utc).isoformat(),
                    "language": language,
                }
            )
            await self.batch_repo.save_processing_pipeline_state(batch_id, updated_pipeline_state)

            logger.info(f"Successfully initiated spellcheck pipeline for batch {batch_id}")

        except Exception as e:
            logger.error(f"Error handling BatchEssaysReady message: {e}", exc_info=True)
            raise
