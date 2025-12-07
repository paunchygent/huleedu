"""Workflow continuation logic for CJ Assessment Service.

Isolates continuation checks and scoring trigger away from callback handler
to improve SRP and keep modules small and focused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic import comparison_processing, scoring_ranking
from services.cj_assessment_service.cj_core_logic.batch_finalizer import BatchFinalizer
from services.cj_assessment_service.cj_core_logic.batch_submission import (
    merge_batch_processing_metadata,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.cj_core_logic.pair_generation import PairGenerationMode
from services.cj_assessment_service.cj_core_logic.scoring_ranking import BTScoringResult
from services.cj_assessment_service.cj_core_logic.workflow_decision import (
    ContinuationDecision,
    _build_continuation_context,
    _can_attempt_resampling,
    _compute_success_metrics,
    decide,
)
from services.cj_assessment_service.cj_core_logic.workflow_diagnostics import (
    record_workflow_decision,
)
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    PairMatchingStrategyProtocol,
    PairOrientationStrategyProtocol,
    SessionProviderProtocol,
)

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
        BatchRetryProcessor,
    )
    from services.cj_assessment_service.config import Settings

logger = create_service_logger("cj_assessment_service.workflow_continuation")


async def check_workflow_continuation(
    batch_id: int,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    correlation_id: UUID,
) -> bool:
    """Return True only when all submitted callbacks for the batch have arrived."""
    async with session_provider.session() as session:
        batch_state = await batch_repository.get_batch_state(session, batch_id)
        if not batch_state:
            logger.warning(
                "Batch state not found for batch",
                extra={"correlation_id": str(correlation_id), "batch_id": batch_id},
            )
            return False

        callbacks_received = batch_state.completed_comparisons + batch_state.failed_comparisons
        pending_callbacks = max(batch_state.submitted_comparisons - callbacks_received, 0)
        iteration_complete = bool(batch_state.submitted_comparisons > 0 and pending_callbacks == 0)

        denominator = batch_state.completion_denominator()

        logger.info(
            "Continuation check computed",
            extra={
                "correlation_id": str(correlation_id),
                "batch_id": batch_id,
                "submitted_comparisons": batch_state.submitted_comparisons,
                "completed_comparisons": batch_state.completed_comparisons,
                "failed_comparisons": batch_state.failed_comparisons,
                "callbacks_received": callbacks_received,
                "pending_callbacks": pending_callbacks,
                "completion_denominator": denominator,
                "iteration_complete": iteration_complete,
            },
        )

        return iteration_complete


def _resolve_comparison_budget(
    metadata: dict[str, Any] | None,
    settings: "Settings",
) -> int:
    """Resolve effective comparison budget from metadata or settings."""
    budget = metadata.get("comparison_budget") if isinstance(metadata, dict) else None
    max_pairs = budget.get("max_pairs_requested") if budget else None

    if not isinstance(max_pairs, int) or max_pairs <= 0:
        max_pairs = settings.MAX_PAIRWISE_COMPARISONS

    return max_pairs


def _extract_previous_scores(metadata: dict[str, Any] | None) -> dict[str, float]:
    """Safely extract previously persisted BT scores from metadata."""

    if not isinstance(metadata, dict):
        return {}

    scores_obj = metadata.get("bt_scores")
    if not isinstance(scores_obj, dict):
        return {}

    try:
        return {str(k): float(v) for k, v in scores_obj.items()}
    except Exception:
        return {}


async def trigger_existing_workflow_continuation(
    batch_id: int,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: "Settings",
    content_client: ContentClientProtocol,
    correlation_id: UUID,
    llm_interaction: LLMInteractionProtocol,
    matching_strategy: PairMatchingStrategyProtocol,
    orientation_strategy: PairOrientationStrategyProtocol,
    retry_processor: "BatchRetryProcessor | None" = None,
    grade_projector: GradeProjector | None = None,
) -> None:
    """Continue workflow after callback if conditions allow.

    - Checks completion thresholds and triggers finalization via BatchFinalizer
    - Requests additional comparisons when budget remains and stability not reached

    The same DI-provided PairOrientationStrategyProtocol is threaded into both
    COVERAGE and RESAMPLING continuation paths so that changing
    `PAIR_ORIENTATION_STRATEGY` at the settings/DI level affects initial
    submission and all continuation waves without any internal fallbacks.
    """
    log_extra = {"correlation_id": str(correlation_id), "batch_id": batch_id}
    logger.info("Triggering workflow continuation", extra=log_extra)
    _ = retry_processor  # reserved for future retry-aware continuation paths

    async with session_provider.session() as session:
        batch_state = await batch_repository.get_batch_state(session, batch_id)
        if not batch_state:
            logger.error("Batch state not found", extra=log_extra)
            return

        completed = batch_state.completed_comparisons or 0
        failed = batch_state.failed_comparisons or 0
        callbacks_received = completed + failed
        pending_callbacks = max(batch_state.submitted_comparisons - callbacks_received, 0)

        if pending_callbacks > 0:
            logger.info(
                "Waiting for remaining callbacks before scoring",
                extra={
                    **log_extra,
                    "pending_callbacks": pending_callbacks,
                    "submitted_comparisons": batch_state.submitted_comparisons,
                    "completed_comparisons": batch_state.completed_comparisons,
                    "failed_comparisons": batch_state.failed_comparisons,
                },
            )
            return

        metadata = (
            batch_state.processing_metadata
            if isinstance(batch_state.processing_metadata, dict)
            else {}
        )
        config_overrides_payload = (
            metadata.get("config_overrides") if isinstance(metadata, dict) else None
        )
        llm_overrides_payload = (
            metadata.get("llm_overrides") if isinstance(metadata, dict) else None
        )
        original_request_payload = (
            metadata.get("original_request") if isinstance(metadata, dict) else None
        )

        max_pairs_cap = _resolve_comparison_budget(metadata, settings)
        pairs_submitted = batch_state.submitted_comparisons or 0
        pairs_remaining = max(0, max_pairs_cap - pairs_submitted)
        budget_exhausted = pairs_remaining <= 0

        denominator = batch_state.completion_denominator()
        callbacks_reached_cap = denominator > 0 and callbacks_received >= denominator

        (
            success_rate,
            zero_successes,
            below_success_threshold,
            success_rate_threshold,
        ) = _compute_success_metrics(
            completed=completed,
            failed=failed,
            callbacks_received=callbacks_received,
            settings=settings,
        )

        essays = await essay_repository.get_essays_for_cj_batch(
            session=session,
            cj_batch_id=batch_id,
        )
        essays_for_api = [
            EssayForComparison(
                id=essay.els_essay_id,
                text_content=essay.assessment_input_text,
                current_bt_score=essay.current_bt_score,
                is_anchor=bool(getattr(essay, "is_anchor", False)),
            )
            for essay in essays
        ]

        previous_scores = _extract_previous_scores(metadata)

        bt_scoring_results: list[BTScoringResult] = []
        bt_se_summary: dict[str, float | int] | None = None

        try:
            current_scores = await scoring_ranking.record_comparisons_and_update_scores(
                all_essays=essays_for_api,
                comparison_results=[],
                session_provider=session_provider,
                comparison_repository=comparison_repository,
                essay_repository=essay_repository,
                cj_batch_id=batch_id,
                correlation_id=correlation_id,
                scoring_result_container=bt_scoring_results,
            )
            if bt_scoring_results:
                bt_se_summary = bt_scoring_results[0].se_summary
        except HuleEduError as exc:  # pragma: no cover - domain error, treat as unstable
            logger.warning(
                "BT scoring failed while evaluating continuation; treating batch as unstable",
                extra={
                    **log_extra,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            # Fall back to previous scores (if any) so that metadata remains
            # consistent; stability_passed stays False so caps/success-rate
            # semantics drive finalization behaviour.
            current_scores = previous_scores or {}
        except Exception as exc:  # pragma: no cover - defensive recovery guard
            logger.error(
                "Failed to recompute scores after callbacks",
                extra={**log_extra, "error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            return

        ctx = await _build_continuation_context(
            batch_id=batch_id,
            batch_state=batch_state,
            metadata=metadata,
            settings=settings,
            current_scores=current_scores,
            previous_scores=previous_scores,
            callbacks_received=callbacks_received,
            pending_callbacks=pending_callbacks,
            completed=completed,
            failed=failed,
            denominator=denominator,
            max_pairs_cap=max_pairs_cap,
            pairs_submitted=pairs_submitted,
            pairs_remaining=pairs_remaining,
            budget_exhausted=budget_exhausted,
            callbacks_reached_cap=callbacks_reached_cap,
            success_rate=success_rate,
            success_rate_threshold=success_rate_threshold,
            zero_successes=zero_successes,
            below_success_threshold=below_success_threshold,
            bt_se_summary=bt_se_summary,
            comparison_repository=comparison_repository,
            session=session,
            log_extra=log_extra,
        )

    # Outside the DB session: persist metadata and drive actions.
    metadata_already_merged = False

    can_attempt_resampling = _can_attempt_resampling(ctx)
    # Select the appropriate resampling cap based on net size.
    resampling_cap = (
        ctx.small_net_resampling_cap if ctx.is_small_net else ctx.regular_batch_resampling_cap
    )
    if can_attempt_resampling and resampling_cap > 0 and ctx.resampling_pass_count < resampling_cap:
        metadata_updates = dict(ctx.metadata_updates)
        metadata_updates.update(
            {
                "max_possible_pairs": ctx.max_possible_pairs,
                "successful_pairs_count": ctx.successful_pairs_count,
                "unique_coverage_complete": ctx.unique_coverage_complete,
                "resampling_pass_count": ctx.resampling_pass_count + 1,
            }
        )
        await merge_batch_processing_metadata(
            session_provider=session_provider,
            cj_batch_id=batch_id,
            metadata_updates=metadata_updates,
            correlation_id=correlation_id,
        )
        metadata_already_merged = True

        submitted = await comparison_processing.request_additional_comparisons_for_batch(
            cj_batch_id=batch_id,
            session_provider=session_provider,
            batch_repository=batch_repository,
            essay_repository=essay_repository,
            comparison_repository=comparison_repository,
            instruction_repository=instruction_repository,
            llm_interaction=llm_interaction,
            matching_strategy=matching_strategy,
            orientation_strategy=orientation_strategy,
            settings=settings,
            correlation_id=correlation_id,
            log_extra=log_extra,
            llm_overrides_payload=llm_overrides_payload,
            config_overrides_payload=config_overrides_payload,
            original_request_payload=original_request_payload,
            mode=PairGenerationMode.RESAMPLING,
        )
        if submitted:
            return
        logger.info(
            "No additional comparisons enqueued during small-net Phase-2 resampling",
            extra={**log_extra, "pairs_remaining": ctx.pairs_remaining},
        )

    decision = decide(ctx)

    record_workflow_decision(ctx, decision)

    logger.info(
        "Continuation decision evaluated",
        extra={
            **log_extra,
            "decision": decision.value,
            "callbacks_received": ctx.callbacks_received,
            "denominator": ctx.denominator,
            "max_score_change": ctx.max_score_change,
            "success_rate": ctx.success_rate,
            "success_rate_threshold": ctx.success_rate_threshold,
            "callbacks_reached_cap": ctx.callbacks_reached_cap,
            "budget_exhausted": ctx.budget_exhausted,
            "pairs_remaining": ctx.pairs_remaining,
            "is_small_net": ctx.is_small_net,
            "small_net_cap_reached": ctx.small_net_cap_reached,
            "bt_se_inflated": ctx.bt_se_inflated,
            "comparison_coverage_sparse": ctx.comparison_coverage_sparse,
            "has_isolated_items": ctx.has_isolated_items,
        },
    )

    if not metadata_already_merged:
        if (
            can_attempt_resampling
            and resampling_cap > 0
            and ctx.resampling_pass_count >= resampling_cap
        ):
            if ctx.is_small_net:
                log_message = (
                    "Small-net Phase-2 resampling cap reached; falling back to finalization"
                )
            else:
                log_message = (
                    "Regular-batch resampling cap reached; falling back to continuation caps"
                )
            logger.info(
                log_message,
                extra={
                    **log_extra,
                    "expected_essay_count": ctx.expected_essay_count,
                    "resampling_pass_count": ctx.resampling_pass_count,
                    "small_net_phase2_entered": ctx.is_small_net,
                },
            )

        metadata_updates = dict(ctx.metadata_updates)
        metadata_updates.update(
            {
                "max_possible_pairs": ctx.max_possible_pairs,
                "successful_pairs_count": ctx.successful_pairs_count,
                "unique_coverage_complete": ctx.unique_coverage_complete,
                "resampling_pass_count": ctx.resampling_pass_count,
            }
        )
        await merge_batch_processing_metadata(
            session_provider=session_provider,
            cj_batch_id=batch_id,
            metadata_updates=metadata_updates,
            correlation_id=correlation_id,
        )

    if decision is ContinuationDecision.FINALIZE_FAILURE:
        logger.warning(
            "Finalizing batch as FAILED due to low success rate",
            extra={
                **log_extra,
                "callbacks_received": ctx.callbacks_received,
                "completed_comparisons": ctx.completed,
                "failed_comparisons": ctx.failed,
                "success_rate": ctx.success_rate,
                "success_rate_threshold": ctx.success_rate_threshold,
                "callbacks_reached_cap": ctx.callbacks_reached_cap,
                "budget_exhausted": ctx.budget_exhausted,
            },
        )
        if grade_projector is None:
            raise ValueError(
                "grade_projector is required for failure finalization. "
                "Please inject a GradeProjector instance via DI.",
            )

        finalizer = BatchFinalizer(
            session_provider=session_provider,
            batch_repository=batch_repository,
            comparison_repository=comparison_repository,
            essay_repository=essay_repository,
            event_publisher=event_publisher,
            content_client=content_client,
            settings=settings,
            grade_projector=grade_projector,
        )
        await finalizer.finalize_failure(
            batch_id=batch_id,
            correlation_id=correlation_id,
            log_extra=log_extra,
            failure_reason="low_success_rate",
            failure_details={
                "callbacks_received": ctx.callbacks_received,
                "completed_comparisons": ctx.completed,
                "failed_comparisons": ctx.failed,
                "success_rate": ctx.success_rate,
                "success_rate_threshold": ctx.success_rate_threshold,
                "callbacks_reached_cap": ctx.callbacks_reached_cap,
                "budget_exhausted": ctx.budget_exhausted,
            },
        )
        return

    if decision is ContinuationDecision.FINALIZE_SCORING:
        logger.info("Finalizing batch after stability/budget evaluation", extra=log_extra)
        if grade_projector is None:
            raise ValueError(
                "grade_projector is required for finalization. "
                "Please inject a GradeProjector instance via DI.",
            )

        finalizer = BatchFinalizer(
            session_provider=session_provider,
            batch_repository=batch_repository,
            comparison_repository=comparison_repository,
            essay_repository=essay_repository,
            event_publisher=event_publisher,
            content_client=content_client,
            settings=settings,
            grade_projector=grade_projector,
        )
        await finalizer.finalize_scoring(
            batch_id=batch_id,
            correlation_id=correlation_id,
            log_extra=log_extra,
        )
        return

    if decision is ContinuationDecision.REQUEST_MORE_COMPARISONS:
        submitted = await comparison_processing.request_additional_comparisons_for_batch(
            cj_batch_id=batch_id,
            session_provider=session_provider,
            batch_repository=batch_repository,
            essay_repository=essay_repository,
            comparison_repository=comparison_repository,
            instruction_repository=instruction_repository,
            llm_interaction=llm_interaction,
            matching_strategy=matching_strategy,
            orientation_strategy=orientation_strategy,
            settings=settings,
            correlation_id=correlation_id,
            log_extra=log_extra,
            llm_overrides_payload=llm_overrides_payload,
            config_overrides_payload=config_overrides_payload,
            original_request_payload=original_request_payload,
            mode=PairGenerationMode.COVERAGE,
        )
        if submitted:
            return
        logger.info(
            "No additional comparisons enqueued despite remaining budget after stability check",
            extra={**log_extra, "pairs_remaining": ctx.pairs_remaining},
        )
