"""Workflow continuation logic for CJ Assessment Service.

Isolates continuation checks and scoring trigger away from callback handler
to improve SRP and keep modules small and focused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import func, select

from services.cj_assessment_service.cj_core_logic import comparison_processing
from services.cj_assessment_service.cj_core_logic.batch_completion_checker import (
    BatchCompletionChecker,
)
from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.cj_core_logic.batch_finalizer import BatchFinalizer
from services.cj_assessment_service.cj_core_logic.batch_submission import get_batch_state
from services.cj_assessment_service.cj_core_logic.callback_state_manager import (
    check_batch_completion_conditions,
)
from services.cj_assessment_service.models_db import ComparisonPair
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
    """Determine whether this callback should trigger continuation.

    CURRENT:
    - Uses completed comparison counts and completion thresholds only.

    FUTURE:
    - For bundled, stability-driven mode, continuation should factor in
      BT score stability via comparison_processing._check_iteration_stability.
    - See TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION*.md.
    """
    async with database.session() as session:
        # Get batch state to check total expected comparisons
        batch_state = await get_batch_state(session, batch_id, correlation_id)
        if not batch_state:
            logger.warning(
                "Batch state not found for batch",
                extra={"correlation_id": str(correlation_id), "batch_id": batch_id},
            )
            return False

        # Get count of completed comparisons for this batch
        completed_count_stmt = (
            select(func.count())
            .select_from(ComparisonPair)
            .where(
                ComparisonPair.cj_batch_id == batch_id,
                ComparisonPair.winner.in_(["essay_a", "essay_b"]),
            )
        )
        completed_count = (await session.execute(completed_count_stmt)).scalar_one()

        # Support both periodic continuation (every 5) and threshold-based
        should_continue: bool = False
        denominator = batch_state.completion_denominator()
        if denominator > 0:
            # Periodic continuation every 5 completions
            if completed_count > 0 and completed_count % 5 == 0:
                should_continue = True
            # Also check completion threshold if configured
            if (
                not should_continue
                and batch_state.completion_threshold_pct
                and batch_state.completion_threshold_pct > 0
            ):
                completion_percentage = (completed_count / denominator) * 100
                if completion_percentage >= batch_state.completion_threshold_pct:
                    should_continue = True

        logger.info(
            "Continuation check computed",
            extra={
                "correlation_id": str(correlation_id),
                "batch_id": batch_id,
                "completed_pairs": completed_count,
                "total_comparisons": batch_state.total_comparisons,
                "total_budget": batch_state.total_budget,
                "completion_denominator": denominator,
                "should_continue": should_continue,
            },
        )

        return should_continue


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

    async with database.session() as session:
        # Ensure valid comparisons exist (for observability)
        valid_comparisons_stmt = (
            select(func.count())
            .select_from(ComparisonPair)
            .where(
                ComparisonPair.cj_batch_id == batch_id,
                ComparisonPair.winner.isnot(None),
                ComparisonPair.winner != "error",
            )
        )
        valid_comparisons = (await session.execute(valid_comparisons_stmt)).scalar_one()

        logger.info(
            "Valid comparisons found",
            extra={**log_extra, "valid_comparisons": valid_comparisons},
        )

        # If we are close to completion, attempt fairness retry to clean up failures
        batch_is_completing = await check_batch_completion_conditions(
            batch_id=batch_id,
            database=database,
            session=session,
            correlation_id=correlation_id,
        )
        if batch_is_completing and retry_processor:
            logger.info(
                "Processing remaining failed comparisons for fairness",
                extra=log_extra,
            )
            try:
                remaining_result = await retry_processor.process_remaining_failed_comparisons(
                    cj_batch_id=batch_id,
                    correlation_id=correlation_id,
                )
                if remaining_result:
                    logger.info(
                        "Fairness retries submitted",
                        extra={
                            **log_extra,
                            "remaining_comparisons_processed": remaining_result.total_submitted,
                        },
                    )
                else:
                    logger.info("No failed comparisons to retry", extra=log_extra)
            except Exception as e:
                logger.error(
                    f"Fairness retry failed: {e}",
                    extra={**log_extra, "error": str(e)},
                    exc_info=True,
                )

        # Fetch batch_state to pull processing_metadata for overrides
        batch_state = await get_batch_state(session, batch_id, correlation_id)
        if not batch_state:
            logger.error("Batch state not found", extra=log_extra)
            return

        metadata = (
            batch_state.processing_metadata
            if isinstance(batch_state.processing_metadata, dict)
            else {}
        )
        config_overrides_payload = (
            metadata.get("config_overrides") if isinstance(metadata, dict) else None
        )
        config_overrides = None
        if isinstance(config_overrides_payload, dict):
            config_overrides = BatchConfigOverrides(**config_overrides_payload)

        llm_overrides_payload = (
            metadata.get("llm_overrides") if isinstance(metadata, dict) else None
        )

        max_pairs_cap, enforce_full_budget = _resolve_comparison_budget(metadata, settings)
        pairs_submitted = batch_state.total_comparisons or 0
        pairs_remaining = max(0, max_pairs_cap - pairs_submitted)
        budget_exhausted = pairs_remaining <= 0

        # Check completion threshold and trigger finalization
        completion_checker = BatchCompletionChecker(database=database)

        is_complete = await completion_checker.check_batch_completion(
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
            config_overrides=config_overrides,
        )

        should_request_more = pairs_remaining > 0 and (not is_complete or enforce_full_budget)

        # TODO[TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION]:
        # For bundled, stability-driven mode, replace or augment this
        # completion-rate logic with a stability-based decision using
        # BT scores and _check_iteration_stability().

        if should_request_more:
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
                "No additional comparisons enqueued despite remaining budget; "
                "proceeding to finalization check",
                extra={**log_extra, "pairs_remaining": pairs_remaining},
            )

        if not is_complete and budget_exhausted:
            logger.info(
                "Comparison budget exhausted; finalizing batch despite incomplete threshold",
                extra=log_extra,
            )
            is_complete = True

        if is_complete:
            logger.info("Completion threshold reached; finalizing scoring", extra=log_extra)
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
