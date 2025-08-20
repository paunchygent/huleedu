"""
Spellcheck result handler for Essay Lifecycle Service.

Handles SpellcheckPhaseCompletedV1 (thin event) for state transitions
and SpellcheckResultDataV1 (rich event) for spellcheck completion.
Part of dual-event pattern where RAS handles rich SpellcheckResultV1.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import get_current_trace_id, trace_operation
from opentelemetry import trace
from quart import current_app, has_app_context

# Import event constants from state machine to ensure consistency
from services.essay_lifecycle_service.essay_state_machine import (
    EVT_SPELLCHECK_FAILED,
    EVT_SPELLCHECK_SUCCEEDED,
    EssayStateMachine,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from services.essay_lifecycle_service.protocols import (
        BatchPhaseCoordinator,
        EssayRepositoryProtocol,
    )

logger = create_service_logger("spellcheck_result_handler")


class SpellcheckResultHandler:
    """Handler for spellcheck phase completion events."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
        session_factory: async_sessionmaker,
    ) -> None:
        """Initialize spellcheck result handler."""
        self.repository = repository
        self.batch_coordinator = batch_coordinator
        self.session_factory = session_factory

    async def handle_spellcheck_result(
        self,
        result_data: SpellcheckResultDataV1,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Handle spellcheck result from Spell Checker Service (rich event)."""
        try:
            # Determine success from status
            is_success = result_data.status == EssayStatus.SPELLCHECKED_SUCCESS

            logger.info(
                "Processing spellcheck result",
                extra={
                    "essay_id": result_data.entity_id,
                    "status": result_data.status.value,
                    "success": is_success,
                    "correlation_id": str(correlation_id),
                },
            )

            # Get current essay state
            if not result_data.entity_id:
                logger.error("Missing entity_id in spellcheck result")
                return False

            # START UNIT OF WORK - Open transaction early for all DB operations
            async with self.session_factory() as session:
                async with session.begin():
                    essay_state = await self.repository.get_essay_state(
                        result_data.entity_id, session
                    )
                    if essay_state is None:
                        logger.error(
                            "Essay not found for spellcheck result",
                            extra={
                                "essay_id": result_data.entity_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                        return False

                    # Create state machine and trigger appropriate event
                    state_machine = EssayStateMachine(
                        essay_id=result_data.entity_id, initial_status=essay_state.current_status
                    )

                    if is_success:
                        trigger = EVT_SPELLCHECK_SUCCEEDED
                        logger.info(
                            "Spellcheck succeeded, transitioning to success state",
                            extra={
                                "essay_id": result_data.entity_id,
                                "current_status": essay_state.current_status.value,
                                "correlation_id": str(correlation_id),
                            },
                        )
                    else:
                        trigger = EVT_SPELLCHECK_FAILED
                        logger.warning(
                            "Spellcheck failed, transitioning to failed state",
                            extra={
                                "essay_id": result_data.entity_id,
                                "current_status": essay_state.current_status.value,
                                "error_info": result_data.system_metadata.error_info
                                if result_data.system_metadata
                                else None,
                                "correlation_id": str(correlation_id),
                            },
                        )

                    # Attempt state transition
                    if state_machine.trigger_event(trigger):
                        storage_ref_to_add = None
                        if is_success and result_data.storage_metadata:
                            # Get tracer if available
                            tracer = None
                            if has_app_context() and hasattr(current_app, "tracer"):
                                tracer = current_app.tracer

                            # Trace storage reference extraction
                            with (
                                trace_operation(
                                    tracer or trace.get_tracer(__name__),
                                    "extract_storage_reference",
                                    {
                                        "essay_id": str(result_data.entity_id),
                                        "has_storage_metadata": True,
                                        "content_type": ContentType.CORRECTED_TEXT.value,
                                    },
                                )
                                if tracer
                                else nullcontext()
                            ):
                                # Safely access the nested storage_id for the spellchecked essay
                                spellchecked_ref = result_data.storage_metadata.references.get(
                                    ContentType.CORRECTED_TEXT
                                )
                                if spellchecked_ref:
                                    storage_id = spellchecked_ref.get("default")
                                    if storage_id:
                                        storage_ref_to_add = (
                                            ContentType.CORRECTED_TEXT,
                                            storage_id,
                                        )
                                        logger.info(
                                            "Extracted storage reference",
                                            extra={
                                                "storage_id": storage_id,
                                                "content_type": ContentType.CORRECTED_TEXT.value,
                                                "trace_id": get_current_trace_id(),
                                            },
                                        )

                        await self.repository.update_essay_status_via_machine(
                            result_data.entity_id,
                            state_machine.current_status,
                            {
                                "spellcheck_result": {
                                    "success": is_success,
                                    "status": result_data.status.value,
                                    "original_text_storage_id": result_data.original_text_storage_id,
                                    "storage_metadata": result_data.storage_metadata.model_dump()
                                    if result_data.storage_metadata
                                    else None,
                                    "corrections_made": result_data.corrections_made,
                                    "error_info": result_data.system_metadata.error_info
                                    if result_data.system_metadata
                                    else None,
                                },
                                "current_phase": "spellcheck",
                                "phase_outcome_status": result_data.status.value,
                            },
                            session,
                            storage_reference=storage_ref_to_add,
                            correlation_id=correlation_id,
                        )

                        logger.info(
                            "Successfully updated essay status via state machine",
                            extra={
                                "essay_id": result_data.entity_id,
                                "new_status": state_machine.current_status.value,
                                "correlation_id": str(correlation_id),
                            },
                        )

                        # Check for batch phase completion after individual essay state update
                        updated_essay_state = await self.repository.get_essay_state(
                            result_data.entity_id, session
                        )
                        if updated_essay_state:
                            await self.batch_coordinator.check_batch_completion(
                                essay_state=updated_essay_state,
                                phase_name=PhaseName.SPELLCHECK,
                                correlation_id=correlation_id,
                                session=session,
                            )
                        # Transaction commits here
                    else:
                        logger.error(
                            f"State machine trigger '{trigger}' failed for essay "
                            f"{result_data.entity_id} from status "
                            f"{essay_state.current_status.value}.",
                            extra={"correlation_id": str(correlation_id)},
                        )
                        return False

            # Confirm idempotency after successful transaction commit
            if confirm_idempotency is not None:
                await confirm_idempotency()

            logger.info(
                "Successfully processed spellcheck result",
                extra={
                    "essay_id": result_data.entity_id,
                    "new_status": state_machine.current_status.value,
                    "correlation_id": str(correlation_id),
                },
            )

            return True

        except Exception as e:
            logger.error(
                "Error handling spellcheck result",
                extra={
                    "essay_id": getattr(result_data, "entity_id", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False

    async def handle_spellcheck_phase_completed(
        self,
        essay_id: str,
        batch_id: str,
        status: EssayStatus,
        corrected_text_storage_id: str | None,
        error_code: str | None,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Handle thin spellcheck phase completion event for state transitions.

        This method handles the new thin event from the dual event pattern,
        containing only the minimal data needed for state transitions.
        """
        try:
            # Determine success from status
            is_success = status == EssayStatus.SPELLCHECKED_SUCCESS

            logger.info(
                "Processing spellcheck phase completed (thin event)",
                extra={
                    "essay_id": essay_id,
                    "batch_id": batch_id,
                    "status": status.value,
                    "success": is_success,
                    "correlation_id": str(correlation_id),
                },
            )

            # START UNIT OF WORK - Open transaction early for all DB operations
            try:
                session_factory_call = self.session_factory()
            except Exception as e:
                logger.error(
                    "Failed to create database session",
                    extra={
                        "essay_id": essay_id,
                        "error": str(e),
                        "correlation_id": str(correlation_id),
                    },
                )
                return False

            async with session_factory_call as session:
                async with session.begin():
                    essay_state = await self.repository.get_essay_state(essay_id, session)
                    if essay_state is None:
                        logger.error(
                            "Essay not found for spellcheck phase completed",
                            extra={
                                "essay_id": essay_id,
                                "batch_id": batch_id,
                                "correlation_id": str(correlation_id),
                            },
                        )
                        return False

                    # Create state machine and trigger appropriate event
                    state_machine = EssayStateMachine(
                        essay_id=essay_id, initial_status=essay_state.current_status
                    )

                    if is_success:
                        trigger = EVT_SPELLCHECK_SUCCEEDED
                        logger.info(
                            "Spellcheck phase succeeded, transitioning to success state",
                            extra={
                                "essay_id": essay_id,
                                "current_status": essay_state.current_status.value,
                                "correlation_id": str(correlation_id),
                            },
                        )
                    else:
                        trigger = EVT_SPELLCHECK_FAILED
                        logger.warning(
                            "Spellcheck phase failed, transitioning to failed state",
                            extra={
                                "essay_id": essay_id,
                                "current_status": essay_state.current_status.value,
                                "error_code": error_code,
                                "correlation_id": str(correlation_id),
                            },
                        )

                    # Attempt state transition
                    if state_machine.trigger_event(trigger):
                        storage_ref_to_add = None
                        if is_success and corrected_text_storage_id:
                            storage_ref_to_add = (
                                ContentType.CORRECTED_TEXT,
                                corrected_text_storage_id,
                            )
                            logger.info(
                                "Using corrected text storage reference",
                                extra={
                                    "storage_id": corrected_text_storage_id,
                                    "content_type": ContentType.CORRECTED_TEXT.value,
                                },
                            )

                        # Preserve existing commanded_phases metadata
                        existing_commanded_phases = essay_state.processing_metadata.get(
                            "commanded_phases", []
                        )

                        # Ensure spellcheck is in commanded_phases
                        if "spellcheck" not in existing_commanded_phases:
                            existing_commanded_phases.append("spellcheck")

                        await self.repository.update_essay_status_via_machine(
                            essay_id,
                            state_machine.current_status,
                            {
                                "spellcheck_result": {
                                    "success": is_success,
                                    "status": status.value,
                                    "corrected_text_storage_id": corrected_text_storage_id,
                                    "error_code": error_code,
                                },
                                "current_phase": "spellcheck",
                                "commanded_phases": existing_commanded_phases,
                                "phase_outcome_status": status.value,
                            },
                            session,
                            storage_reference=storage_ref_to_add,
                            correlation_id=correlation_id,
                        )

                        logger.info(
                            "Successfully updated essay status via state machine (thin event)",
                            extra={
                                "essay_id": essay_id,
                                "new_status": state_machine.current_status.value,
                                "correlation_id": str(correlation_id),
                            },
                        )

                        # Check for batch phase completion after individual essay state update
                        updated_essay_state = await self.repository.get_essay_state(
                            essay_id, session
                        )
                        if updated_essay_state:
                            await self.batch_coordinator.check_batch_completion(
                                essay_state=updated_essay_state,
                                phase_name=PhaseName.SPELLCHECK,
                                correlation_id=correlation_id,
                                session=session,
                            )
                        # Transaction commits here
                    else:
                        logger.error(
                            f"State machine trigger '{trigger}' failed for essay "
                            f"{essay_id} from status "
                            f"{essay_state.current_status.value}.",
                            extra={"correlation_id": str(correlation_id)},
                        )
                        return False

            # Confirm idempotency after successful transaction commit
            if confirm_idempotency is not None:
                await confirm_idempotency()

            logger.info(
                "Successfully processed spellcheck phase completed (thin event)",
                extra={
                    "essay_id": essay_id,
                    "new_status": state_machine.current_status.value,
                    "correlation_id": str(correlation_id),
                },
            )

            return True

        except Exception as e:
            logger.error(
                "Error handling spellcheck phase completed",
                extra={
                    "essay_id": essay_id,
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False
