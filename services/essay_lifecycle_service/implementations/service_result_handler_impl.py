"""
Service result handler implementation for Essay Lifecycle Service.

Handles results from specialized services like spell checker and CJ assessment,
integrating with EssayStateMachine for proper state transitions.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING
from uuid import UUID

from common_core.domain_enums import ContentType
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
)
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.pipeline_models import PhaseName
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import get_current_trace_id, trace_operation
from opentelemetry import trace
from quart import current_app, has_app_context

# Import event constants from state machine to ensure consistency
from services.essay_lifecycle_service.essay_state_machine import (
    EVT_CJ_ASSESSMENT_FAILED,
    EVT_CJ_ASSESSMENT_SUCCEEDED,
    EVT_SPELLCHECK_FAILED,
    EVT_SPELLCHECK_SUCCEEDED,
)

# Import at runtime to avoid circular imports
if TYPE_CHECKING:
    from services.essay_lifecycle_service.essay_state_machine import EssayStateMachine
    from services.essay_lifecycle_service.protocols import (
        BatchPhaseCoordinator,
        EssayRepositoryProtocol,
        ServiceResultHandler,
    )

# Import EssayStateMachine at runtime since it's used in the code
from services.essay_lifecycle_service.essay_state_machine import EssayStateMachine
from services.essay_lifecycle_service.protocols import (
    BatchPhaseCoordinator,
    EssayRepositoryProtocol,
    ServiceResultHandler,
)

logger = create_service_logger("service_result_handler")


class DefaultServiceResultHandler(ServiceResultHandler):
    """Default implementation of ServiceResultHandler protocol."""

    def __init__(
        self, repository: EssayRepositoryProtocol, batch_coordinator: BatchPhaseCoordinator
    ) -> None:
        self.repository = repository
        self.batch_coordinator = batch_coordinator

    async def handle_spellcheck_result(
        self,
        result_data: SpellcheckResultDataV1,
        correlation_id: UUID,
    ) -> bool:
        """Handle spellcheck result from Spell Checker Service."""
        try:
            # Determine success from status
            is_success = result_data.status == EssayStatus.SPELLCHECKED_SUCCESS

            logger.info(
                "Processing spellcheck result",
                extra={
                    "essay_id": result_data.entity_ref.entity_id,
                    "status": result_data.status.value,
                    "success": is_success,
                    "correlation_id": str(correlation_id),
                },
            )

            # Get current essay state
            essay_state = await self.repository.get_essay_state(result_data.entity_ref.entity_id)
            if essay_state is None:
                logger.error(
                    "Essay not found for spellcheck result",
                    extra={
                        "essay_id": result_data.entity_ref.entity_id,
                        "correlation_id": str(correlation_id),
                    },
                )
                return False

            # Create state machine and trigger appropriate event
            state_machine = EssayStateMachine(
                essay_id=result_data.entity_ref.entity_id, initial_status=essay_state.current_status
            )

            if is_success:
                trigger = EVT_SPELLCHECK_SUCCEEDED
                logger.info(
                    "Spellcheck succeeded, transitioning to success state",
                    extra={
                        "essay_id": result_data.entity_ref.entity_id,
                        "current_status": essay_state.current_status.value,
                        "correlation_id": str(correlation_id),
                    },
                )
            else:
                trigger = EVT_SPELLCHECK_FAILED
                logger.warning(
                    "Spellcheck failed, transitioning to failed state",
                    extra={
                        "essay_id": result_data.entity_ref.entity_id,
                        "current_status": essay_state.current_status.value,
                        "error_info": result_data.system_metadata.error_info
                        if result_data.system_metadata
                        else None,
                        "correlation_id": str(correlation_id),
                    },
                )

            # Attempt state transition
            if state_machine.trigger(trigger):
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
                                "essay_id": str(result_data.entity_ref.entity_id),
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
                                storage_ref_to_add = (ContentType.CORRECTED_TEXT, storage_id)
                                logger.info(
                                    "Extracted storage reference",
                                    extra={
                                        "storage_id": storage_id,
                                        "content_type": ContentType.CORRECTED_TEXT.value,
                                        "trace_id": get_current_trace_id(),
                                    },
                                )

                await self.repository.update_essay_status_via_machine(
                    essay_id=result_data.entity_ref.entity_id,
                    new_status=state_machine.current_status,
                    storage_reference=storage_ref_to_add,
                    metadata={
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
                )

                logger.info(
                    "Successfully updated essay status via state machine",
                    extra={
                        "essay_id": result_data.entity_ref.entity_id,
                        "new_status": state_machine.current_status.value,
                        "correlation_id": str(correlation_id),
                    },
                )
            else:
                logger.error(
                    f"State machine trigger '{trigger}' failed for essay "
                    f"{result_data.entity_ref.entity_id} from status "
                    f"{essay_state.current_status.value}.",
                    extra={"correlation_id": str(correlation_id)},
                )
                return False

            logger.info(
                "Successfully processed spellcheck result",
                extra={
                    "essay_id": result_data.entity_ref.entity_id,
                    "new_status": state_machine.current_status.value,
                    "correlation_id": str(correlation_id),
                },
            )

            # Check for batch phase completion after individual essay state update
            updated_essay_state = await self.repository.get_essay_state(
                result_data.entity_ref.entity_id
            )
            if updated_essay_state:
                await self.batch_coordinator.check_batch_completion(
                    essay_state=updated_essay_state,
                    phase_name=PhaseName.SPELLCHECK,
                    correlation_id=correlation_id,
                )

            return True

        except Exception as e:
            logger.error(
                "Error handling spellcheck result",
                extra={
                    "essay_id": getattr(result_data.entity_ref, "entity_id", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False

    async def handle_cj_assessment_completed(
        self,
        result_data: CJAssessmentCompletedV1,
        correlation_id: UUID,
    ) -> bool:
        """Handle CJ assessment completion from CJ Assessment Service."""
        try:
            logger.info(
                "Processing CJ assessment completion for batch",
                extra={
                    "batch_id": result_data.entity_ref.entity_id,
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
                essay_state = await self.repository.get_essay_state(essay_id)
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
                    # Preserve existing commanded_phases metadata
                    existing_commanded_phases = essay_state.processing_metadata.get(
                        "commanded_phases", []
                    )

                    # Ensure cj_assessment is in commanded_phases
                    if "cj_assessment" not in existing_commanded_phases:
                        existing_commanded_phases.append("cj_assessment")

                    await self.repository.update_essay_status_via_machine(
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
                            "commanded_phases": existing_commanded_phases,
                            "phase_outcome_status": "CJ_ASSESSMENT_SUCCESS",
                        },
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
                        f"State machine trigger '{EVT_CJ_ASSESSMENT_SUCCEEDED}' failed "
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
                    "batch_id": result_data.entity_ref.entity_id,
                    "total_rankings": len(result_data.rankings),
                    "correlation_id": str(correlation_id),
                },
            )

            # Get batch status summary to log
            batch_status_summary = await self.repository.get_batch_status_summary(
                result_data.entity_ref.entity_id
            )
            logger.info(
                "Batch status summary after CJ assessment processing",
                extra={
                    "batch_id": result_data.entity_ref.entity_id,
                    "status_summary": {k.value: v for k, v in batch_status_summary.items()},
                    "correlation_id": str(correlation_id),
                },
            )

            # We need a representative essay_state from the batch to trigger check_batch_completion
            if result_data.rankings:
                # Try multiple essays in case the first one has metadata issues
                for i, ranking in enumerate(result_data.rankings[:3]):  # Check first 3 essays
                    essay_id_in_ranking = ranking.get("els_essay_id")
                    if essay_id_in_ranking:
                        batch_representative_essay_state = await self.repository.get_essay_state(
                            essay_id_in_ranking
                        )
                        if batch_representative_essay_state:
                            logger.info(
                                f"Triggering batch completion check with essay {i+1}/{len(result_data.rankings)}",
                                extra={
                                    "essay_id": essay_id_in_ranking,
                                    "essay_status": batch_representative_essay_state.current_status.value,
                                    "essay_metadata": batch_representative_essay_state.processing_metadata,
                                    "correlation_id": str(correlation_id),
                                },
                            )
                            await self.batch_coordinator.check_batch_completion(
                                essay_state=batch_representative_essay_state,
                                phase_name=PhaseName.CJ_ASSESSMENT,
                                correlation_id=correlation_id,
                            )
                            break  # Only need to check once

            return True

        except Exception as e:
            logger.error(
                "Error handling CJ assessment completion",
                extra={
                    "batch_id": getattr(result_data.entity_ref, "entity_id", "unknown"),
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
                    "batch_id": result_data.entity_ref.entity_id,
                    "job_id": result_data.cj_assessment_job_id,
                    "status": result_data.status.value if result_data.status else "unknown",
                    "correlation_id": str(correlation_id),
                },
            )

            # CJ assessment failure affects all essays in the batch
            # Need to find all essays in this batch and mark them as failed
            batch_essays = await self.repository.list_essays_by_batch(
                result_data.entity_ref.entity_id
            )

            for essay_state in batch_essays:
                # Only update essays that are currently awaiting CJ assessment
                if essay_state.current_status != EssayStatus.AWAITING_CJ_ASSESSMENT:
                    continue

                # Create state machine and trigger failure event
                state_machine = EssayStateMachine(
                    essay_id=essay_state.essay_id, initial_status=essay_state.current_status
                )

                # Attempt state transition
                if state_machine.trigger(EVT_CJ_ASSESSMENT_FAILED):
                    await self.repository.update_essay_status_via_machine(
                        essay_id=essay_state.essay_id,
                        new_status=state_machine.current_status,
                        metadata={
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

            return True

        except Exception as e:
            logger.error(
                "Error handling CJ assessment failure",
                extra={
                    "batch_id": getattr(result_data.entity_ref, "entity_id", "unknown"),
                    "error": str(e),
                    "correlation_id": str(correlation_id),
                },
            )
            return False
