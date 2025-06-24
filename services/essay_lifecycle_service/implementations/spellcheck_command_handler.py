"""
Spellcheck command handler for Essay Lifecycle Service.

Handles spellcheck initiation commands from BOS, including state machine
transitions and service dispatch coordination.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1

from common_core.enums import Language
from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.essay_state_machine import (
    CMD_INITIATE_SPELLCHECK,
    EVT_SPELLCHECK_STARTED,
    EssayStateMachine,
)
from services.essay_lifecycle_service.protocols import (
    EssayRepositoryProtocol,
    EventPublisher,
    SpecializedServiceRequestDispatcher,
)

logger = create_service_logger("spellcheck_command_handler")


class SpellcheckCommandHandler:
    """Handles spellcheck initiation commands and state transitions."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        event_publisher: EventPublisher,
    ) -> None:
        self.repository = repository
        self.request_dispatcher = request_dispatcher
        self.event_publisher = event_publisher

    async def process_initiate_spellcheck_command(
        self,
        command_data: BatchServiceSpellcheckInitiateCommandDataV1,
        correlation_id: UUID | None = None,
    ) -> None:
        """Process spellcheck initiation command from Batch Orchestrator Service."""
        logger.info(
            "Processing spellcheck initiation command from BOS with State Machine",
            extra={
                "batch_id": command_data.entity_ref.entity_id,
                "essays_count": len(command_data.essays_to_process),
                "language": command_data.language,
                "correlation_id": str(correlation_id),
            },
        )

        # Process each essay with state machine
        successfully_transitioned_essays = []

        for essay_ref in command_data.essays_to_process:
            essay_id = essay_ref.essay_id
            try:
                essay_state_model = await self.repository.get_essay_state(essay_id)
                if essay_state_model is None:
                    logger.error(
                        f"Essay {essay_id} not found in state store for spellcheck command",
                        extra={
                            "batch_id": command_data.entity_ref.entity_id,
                            "correlation_id": str(correlation_id),
                        },
                    )
                    continue

                # Instantiate EssayStateMachine with current status
                essay_machine = EssayStateMachine(
                    essay_id=essay_id, initial_status=essay_state_model.current_status
                )

                # Attempt to trigger the transition for initiating spellcheck
                if essay_machine.trigger(CMD_INITIATE_SPELLCHECK):
                    # Persist the new state from the machine
                    await self.repository.update_essay_status_via_machine(
                        essay_id,
                        essay_machine.current_status,
                        {
                            "bos_command": "spellcheck_initiate",
                            "current_phase": "spellcheck",
                            "commanded_phases": list(
                                set(
                                    essay_state_model.processing_metadata.get(
                                        "commanded_phases", []
                                    )
                                    + ["spellcheck"]
                                )
                            ),
                        },
                    )

                    logger.info(
                        f"Essay {essay_id} transitioned to "
                        f"{essay_machine.current_status.value} via state machine.",
                        extra={
                            "batch_id": command_data.entity_ref.entity_id,
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
                            "batch_id": command_data.entity_ref.entity_id,
                            "correlation_id": str(correlation_id),
                        },
                    )
            except Exception as e:
                logger.error(
                    f"Failed to process essay {essay_id} with state machine",
                    extra={
                        "error": str(e),
                        "batch_id": command_data.entity_ref.entity_id,
                        "correlation_id": str(correlation_id),
                    },
                )

        # Dispatch requests to specialized services AFTER successful state transitions
        if successfully_transitioned_essays:
            try:
                # Convert string language to Language enum at boundary
                language_enum = Language(command_data.language)

                await self.request_dispatcher.dispatch_spellcheck_requests(
                    essays_to_process=successfully_transitioned_essays,
                    language=language_enum,
                    correlation_id=correlation_id,
                )

                logger.info(
                    "Successfully dispatched spellcheck requests for transitioned essays",
                    extra={
                        "batch_id": command_data.entity_ref.entity_id,
                        "transitioned_essays_count": len(successfully_transitioned_essays),
                        "correlation_id": str(correlation_id),
                    },
                )

                for essay_ref in successfully_transitioned_essays:
                    try:
                        essay_state_model = await self.repository.get_essay_state(
                            essay_ref.essay_id
                        )
                        if essay_state_model:
                            essay_machine = EssayStateMachine(
                                essay_id=essay_ref.essay_id,
                                initial_status=essay_state_model.current_status,
                            )

                            if essay_machine.trigger(EVT_SPELLCHECK_STARTED):
                                await self.repository.update_essay_status_via_machine(
                                    essay_ref.essay_id,
                                    essay_machine.current_status,
                                    {"spellcheck_phase": "started", "dispatch_completed": True},
                                )
                                logger.info(
                                    f"Essay {essay_ref.essay_id} transitioned to "
                                    f"{essay_machine.current_status.value} after dispatch",
                                    extra={
                                        "batch_id": command_data.entity_ref.entity_id,
                                        "correlation_id": str(correlation_id),
                                    },
                                )
                            else:
                                logger.warning(
                                    f"Failed to trigger EVT_SPELLCHECK_STARTED for "
                                    f"essay {essay_ref.essay_id}",
                                    extra={
                                        "current_status": essay_state_model.current_status.value,
                                        "correlation_id": str(correlation_id),
                                    },
                                )
                    except Exception as e:
                        logger.error(
                            f"Failed to trigger EVT_SPELLCHECK_STARTED "
                            f"for essay {essay_ref.essay_id}",
                            extra={
                                "error": str(e),
                                "correlation_id": str(correlation_id),
                            },
                        )

            except Exception as e:
                logger.error(
                    "Failed to dispatch spellcheck requests",
                    extra={
                        "error": str(e),
                        "batch_id": command_data.entity_ref.entity_id,
                        "correlation_id": str(correlation_id),
                    },
                )
        else:
            logger.warning(
                f"No essays successfully transitioned for spellcheck "
                f"for batch {command_data.entity_ref.entity_id}. Skipping dispatch.",
                extra={"correlation_id": str(correlation_id)},
            )
