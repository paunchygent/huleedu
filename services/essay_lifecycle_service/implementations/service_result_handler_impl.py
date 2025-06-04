"""
Service result handler implementation for Essay Lifecycle Service.

Handles results from specialized services like spell checker and CJ assessment,
integrating with EssayStateMachine for proper state transitions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.events.cj_assessment_events import (
        CJAssessmentCompletedV1,
        CJAssessmentFailedV1,
    )
    from common_core.events.spellcheck_models import SpellcheckResultDataV1

from huleedu_service_libs.logging_utils import create_service_logger

from essay_state_machine import (
    EVT_CJ_ASSESSMENT_FAILED,
    EVT_CJ_ASSESSMENT_SUCCEEDED,
    EVT_SPELLCHECK_FAILED,
    EVT_SPELLCHECK_SUCCEEDED,
    EssayStateMachine,
)
from protocols import BatchPhaseCoordinator, EssayStateStore, ServiceResultHandler

logger = create_service_logger("service_result_handler")


class DefaultServiceResultHandler(ServiceResultHandler):
    """Default implementation of ServiceResultHandler protocol."""

    def __init__(self, state_store: EssayStateStore, batch_coordinator: BatchPhaseCoordinator) -> None:
        self.state_store = state_store
        self.batch_coordinator = batch_coordinator

    async def handle_spellcheck_result(
        self,
        result_data: SpellcheckResultDataV1,
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle spellcheck result from Spell Checker Service."""
        try:
            from common_core.enums import EssayStatus

            # Determine success from status
            is_success = result_data.status == EssayStatus.SPELLCHECKED_SUCCESS

            logger.info(
                "Processing spellcheck result",
                extra={
                    "essay_id": result_data.entity_ref,
                    "status": result_data.status.value,
                    "success": is_success,
                    "correlation_id": str(correlation_id),
                },
            )

            # Get current essay state
            essay_state = await self.state_store.get_essay_state(result_data.entity_ref)
            if essay_state is None:
                logger.error(
                    "Essay not found for spellcheck result",
                    extra={
                        "essay_id": result_data.entity_ref,
                        "correlation_id": str(correlation_id),
                    },
                )
                return False

            # Create state machine and trigger appropriate event
            state_machine = EssayStateMachine(
                essay_id=result_data.entity_ref, initial_status=essay_state.current_status
            )

            if is_success:
                trigger = EVT_SPELLCHECK_SUCCEEDED
                logger.info(
                    "Spellcheck succeeded, transitioning to success state",
                    extra={
                        "essay_id": result_data.entity_ref,
                        "current_status": essay_state.current_status.value,
                        "correlation_id": str(correlation_id),
                    },
                )
            else:
                trigger = EVT_SPELLCHECK_FAILED
                logger.warning(
                    "Spellcheck failed, transitioning to failed state",
                    extra={
                        "essay_id": result_data.entity_ref,
                        "current_status": essay_state.current_status.value,
                        "error_info": result_data.system_metadata.error_info if result_data.system_metadata else None,
                        "correlation_id": str(correlation_id),
                    },
                )

            # Attempt state transition
            if state_machine.trigger(trigger):
                # Correct call to update_essay_status_via_machine
                await self.state_store.update_essay_status_via_machine(
                    essay_id=result_data.entity_ref,
                    new_status=state_machine.current_status,
                    metadata={
                        "spellcheck_result": {
                            "success": is_success,
                            "status": result_data.status.value,
                            "original_text_storage_id": result_data.original_text_storage_id,
                            "storage_metadata": result_data.storage_metadata,
                            "corrections_made": result_data.corrections_made,
                            "error_info": result_data.system_metadata.error_info if result_data.system_metadata else None,
                        },
                        "current_phase": "spellcheck",
                        "phase_outcome_status": result_data.status.value
                    }
                )

                logger.info(
                    "Successfully updated essay status via state machine",
                    extra={
                        "essay_id": result_data.entity_ref,
                        "new_status": state_machine.current_status.value,
                        "correlation_id": str(correlation_id),
                    },
                )
            else:
                logger.error(
                    f"State machine trigger '{trigger}' failed for essay {result_data.entity_ref} "
                    f"from status {essay_state.current_status.value}.",
                    extra={"correlation_id": str(correlation_id)},
                )
                return False

            logger.info(
                "Successfully processed spellcheck result",
                extra={
                    "essay_id": result_data.entity_ref,
                    "new_status": state_machine.current_status.value,
                    "correlation_id": str(correlation_id),
                },
            )

            # Check for batch phase completion after individual essay state update
            updated_essay_state = await self.state_store.get_essay_state(result_data.entity_ref)
            if updated_essay_state:
                await self.batch_coordinator.check_batch_completion(
                    essay_state=updated_essay_state,
                    phase_name="spellcheck",
                    correlation_id=correlation_id,
                )

            return True

        except Exception as e:
            logger.error(
                "Error handling spellcheck result",
                extra={
                    "essay_id": getattr(result_data, "entity_ref", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False

    async def handle_cj_assessment_completed(
        self,
        result_data: CJAssessmentCompletedV1,
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle CJ assessment completion from CJ Assessment Service."""
        try:
            logger.info(
                "Processing CJ assessment completion for batch",
                extra={
                    "batch_id": result_data.entity_ref,
                    "job_id": result_data.cj_assessment_job_id,
                    "correlation_id": str(correlation_id),
                },
            )

            # CJ assessment results are batch-level, need to process each essay ranking
            for ranking in result_data.rankings:
                essay_id = ranking.get("els_essay_id")
                if not essay_id:
                    logger.warning(
                        "Missing essay ID in CJ ranking",
                        extra={"ranking": ranking, "correlation_id": str(correlation_id)},
                    )
                    continue

                # Get current essay state
                essay_state = await self.state_store.get_essay_state(essay_id)
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
                if state_machine.trigger(EVT_CJ_ASSESSMENT_SUCCEEDED):
                    await self.state_store.update_essay_status_via_machine(
                        essay_id=essay_id,
                        new_status=state_machine.current_status,
                        metadata={
                            "cj_assessment_result": {
                                "success": True,
                                "job_id": result_data.cj_assessment_job_id,
                                "rank": ranking.get("rank"),
                                "score": ranking.get("score"),
                                "ranking_data": ranking,
                            },
                            "current_phase": "cj_assessment",
                            "phase_outcome_status": "CJ_ASSESSMENT_SUCCESS"
                        }
                    )

                    logger.info(
                        "Successfully processed CJ assessment completion for essay",
                        extra={
                            "essay_id": essay_id,
                            "new_status": state_machine.current_status.value,
                            "rank": ranking.get("rank"),
                            "correlation_id": str(correlation_id),
                        },
                    )
                else:
                    logger.error(
                        f"State machine trigger '{EVT_CJ_ASSESSMENT_SUCCEEDED}' failed for essay {essay_id} "
                        f"from status {essay_state.current_status.value}.",
                        extra={"correlation_id": str(correlation_id)},
                    )
                    continue

            # After processing all essays in the CJ batch result
            # We need a representative essay_state from the batch to trigger check_batch_completion
            if result_data.rankings:
                first_essay_id_in_ranking = result_data.rankings[0].get("els_essay_id")
                if first_essay_id_in_ranking:
                    batch_representative_essay_state = await self.state_store.get_essay_state(first_essay_id_in_ranking)
                    if batch_representative_essay_state:
                        await self.batch_coordinator.check_batch_completion(
                            essay_state=batch_representative_essay_state,
                            phase_name="cj_assessment",
                            correlation_id=correlation_id,
                        )

            return True

        except Exception as e:
            logger.error(
                "Error handling CJ assessment completion",
                extra={
                    "batch_id": getattr(result_data, "entity_ref", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False

    async def handle_cj_assessment_failed(
        self,
        result_data: CJAssessmentFailedV1,
        correlation_id: UUID | None = None,
    ) -> bool:
        """Handle CJ assessment failure from CJ Assessment Service."""
        try:
            logger.error(
                "Processing CJ assessment failure for batch",
                extra={
                    "batch_id": result_data.entity_ref,
                    "job_id": result_data.cj_assessment_job_id,
                    "status": result_data.status.value if result_data.status else "unknown",
                    "correlation_id": str(correlation_id),
                },
            )

            # CJ assessment failure affects all essays in the batch
            # Need to find all essays in this batch and mark them as failed
            batch_essays = await self.state_store.list_essays_by_batch(result_data.entity_ref)

            for essay_state in batch_essays:
                # Only update essays that are currently awaiting CJ assessment
                from common_core.enums import EssayStatus
                if essay_state.current_status != EssayStatus.AWAITING_CJ_ASSESSMENT:
                    continue

                # Create state machine and trigger failure event
                state_machine = EssayStateMachine(
                    essay_id=essay_state.essay_id, initial_status=essay_state.current_status
                )

                # Attempt state transition
                if state_machine.trigger(EVT_CJ_ASSESSMENT_FAILED):
                    await self.state_store.update_essay_status_via_machine(
                        essay_id=essay_state.essay_id,
                        new_status=state_machine.current_status,
                        metadata={
                            "cj_assessment_result": {
                                "success": False,
                                "job_id": result_data.cj_assessment_job_id,
                                "batch_failure": True,
                                "error_info": result_data.system_metadata.error_info if result_data.system_metadata else None,
                            },
                            "current_phase": "cj_assessment",
                            "phase_outcome_status": "CJ_ASSESSMENT_FAILED"
                        }
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
                        f"State machine trigger '{EVT_CJ_ASSESSMENT_FAILED}' failed for essay {essay_state.essay_id} "
                        f"from status {essay_state.current_status.value}.",
                        extra={"correlation_id": str(correlation_id)},
                    )
                    continue

            return True

        except Exception as e:
            logger.error(
                "Error handling CJ assessment failure",
                extra={
                    "batch_id": getattr(result_data, "entity_ref", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False
