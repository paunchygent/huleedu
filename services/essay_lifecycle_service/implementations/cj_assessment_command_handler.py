"""
CJ Assessment command handler for Essay Lifecycle Service.

Handles CJ assessment initiation commands from BOS, including state machine
transitions and service dispatch coordination.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.batch_service_models import BatchServiceCJAssessmentInitiateCommandDataV1
    from sqlalchemy.ext.asyncio import async_sessionmaker

from common_core.domain_enums import Language
from huleedu_service_libs.logging_utils import create_service_logger

from services.essay_lifecycle_service.constants import MetadataKey
from services.essay_lifecycle_service.essay_state_machine import (
    CMD_INITIATE_CJ_ASSESSMENT,
    EVT_CJ_ASSESSMENT_STARTED,
    EssayStateMachine,
)
from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    EssayRepositoryProtocol,
    SpecializedServiceRequestDispatcher,
)

logger = create_service_logger("cj_assessment_command_handler")


class CJAssessmentCommandHandler:
    """Handles CJ assessment initiation commands and state transitions."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        request_dispatcher: SpecializedServiceRequestDispatcher,
        batch_tracker: BatchEssayTracker,
        session_factory: async_sessionmaker,
    ) -> None:
        self.repository = repository
        self.request_dispatcher = request_dispatcher
        self.batch_tracker = batch_tracker
        self.session_factory = session_factory

    async def process_initiate_cj_assessment_command(
        self,
        command_data: BatchServiceCJAssessmentInitiateCommandDataV1,
        correlation_id: UUID,
        envelope_metadata: dict | None = None,
    ) -> None:
        """Process CJ assessment initiation command from Batch Orchestrator Service."""
        logger.info(
            "Processing CJ assessment initiation command from BOS",
            extra={
                "batch_id": command_data.entity_id,
                "essays_count": len(command_data.essays_to_process),
                "language": command_data.language,
                "correlation_id": str(correlation_id),
            },
        )

        successfully_transitioned_essays = []

        # START UNIT OF WORK
        async with self.session_factory() as session:
            async with session.begin():
                # Process each essay with state machine transitions
                for essay_ref in command_data.essays_to_process:
                    essay_id = essay_ref.essay_id

                    try:
                        # Get current essay state within the active transaction
                        essay_state_model = await self.repository.get_essay_state(essay_id, session)
                        if not essay_state_model:
                            logger.warning(
                                f"Essay {essay_id} not found for CJ assessment command",
                                extra={
                                    "batch_id": command_data.entity_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            continue

                        # Instantiate EssayStateMachine with current status
                        essay_machine = EssayStateMachine(
                            essay_id=essay_id, initial_status=essay_state_model.current_status
                        )

                        # Log current state before transition attempt
                        logger.info(
                            f"Attempting CJ assessment state transition for essay {essay_id}",
                            extra={
                                "essay_id": essay_id,
                                "current_status": essay_state_model.current_status.value,
                                "valid_triggers": essay_machine.get_valid_triggers(),
                                "batch_id": command_data.entity_id,
                                "correlation_id": str(correlation_id),
                            },
                        )

                        # Attempt to trigger the transition for initiating CJ assessment
                        if essay_machine.trigger_event(CMD_INITIATE_CJ_ASSESSMENT):
                            # Persist the new state from the machine
                            await self.repository.update_essay_status_via_machine(
                                essay_id,
                                essay_machine.current_status,
                                {
                                    "bos_command": "cj_assessment_initiate",
                                    MetadataKey.CURRENT_PHASE: "cj_assessment",
                                    MetadataKey.COMMANDED_PHASES: list(
                                        set(
                                            essay_state_model.processing_metadata.get(
                                                MetadataKey.COMMANDED_PHASES, []
                                            )
                                            + ["cj_assessment"]
                                        )
                                    ),
                                },
                                session,  # Positional parameter
                                correlation_id=correlation_id,
                            )

                            logger.info(
                                f"Essay {essay_id} successfully transitioned to "
                                f"{essay_machine.current_status.value} via state machine.",
                                extra={
                                    "essay_id": essay_id,
                                    "previous_status": essay_state_model.current_status.value,
                                    "new_status": essay_machine.current_status.value,
                                    "batch_id": command_data.entity_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )

                            # Add to successfully transitioned list for dispatch
                            successfully_transitioned_essays.append(essay_ref)
                        else:
                            logger.warning(
                                f"State machine trigger '{CMD_INITIATE_CJ_ASSESSMENT}' failed "
                                f"for essay {essay_id} from status "
                                f"{essay_state_model.current_status.value}.",
                                extra={
                                    "batch_id": command_data.entity_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                    except Exception as e:
                        logger.error(
                            f"Failed to process essay {essay_id} with state machine",
                            extra={
                                "error": str(e),
                                "batch_id": command_data.entity_id,
                                "correlation_id": str(correlation_id),
                            },
                        )

                # Dispatch requests to CJ Assessment Service AFTER successful state transitions
                if successfully_transitioned_essays:
                    # Validate that batch_id (entity_id) is not None
                    if command_data.entity_id is None:
                        logger.error(
                            "Cannot dispatch CJ assessment requests: entity_id is None",
                            extra={"correlation_id": str(correlation_id)},
                        )
                        return

                    try:
                        # Convert string language to Language enum at boundary
                        language_enum = Language(command_data.language)

                        # Prefer identity from envelope metadata (canonical source)
                        user_id = None
                        org_id = None
                        batch_status = None

                        if envelope_metadata:
                            user_id = envelope_metadata.get("user_id")
                            org_id = envelope_metadata.get("org_id")

                        if user_id:
                            logger.info(
                                f"Using identity from envelope metadata: user_id={user_id}, org_id={org_id}",
                                extra={
                                    "batch_id": command_data.entity_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            # Still need batch_status for student_prompt_ref
                            batch_status = await self.batch_tracker.get_batch_status(
                                command_data.entity_id
                            )
                        else:
                            # Fallback to Redis if metadata missing (backward compatibility)
                            logger.warning(
                                "Identity not found in envelope metadata, falling back to Redis lookup",
                                extra={
                                    "batch_id": command_data.entity_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            batch_status = await self.batch_tracker.get_batch_status(
                                command_data.entity_id
                            )
                            if batch_status:
                                user_id = batch_status.get("user_id", "unknown-user")
                                org_id = batch_status.get("org_id")
                            else:
                                user_id = "unknown-user"
                                org_id = None
                                logger.error(
                                    "Could not retrieve identity from Redis either, using fallback",
                                    extra={
                                        "batch_id": command_data.entity_id,
                                        "correlation_id": str(correlation_id),
                                    },
                                )

                        # Phase 3.2: Pass student_prompt_ref from command data
                        await self.request_dispatcher.dispatch_cj_assessment_requests(
                            essays_to_process=successfully_transitioned_essays,
                            language=language_enum,
                            course_code=command_data.course_code,
                            batch_id=command_data.entity_id,
                            user_id=user_id,
                            org_id=org_id,
                            correlation_id=correlation_id,
                            session=session,
                            student_prompt_ref=command_data.student_prompt_ref,
                        )

                        logger.info(
                            "Successfully dispatched CJ assessment requests for transitioned essays",
                            extra={
                                "batch_id": command_data.entity_id,
                                "transitioned_essays_count": len(successfully_transitioned_essays),
                                "correlation_id": str(correlation_id),
                            },
                        )

                        # Trigger EVT_CJ_ASSESSMENT_STARTED after successful dispatch
                        for essay_ref in successfully_transitioned_essays:
                            try:
                                essay_state_model = await self.repository.get_essay_state(
                                    essay_ref.essay_id, session
                                )
                                if essay_state_model:
                                    essay_machine = EssayStateMachine(
                                        essay_id=essay_ref.essay_id,
                                        initial_status=essay_state_model.current_status,
                                    )

                                    logger.info(
                                        f"Triggering CJ assessment started for essay {essay_ref.essay_id}",
                                        extra={
                                            "essay_id": essay_ref.essay_id,
                                            "current_status": essay_state_model.current_status.value,
                                            "batch_id": command_data.entity_id,
                                            "correlation_id": str(correlation_id),
                                        },
                                    )

                                    if essay_machine.trigger_event(EVT_CJ_ASSESSMENT_STARTED):
                                        await self.repository.update_essay_status_via_machine(
                                            essay_ref.essay_id,
                                            essay_machine.current_status,
                                            {
                                                "cj_assessment_phase": "started",
                                                "dispatch_completed": True,
                                            },
                                            session,  # Positional parameter
                                            correlation_id=correlation_id,
                                        )
                                        logger.info(
                                            f"Essay {essay_ref.essay_id} transitioned to "
                                            f"{essay_machine.current_status.value} after dispatch",
                                            extra={
                                                "essay_id": essay_ref.essay_id,
                                                "previous_status": essay_state_model.current_status.value,
                                                "new_status": essay_machine.current_status.value,
                                                "batch_id": command_data.entity_id,
                                                "correlation_id": str(correlation_id),
                                            },
                                        )
                                    else:
                                        logger.warning(
                                            f"Failed to trigger EVT_CJ_ASSESSMENT_STARTED "
                                            f"for essay {essay_ref.essay_id}",
                                            extra={
                                                "current_status": essay_state_model.current_status.value,
                                                "correlation_id": str(correlation_id),
                                            },
                                        )
                            except Exception as e:
                                logger.error(
                                    f"Failed to trigger EVT_CJ_ASSESSMENT_STARTED "
                                    f"for essay {essay_ref.essay_id}",
                                    extra={
                                        "error": str(e),
                                        "correlation_id": str(correlation_id),
                                    },
                                )

                    except Exception as e:
                        logger.error(
                            "Failed to dispatch CJ assessment requests",
                            extra={
                                "error": str(e),
                                "batch_id": command_data.entity_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                else:
                    logger.warning(
                        f"No essays successfully transitioned to AWAITING_CJ_ASSESSMENT "
                        f"for batch {command_data.entity_id}. Skipping dispatch.",
                        extra={"correlation_id": str(correlation_id)},
                    )
                # Transaction commits here
