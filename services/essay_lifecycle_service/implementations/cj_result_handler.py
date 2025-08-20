"""
CJ Assessment result handler for Essay Lifecycle Service.

Handles CJ assessment completion and failure events,
managing state transitions for essays in CJ assessment batches.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
)
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger

# Import event constants from state machine to ensure consistency
from services.essay_lifecycle_service.essay_state_machine import (
    EVT_CJ_ASSESSMENT_FAILED,
    EVT_CJ_ASSESSMENT_SUCCEEDED,
    EssayStateMachine,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from services.essay_lifecycle_service.protocols import (
        BatchPhaseCoordinator,
        EssayRepositoryProtocol,
    )

logger = create_service_logger("cj_result_handler")


class CJResultHandler:
    """Handler for CJ assessment results."""

    def __init__(
        self,
        repository: EssayRepositoryProtocol,
        batch_coordinator: BatchPhaseCoordinator,
        session_factory: async_sessionmaker,
    ) -> None:
        """Initialize CJ result handler."""
        self.repository = repository
        self.batch_coordinator = batch_coordinator
        self.session_factory = session_factory

    async def handle_cj_assessment_completed(
        self,
        result_data: CJAssessmentCompletedV1,
        correlation_id: UUID,
        confirm_idempotency: Any = None,
    ) -> bool:
        """Handle CJ assessment completion from CJ Assessment Service.

        CRITICAL: This handler follows clean architecture principles.
        It ONLY updates state machine status - NO business data storage.
        Business data (rankings, scores, grade projections) goes to RAS via AssessmentResultV1.

        Args:
            result_data: Batch CJ assessment completion event (thin event)
            correlation_id: Correlation ID for tracking
            confirm_idempotency: Optional idempotency confirmation callback

        Returns:
            True if all essay states were successfully updated, False otherwise
        """
        try:
            logger.info(
                "Processing CJ assessment completion for batch",
                extra={
                    "batch_id": result_data.entity_id,
                    "job_id": result_data.cj_assessment_job_id,
                    "successful_count": result_data.processing_summary.get("successful", 0),
                    "failed_count": result_data.processing_summary.get("failed", 0),
                    "correlation_id": str(correlation_id),
                },
            )

            # Extract essay IDs from the processing summary
            successful_essay_ids = result_data.processing_summary.get("successful_essay_ids", [])
            failed_essay_ids = result_data.processing_summary.get("failed_essay_ids", [])

            if not successful_essay_ids and not failed_essay_ids:
                logger.warning(
                    "No essay IDs found in CJ assessment completion event",
                    extra={
                        "batch_id": result_data.entity_id,
                        "correlation_id": str(correlation_id),
                    },
                )
                return False

            # START UNIT OF WORK
            async with self.session_factory() as session:
                async with session.begin():
                    # Process successful essays
                    for essay_id in successful_essay_ids:
                        # Get current essay state
                        essay_state = await self.repository.get_essay_state(essay_id, session)
                        if essay_state is None:
                            logger.error(
                                "Essay not found for CJ assessment result",
                                extra={
                                    "essay_id": essay_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            continue

                        # Create state machine and trigger success event
                        state_machine = EssayStateMachine(
                            essay_id=essay_id, initial_status=essay_state.current_status
                        )

                        # Attempt state transition
                        if state_machine.trigger_event(EVT_CJ_ASSESSMENT_SUCCEEDED):
                            # Preserve existing commanded_phases metadata
                            existing_commanded_phases = essay_state.processing_metadata.get(
                                "commanded_phases", []
                            )

                            # Ensure cj_assessment is in commanded_phases
                            if "cj_assessment" not in existing_commanded_phases:
                                existing_commanded_phases.append("cj_assessment")

                            # CRITICAL: Only update state, NO business data storage
                            # Business data (rankings, scores, grades) goes to RAS only
                            await self.repository.update_essay_status_via_machine(
                                essay_id,
                                state_machine.current_status,
                                {
                                    "cj_assessment_result": {
                                        "success": True,
                                        "job_id": result_data.cj_assessment_job_id,
                                        # NO rank, score, or ranking_data - violates clean architecture
                                    },
                                    "current_phase": "cj_assessment",
                                    "commanded_phases": existing_commanded_phases,
                                    "phase_outcome_status": "CJ_ASSESSMENT_SUCCESS",
                                },
                                session,
                                correlation_id=correlation_id,
                            )

                            logger.info(
                                "Successfully processed CJ assessment completion for essay",
                                extra={
                                    "essay_id": essay_id,
                                    "new_status": state_machine.current_status.value,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                        else:
                            logger.error(
                                f"State machine trigger '{EVT_CJ_ASSESSMENT_SUCCEEDED}' failed "
                                f"for essay {essay_id} from status "
                                f"{essay_state.current_status.value}.",
                                extra={"correlation_id": str(correlation_id)},
                            )
                            continue

                    # Process failed essays
                    for essay_id in failed_essay_ids:
                        # Get current essay state
                        essay_state = await self.repository.get_essay_state(essay_id, session)
                        if essay_state is None:
                            logger.error(
                                "Essay not found for CJ assessment failure",
                                extra={
                                    "essay_id": essay_id,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            continue

                        # Create state machine and trigger failure event
                        state_machine = EssayStateMachine(
                            essay_id=essay_id, initial_status=essay_state.current_status
                        )

                        # Attempt state transition
                        if state_machine.trigger_event(EVT_CJ_ASSESSMENT_FAILED):
                            # Preserve existing commanded_phases metadata
                            existing_commanded_phases = essay_state.processing_metadata.get(
                                "commanded_phases", []
                            )

                            # Ensure cj_assessment is in commanded_phases
                            if "cj_assessment" not in existing_commanded_phases:
                                existing_commanded_phases.append("cj_assessment")

                            await self.repository.update_essay_status_via_machine(
                                essay_id,
                                state_machine.current_status,
                                {
                                    "cj_assessment_result": {
                                        "success": False,
                                        "job_id": result_data.cj_assessment_job_id,
                                        # NO error details - clean architecture
                                    },
                                    "current_phase": "cj_assessment",
                                    "commanded_phases": existing_commanded_phases,
                                    "phase_outcome_status": "CJ_ASSESSMENT_FAILED",
                                },
                                session,
                                correlation_id=correlation_id,
                            )

                            logger.info(
                                "Processed CJ assessment failure for essay",
                                extra={
                                    "essay_id": essay_id,
                                    "new_status": state_machine.current_status.value,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                        else:
                            logger.error(
                                f"State machine trigger '{EVT_CJ_ASSESSMENT_FAILED}' failed "
                                f"for essay {essay_id} from status "
                                f"{essay_state.current_status.value}.",
                                extra={"correlation_id": str(correlation_id)},
                            )
                            continue

                    # After processing all essays in the CJ batch result
                    # Check batch completion for ALL essays, not just the first one
                    logger.info(
                        "Checking batch phase completion for CJ assessment",
                        extra={
                            "batch_id": result_data.entity_id,
                            "total_essays": len(successful_essay_ids) + len(failed_essay_ids),
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Get batch status summary to log
                    if result_data.entity_id is None:
                        logger.error(
                            "Cannot get batch status summary: entity_id is None",
                            extra={"correlation_id": str(correlation_id)},
                        )
                        return False

                    batch_status_summary = await self.repository.get_batch_status_summary(
                        result_data.entity_id, session
                    )

                    # Safely create status summary for logging, handling potential mock issues
                    status_summary_for_log: dict[str, int] | str
                    try:
                        if (
                            hasattr(batch_status_summary, "items")
                            and not asyncio.iscoroutine(batch_status_summary)
                            and isinstance(batch_status_summary, dict)
                        ):
                            status_summary_for_log = {
                                k.value
                                if hasattr(k, "value") and not asyncio.iscoroutine(k)
                                else str(k): v
                                for k, v in batch_status_summary.items()
                            }
                        else:
                            status_summary_for_log = str(batch_status_summary)
                    except Exception:
                        status_summary_for_log = (
                            f"<unavailable: {type(batch_status_summary).__name__}>"
                        )

                    logger.info(
                        "Batch status summary after CJ assessment processing",
                        extra={
                            "batch_id": result_data.entity_id,
                            "status_summary": status_summary_for_log,
                            "correlation_id": str(correlation_id),
                        },
                    )

                    # Get a representative essay state to trigger batch completion check
                    representative_essay_id = (
                        (successful_essay_ids + failed_essay_ids)[0]
                        if (successful_essay_ids + failed_essay_ids)
                        else None
                    )
                    if representative_essay_id:
                        representative_essay_state = await self.repository.get_essay_state(
                            representative_essay_id, session
                        )
                        if representative_essay_state:
                            logger.info(
                                "Triggering batch completion check",
                                extra={
                                    "essay_id": representative_essay_id,
                                    "essay_status": representative_essay_state.current_status.value,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            await self.batch_coordinator.check_batch_completion(
                                essay_state=representative_essay_state,
                                phase_name=PhaseName.CJ_ASSESSMENT,
                                correlation_id=correlation_id,
                                session=session,
                            )
                    # Transaction commits here

            # Confirm idempotency after successful transaction commit
            if confirm_idempotency is not None:
                await confirm_idempotency()

            return True

        except Exception as e:
            logger.error(
                "Error handling CJ assessment completion",
                extra={
                    "batch_id": getattr(result_data, "entity_id", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False

    async def handle_cj_assessment_failed(
        self,
        result_data: CJAssessmentFailedV1,
        correlation_id: UUID,
    ) -> bool:
        """Handle CJ assessment failure from CJ Assessment Service."""
        try:
            logger.error(
                "Processing CJ assessment failure for batch",
                extra={
                    "batch_id": result_data.entity_id,
                    "job_id": result_data.cj_assessment_job_id,
                    "status": result_data.status.value if result_data.status else "unknown",
                    "correlation_id": str(correlation_id),
                },
            )

            # START UNIT OF WORK
            async with self.session_factory() as session:
                async with session.begin():
                    # CJ assessment failure affects all essays in the batch
                    # Need to find all essays in this batch and mark them as failed
                    if result_data.entity_id is None:
                        logger.error(
                            "Cannot list essays by batch: entity_id is None",
                            extra={"correlation_id": str(correlation_id)},
                        )
                        return False

                    batch_essays = await self.repository.list_essays_by_batch(result_data.entity_id)

                    for essay_state in batch_essays:
                        # Only update essays that are currently awaiting CJ assessment
                        if essay_state.current_status != EssayStatus.AWAITING_CJ_ASSESSMENT:
                            continue

                        # Create state machine and trigger failure event
                        state_machine = EssayStateMachine(
                            essay_id=essay_state.essay_id, initial_status=essay_state.current_status
                        )

                        # Attempt state transition
                        if state_machine.trigger_event(EVT_CJ_ASSESSMENT_FAILED):
                            await self.repository.update_essay_status_via_machine(
                                essay_state.essay_id,
                                state_machine.current_status,
                                {
                                    "cj_assessment_result": {
                                        "success": False,
                                        "job_id": result_data.cj_assessment_job_id,
                                        "batch_failure": True,
                                        "error_info": result_data.system_metadata.error_info
                                        if result_data.system_metadata
                                        else None,
                                    },
                                    "current_phase": "cj_assessment",
                                    "phase_outcome_status": "CJ_ASSESSMENT_FAILED",
                                },
                                session,
                                correlation_id=correlation_id,
                            )

                            logger.info(
                                "Successfully processed CJ assessment failure for essay",
                                extra={
                                    "essay_id": essay_state.essay_id,
                                    "new_status": state_machine.current_status.value,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                        else:
                            logger.error(
                                f"State machine trigger '{EVT_CJ_ASSESSMENT_FAILED}' failed "
                                f"for essay {essay_state.essay_id} from status "
                                f"{essay_state.current_status.value}.",
                                extra={"correlation_id": str(correlation_id)},
                            )
                            continue
                    # Transaction commits here

            return True

        except Exception as e:
            logger.error(
                "Error handling CJ assessment failure",
                extra={
                    "batch_id": getattr(result_data, "entity_id", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False
