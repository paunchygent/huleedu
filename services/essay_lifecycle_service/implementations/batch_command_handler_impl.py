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

from services.essay_lifecycle_service.essay_state_machine import (
    CMD_INITIATE_SPELLCHECK,
    EssayStateMachine,
)
from services.essay_lifecycle_service.protocols import (
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
            "Processing spellcheck initiation command from BOS with State Machine",
            extra={
                "batch_id": batch_id,
                "essays_count": len(essays_to_process),
                "language": language,
                "correlation_id": str(correlation_id),
            },
        )

        # Process each essay with state machine
        successfully_transitioned_essays = []

        for essay_ref in essays_to_process:
            essay_id = essay_ref.essay_id
            try:
                essay_state_model = await self.state_store.get_essay_state(essay_id)
                if essay_state_model is None:
                    logger.error(
                        f"Essay {essay_id} not found in state store for spellcheck command",
                        extra={
                            "batch_id": batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )
                    continue

                # Instantiate EssayStateMachine with current status
                essay_machine = EssayStateMachine(
                    essay_id=essay_id,
                    initial_status=essay_state_model.current_status
                )

                # Attempt to trigger the transition for initiating spellcheck
                if essay_machine.trigger(CMD_INITIATE_SPELLCHECK):
                    # Persist the new state from the machine
                    await self.state_store.update_essay_status_via_machine(
                        essay_id,
                        essay_machine.current_status,
                        {
                            "bos_command": "spellcheck_initiate",
                            "current_phase": "spellcheck",
                            "commanded_phases": list(set(
                                essay_state_model.processing_metadata.get(
                                    "commanded_phases", []
                                ) + ["spellcheck"]
                            ))
                        }
                    )

                    logger.info(
                        f"Essay {essay_id} transitioned to "
                        f"{essay_machine.current_status.value} via state machine.",
                        extra={
                            "batch_id": batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Add to successfully transitioned list for dispatch
                    successfully_transitioned_essays.append(essay_ref)
                else:
                    logger.warning(
                        f"State machine trigger '{CMD_INITIATE_SPELLCHECK}' failed "
                        f"for essay {essay_id} from status "
                        f"{essay_state_model.current_status.value}.",
                        extra={
                            "batch_id": batch_id,
                            "correlation_id": str(correlation_id),
                        },
                    )
            except Exception as e:
                logger.error(
                    f"Failed to process essay {essay_id} with state machine",
                    extra={
                        "error": str(e),
                        "batch_id": batch_id,
                        "correlation_id": str(correlation_id),
                    },
                )

        # Dispatch requests to specialized services AFTER successful state transitions
        if successfully_transitioned_essays:
            try:
                await self.request_dispatcher.dispatch_spellcheck_requests(
                    essays_to_process=successfully_transitioned_essays,
                    language=language,
                    correlation_id=correlation_id,
                )

                logger.info(
                    "Successfully dispatched spellcheck requests for transitioned essays",
                    extra={
                        "batch_id": batch_id,
                        "transitioned_essays_count": len(
                            successfully_transitioned_essays
                        ),
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
        else:
            logger.warning(
                f"No essays successfully transitioned to AWAITING_SPELLCHECK "
                f"for batch {batch_id}. Skipping dispatch.",
                extra={"correlation_id": str(correlation_id)}
            )

    async def process_initiate_nlp_command(
        self,
        command_data: BatchServiceNLPInitiateCommandDataV1,
        correlation_id: UUID | None = None
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
