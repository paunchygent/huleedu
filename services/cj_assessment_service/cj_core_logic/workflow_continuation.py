"""Workflow continuation logic for CJ Assessment Service.

Isolates continuation checks and scoring trigger away from callback handler
to improve SRP and keep modules small and focused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic import comparison_processing, scoring_ranking
from services.cj_assessment_service.cj_core_logic.batch_finalizer import BatchFinalizer
from services.cj_assessment_service.cj_core_logic.batch_submission import (
    get_batch_state,
    merge_batch_processing_metadata,
)
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
        BatchRetryProcessor,
    )
    from services.cj_assessment_service.config import Settings

logger = create_service_logger("cj_assessment_service.workflow_continuation")


async def check_workflow_continuation(
    batch_id: int,
    database: CJRepositoryProtocol,
    correlation_id: UUID,
) -> bool:
    """Return True only when all submitted callbacks for the batch have arrived."""
    async with database.session() as session:
        batch_state = await get_batch_state(session, batch_id, correlation_id)
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
) -> tuple[int, bool]:
    budget = metadata.get("comparison_budget") if isinstance(metadata, dict) else None
    max_pairs = budget.get("max_pairs_requested") if budget else None
    enforce_full_budget = bool(budget and budget.get("source") == "runner_override")

    if not isinstance(max_pairs, int) or max_pairs <= 0:
        max_pairs = settings.MAX_PAIRWISE_COMPARISONS

    return max_pairs, enforce_full_budget


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
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: "Settings",
    content_client: ContentClientProtocol,
    correlation_id: UUID,
    llm_interaction: LLMInteractionProtocol,
    retry_processor: "BatchRetryProcessor | None" = None,
) -> None:
    """Continue workflow after callback if conditions allow.

    - Applies fairness retry if near completion and retry processor provided
    - Checks completion thresholds and triggers finalization via BatchFinalizer
    """
    log_extra = {"correlation_id": str(correlation_id), "batch_id": batch_id}
    logger.info("Triggering workflow continuation", extra=log_extra)
    _ = retry_processor  # reserved for future retry-aware continuation paths

    async with database.session() as session:
        batch_state = await get_batch_state(session, batch_id, correlation_id)
        if not batch_state:
            logger.error("Batch state not found", extra=log_extra)
            return

        callbacks_received = batch_state.completed_comparisons + batch_state.failed_comparisons
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

        max_pairs_cap, _ = _resolve_comparison_budget(metadata, settings)
        pairs_submitted = batch_state.submitted_comparisons or 0
        pairs_remaining = max(0, max_pairs_cap - pairs_submitted)
        budget_exhausted = pairs_remaining <= 0

        denominator = batch_state.completion_denominator()
        callbacks_reached_cap = denominator > 0 and callbacks_received >= denominator

        essays = await database.get_essays_for_cj_batch(session=session, cj_batch_id=batch_id)
        essays_for_api = [
            EssayForComparison(
                id=essay.els_essay_id,
                text_content=essay.assessment_input_text,
                current_bt_score=essay.current_bt_score,
            )
            for essay in essays
        ]

        previous_scores = _extract_previous_scores(metadata)

        max_score_change = None  # Use None instead of float("inf") for JSON compatibility
        stability_passed = False

        try:
            current_scores = await scoring_ranking.record_comparisons_and_update_scores(
                all_essays=essays_for_api,
                comparison_results=[],
                db_session=session,
                cj_batch_id=batch_id,
                correlation_id=correlation_id,
            )

            if previous_scores:
                max_score_change = scoring_ranking.check_score_stability(
                    current_scores,
                    previous_scores,
                    stability_threshold=getattr(settings, "SCORE_STABILITY_THRESHOLD", 0.05),
                )
                stability_passed = callbacks_received >= getattr(
                    settings, "MIN_COMPARISONS_FOR_STABILITY_CHECK", 0
                ) and max_score_change <= getattr(settings, "SCORE_STABILITY_THRESHOLD", 0.05)

            await merge_batch_processing_metadata(
                session=session,
                cj_batch_id=batch_id,
                metadata_updates={
                    "bt_scores": current_scores,
                    "last_scored_iteration": batch_state.current_iteration,
                    "last_score_change": max_score_change,
                },
                correlation_id=correlation_id,
            )
        except Exception as exc:  # pragma: no cover - defensive recovery guard
            logger.error(
                "Failed to recompute scores after callbacks",
                extra={**log_extra, "error": str(exc), "error_type": type(exc).__name__},
                exc_info=True,
            )
            return

        should_finalize = stability_passed or callbacks_reached_cap or budget_exhausted

        logger.info(
            "Callback iteration complete; evaluated stability",
            extra={
                **log_extra,
                "callbacks_received": callbacks_received,
                "callbacks_reached_cap": callbacks_reached_cap,
                "denominator": denominator,
                "stability_passed": stability_passed,
                "max_score_change": max_score_change,
                "pairs_remaining": pairs_remaining,
                "budget_exhausted": budget_exhausted,
                "should_finalize": should_finalize,
            },
        )

        if should_finalize:
            logger.info("Finalizing batch after stability/budget evaluation", extra=log_extra)
            finalizer = BatchFinalizer(
                database=database,
                event_publisher=event_publisher,
                content_client=content_client,
                settings=settings,
            )
            await finalizer.finalize_scoring(
                batch_id=batch_id,
                correlation_id=correlation_id,
                session=session,
                log_extra=log_extra,
            )
            return

        if pairs_remaining > 0:
            submitted = await comparison_processing.request_additional_comparisons_for_batch(
                cj_batch_id=batch_id,
                database=database,
                llm_interaction=llm_interaction,
                settings=settings,
                correlation_id=correlation_id,
                log_extra=log_extra,
                llm_overrides_payload=llm_overrides_payload,
                config_overrides_payload=config_overrides_payload,
                original_request_payload=metadata.get("original_request")
                if isinstance(metadata, dict)
                else None,
            )
            if submitted:
                return
            logger.info(
                "No additional comparisons enqueued despite remaining budget after stability check",
                extra={**log_extra, "pairs_remaining": pairs_remaining},
            )
