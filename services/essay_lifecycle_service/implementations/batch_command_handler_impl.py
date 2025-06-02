"""
Batch command handler implementation for Essay Lifecycle Service.

Implements BatchCommandHandler protocol for processing batch commands from BOS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.batch_service_models import (
        BatchServiceAIFeedbackInitiateCommandDataV1,
        BatchServiceCJAssessmentInitiateCommandDataV1,
        BatchServiceNLPInitiateCommandDataV1,
        BatchServiceSpellcheckInitiateCommandDataV1,
    )

from huleedu_service_libs.logging_utils import create_service_logger

from protocols import (
    BatchCommandHandler,
    EssayStateStore,
    EventPublisher,
    SpecializedServiceRequestDispatcher,
)


class DefaultBatchCommandHandler(BatchCommandHandler):
    """Default implementation of BatchCommandHandler protocol."""

    def __init__(
        self,
        state_store: EssayStateStore,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
    ) -> None:
        self.state_store = state_store
        self.request_dispatcher = request_dispatcher
        self.event_publisher = event_publisher

    async def process_initiate_spellcheck_command(
        self,
        command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID | None = None,
    ) -> None:
        """Process spellcheck initiation command from Batch Orchestrator Service."""
        logger = create_service_logger("batch_command_handler")

        batch_id = command_data.entity_ref.entity_id
        essays_to_process = command_data.essays_to_process
        language = command_data.language

        logger.info(
            "Processing spellcheck initiation command from BOS",
            extra={
                "batch_id": batch_id,
                "essays_count": len(essays_to_process),
                "language": language,
                "correlation_id": str(correlation_id),
            },
        )

        # Step 1: Update essay states to AWAITING_SPELLCHECK
        from common_core.enums import EssayStatus

        for essay_ref in essays_to_process:
            essay_id = essay_ref.essay_id
            try:
                # Update the essay state to AWAITING_SPELLCHECK
                essay_state = await self.state_store.get_essay_state(essay_id)
                if essay_state is None:
                    logger.error(
                        f"Essay {essay_id} not found in state store",
                        extra={"batch_id": batch_id, "correlation_id": str(correlation_id)},
                    )
                    continue

                # Update essay status
                await self.state_store.update_essay_status(
                    essay_id, EssayStatus.AWAITING_SPELLCHECK
                )

                logger.info(
                    f"Updated essay {essay_id} status to AWAITING_SPELLCHECK",
                    extra={"batch_id": batch_id, "correlation_id": str(correlation_id)},
                )

            except Exception as e:
                logger.error(
                    f"Failed to update essay {essay_id} status",
                    extra={
                        "error": str(e),
                        "batch_id": batch_id,
                        "correlation_id": str(correlation_id),
                    },
                )

        # Step 2: Dispatch requests to Spell Checker Service
        try:
            await self.request_dispatcher.dispatch_spellcheck_requests(
                essays_to_process=essays_to_process,
                language=language,
                correlation_id=correlation_id,
            )

            logger.info(
                "Successfully dispatched spellcheck requests",
                extra={
                    "batch_id": batch_id,
                    "essays_count": len(essays_to_process),
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to dispatch spellcheck requests",
                extra={
                    "error": str(e),
                    "batch_id": batch_id,
                    "correlation_id": str(correlation_id),
                },
            )

    async def process_initiate_nlp_command(
        self, command_data: BatchServiceNLPInitiateCommandDataV1, correlation_id: UUID | None = None
    ) -> None:
        """Process NLP initiation command from Batch Orchestrator Service."""
        # TODO: Implement when NLP Service is available
        logger = create_service_logger("batch_command_handler")
        logger.info("Received NLP initiation command (STUB)")

    async def process_initiate_ai_feedback_command(
        self,
        command_data: BatchServiceAIFeedbackInitiateCommandDataV1,
        correlation_id: UUID | None = None,
    ) -> None:
        """Process AI feedback initiation command from Batch Orchestrator Service."""
        # TODO: Implement when AI Feedback Service is available
        logger = create_service_logger("batch_command_handler")
        logger.info("Received AI feedback initiation command (STUB)")

    async def process_initiate_cj_assessment_command(
        self,
        command_data: BatchServiceCJAssessmentInitiateCommandDataV1,
        correlation_id: UUID | None = None,
    ) -> None:
        """Process CJ assessment initiation command from Batch Orchestrator Service."""
        # TODO: Implement when CJ Assessment Service is available
        logger = create_service_logger("batch_command_handler")
        logger.info("Received CJ assessment initiation command (STUB)")
