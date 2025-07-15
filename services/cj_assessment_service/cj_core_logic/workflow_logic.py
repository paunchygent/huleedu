"""Workflow state machine logic for CJ Assessment Service.

This module handles LLM callback processing and batch workflow progression
with concurrent-safe state transitions and optimistic locking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.status_enums import CJBatchStateEnum
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_db import CJBatchState, ComparisonPair
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
)

logger = create_service_logger("cj_assessment_service.workflow_logic")


async def continue_cj_assessment_workflow(
    comparison_result: LLMComparisonResultV1,
    correlation_id: UUID,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
) -> None:
    """Process LLM callback and advance batch workflow state machine.

    Main entry point for processing comparison callbacks from LLM Provider Service.
    Coordinates state updates with optimistic locking to prevent race conditions.

    Args:
        comparison_result: The LLM comparison result callback data
        correlation_id: Request correlation ID for tracing
        database: Database access protocol implementation
        event_publisher: Event publisher protocol implementation
        settings: Application settings
    """
    # Get business metrics
    business_metrics = get_business_metrics()
    comparisons_total_metric = business_metrics.get("cj_comparisons_total")
    batch_progress_metric = business_metrics.get("cj_batch_progress_percentage")
    batch_duration_metric = business_metrics.get("cj_batch_processing_duration_seconds")
    score_stability_metric = business_metrics.get("cj_score_stability_changes")
    iterations_per_batch_metric = business_metrics.get("cj_iterations_per_batch")

    log_extra = {
        "correlation_id": str(correlation_id),
        "request_id": comparison_result.request_id,
        "is_error": comparison_result.is_error,
    }

    logger.info(
        f"Processing LLM callback for request {comparison_result.request_id}",
        extra=log_extra,
    )

    try:
        # Step 1: Update the comparison result in database
        batch_id = await _update_comparison_result(
            comparison_result=comparison_result,
            database=database,
            correlation_id=correlation_id,
        )

        if batch_id is None:
            logger.warning(
                f"No comparison pair found for request_id {comparison_result.request_id}",
                extra=log_extra,
            )
            return

        log_extra["batch_id"] = batch_id

        # Record comparison metrics
        if comparisons_total_metric:
            if comparison_result.is_error:
                comparisons_total_metric.labels(status="failed").inc()
            else:
                comparisons_total_metric.labels(status="completed").inc()

        # Step 2: Update batch state and decide next action
        next_action = await _update_batch_state_and_decide(
            batch_id=batch_id,
            database=database,
            settings=settings,
            correlation_id=correlation_id,
        )

        log_extra["next_action"] = next_action
        logger.info(
            f"Batch {batch_id} state updated, next action: {next_action}",
            extra=log_extra,
        )

        # Step 3: Execute the decided action
        await _execute_action(
            action=next_action,
            batch_id=batch_id,
            database=database,
            event_publisher=event_publisher,
            settings=settings,
            correlation_id=correlation_id,
            batch_progress_metric=batch_progress_metric,
            batch_duration_metric=batch_duration_metric,
            score_stability_metric=score_stability_metric,
            iterations_per_batch_metric=iterations_per_batch_metric,
        )

    except Exception as e:
        logger.error(
            f"Error in workflow continuation: {str(e)}",
            extra={
                **log_extra,
                "exception_type": type(e).__name__,
            },
            exc_info=True,
        )
        # Don't re-raise - we want to acknowledge the message to prevent reprocessing


async def _update_comparison_result(
    comparison_result: LLMComparisonResultV1,
    database: CJRepositoryProtocol,
    correlation_id: UUID,
) -> int | None:
    """Update comparison pair with LLM callback result.

    Finds ComparisonPair by request_correlation_id and updates with
    success data or error details. Implements idempotency check.

    Args:
        comparison_result: The LLM comparison result callback data
        database: Database access protocol implementation
        correlation_id: Request correlation ID for tracing

    Returns:
        The batch_id of the updated comparison, or None if not found
    """
    async with database.session() as session:
        # Find comparison pair by request correlation ID
        stmt = select(ComparisonPair).where(
            ComparisonPair.request_correlation_id == UUID(comparison_result.request_id)
        )
        result = await session.execute(stmt)
        comparison_pair = result.scalar_one_or_none()

        if comparison_pair is None:
            return None

        # Check idempotency - skip if already has result
        if comparison_pair.winner is not None:
            logger.info(
                f"Comparison pair {comparison_pair.id} already has result, skipping update",
                extra={
                    "correlation_id": str(correlation_id),
                    "request_id": comparison_result.request_id,
                    "existing_winner": comparison_pair.winner,
                },
            )
            return comparison_pair.cj_batch_id

        # Update with result or error
        comparison_pair.completed_at = datetime.now(UTC)

        if comparison_result.is_error and comparison_result.error_detail:
            # Update error fields
            comparison_pair.winner = "error"
            comparison_pair.error_code = comparison_result.error_detail.error_code
            comparison_pair.error_correlation_id = comparison_result.error_detail.correlation_id
            comparison_pair.error_timestamp = comparison_result.error_detail.timestamp
            comparison_pair.error_service = comparison_result.error_detail.service
            comparison_pair.error_details = comparison_result.error_detail.details

            logger.warning(
                f"Updated comparison pair {comparison_pair.id} with error result",
                extra={
                    "correlation_id": str(correlation_id),
                    "error_code": comparison_result.error_detail.error_code.value,
                },
            )
        else:
            # Update success fields
            comparison_pair.winner = (
                comparison_result.winner.value if comparison_result.winner else None
            )
            comparison_pair.confidence = comparison_result.confidence
            comparison_pair.justification = comparison_result.justification
            # Raw response not available in current model
            comparison_pair.raw_llm_response = None

            # Store additional metadata
            comparison_pair.processing_metadata = {
                "provider": comparison_result.provider.value,
                "model": comparison_result.model,
                "response_time_ms": comparison_result.response_time_ms,
                "token_usage": {
                    "prompt_tokens": comparison_result.token_usage.prompt_tokens,
                    "completion_tokens": comparison_result.token_usage.completion_tokens,
                    "total_tokens": comparison_result.token_usage.total_tokens,
                },
                "cost_estimate": comparison_result.cost_estimate,
            }

            logger.info(
                f"Updated comparison pair {comparison_pair.id} with success result",
                extra={
                    "correlation_id": str(correlation_id),
                    "winner": comparison_pair.winner,
                    "confidence": comparison_pair.confidence,
                },
            )

        await session.commit()
        return comparison_pair.cj_batch_id


async def _update_batch_state_and_decide(
    batch_id: int,
    database: CJRepositoryProtocol,
    settings: Settings,
    correlation_id: UUID,
) -> str:
    """Update batch state with optimistic locking and decide next action.

    Uses SELECT FOR UPDATE to lock CJBatchState row, updates counters,
    calculates progress, and determines state transitions.

    Args:
        batch_id: The CJ batch ID to update
        database: Database access protocol implementation
        settings: Application settings
        correlation_id: Request correlation ID for tracing

    Returns:
        Action string: "continue", "check_stability", "partial_scoring", "complete", or "failed"
    """
    async with database.session() as session:
        # Use SELECT FOR UPDATE to lock the batch state row
        stmt = select(CJBatchState).where(CJBatchState.batch_id == batch_id).with_for_update()
        result = await session.execute(stmt)
        batch_state = result.scalar_one_or_none()

        if batch_state is None:
            logger.error(
                f"No batch state found for batch_id {batch_id}",
                extra={"correlation_id": str(correlation_id), "batch_id": batch_id},
            )
            return "failed"

        # Update counters
        batch_state.completed_comparisons += 1
        batch_state.last_activity_at = datetime.now(UTC)

        # Calculate progress percentage with zero-division protection
        if batch_state.total_comparisons > 0:
            progress_pct = (batch_state.completed_comparisons / batch_state.total_comparisons) * 100
        else:
            progress_pct = 0.0

        # Check if this was an error result
        # We need to query for failed comparisons count
        failed_stmt = select(ComparisonPair).where(
            ComparisonPair.cj_batch_id == batch_id, ComparisonPair.winner == "error"
        )
        failed_result = await session.execute(failed_stmt)
        failed_comparisons = len(failed_result.scalars().all())
        batch_state.failed_comparisons = failed_comparisons

        # Calculate failure rate
        if batch_state.completed_comparisons > 0:
            failure_rate = (
                batch_state.failed_comparisons / batch_state.completed_comparisons
            ) * 100
        else:
            failure_rate = 0.0

        log_extra = {
            "correlation_id": str(correlation_id),
            "batch_id": batch_id,
            "completed": batch_state.completed_comparisons,
            "total": batch_state.total_comparisons,
            "failed": batch_state.failed_comparisons,
            "progress_pct": progress_pct,
            "failure_rate": failure_rate,
            "current_state": batch_state.state.value,
        }

        logger.info(
            f"Batch {batch_id} progress: {progress_pct:.1f}% "
            f"({batch_state.completed_comparisons}/{batch_state.total_comparisons})",
            extra=log_extra,
        )

        # Decide next action based on state and progress
        if batch_state.state == CJBatchStateEnum.CANCELLED:
            return "cancelled"

        # Check failure threshold (e.g., >20% failures)
        failure_threshold = getattr(settings, "MAX_FAILURE_RATE_PCT", 20.0)
        if failure_rate > failure_threshold:
            batch_state.state = CJBatchStateEnum.FAILED
            await session.commit()
            return "failed"

        # Check if all comparisons are complete
        if batch_state.completed_comparisons >= batch_state.total_comparisons:
            batch_state.state = CJBatchStateEnum.COMPLETED
            await session.commit()
            return "complete"

        # Check if we should do partial scoring
        if (
            progress_pct >= batch_state.completion_threshold_pct
            and not batch_state.partial_scoring_triggered
        ):
            batch_state.partial_scoring_triggered = True
            await session.commit()
            return "partial_scoring"

        # Check if we should check score stability (every N comparisons)
        stability_check_interval = getattr(settings, "STABILITY_CHECK_INTERVAL", 10)
        if batch_state.completed_comparisons % stability_check_interval == 0:
            # Check if scores have stabilized
            is_stable = await _check_score_stability(
                batch_state=batch_state,
                session=session,
                settings=settings,
                correlation_id=correlation_id,
            )
            if is_stable:
                batch_state.state = CJBatchStateEnum.COMPLETED
                await session.commit()
                return "complete"
            return "check_stability"

        # Default: continue processing
        await session.commit()
        return "continue"


async def _check_score_stability(
    batch_state: CJBatchState,
    session: AsyncSession,
    settings: Settings,
    correlation_id: UUID,
) -> bool:
    """Check if Bradley-Terry scores have converged.

    Compares current scores with previous iteration to determine
    if maximum score change is below stability threshold.

    Args:
        batch_state: The batch state object
        session: Active database session
        settings: Application settings
        correlation_id: Request correlation ID for tracing

    Returns:
        True if scores are stable, False otherwise
    """
    # Get previous scores from processing metadata
    processing_metadata = batch_state.processing_metadata or {}
    previous_scores = processing_metadata.get("previous_scores", {})

    if not previous_scores:
        # First stability check, no previous scores
        logger.info(
            f"First stability check for batch {batch_state.batch_id}, no previous scores",
            extra={"correlation_id": str(correlation_id), "batch_id": batch_state.batch_id},
        )
        return False

    # TODO: Calculate current scores - placeholder for now
    # This would typically call a scoring function that computes Bradley-Terry scores
    # from all completed comparisons in the batch
    current_scores: dict[str, float] = {}  # Placeholder - should be calculated from comparisons

    # For now, simulate score calculation
    logger.warning(
        "TODO: Implement actual Bradley-Terry score calculation",
        extra={"correlation_id": str(correlation_id), "batch_id": batch_state.batch_id},
    )

    # Suppress unused session warning - it will be used when score calculation is implemented
    _ = session

    # Calculate maximum score change
    max_change = 0.0
    for essay_id, current_score in current_scores.items():
        if essay_id in previous_scores:
            change = abs(current_score - previous_scores[essay_id])
            max_change = max(max_change, change)

    # Get stability threshold from settings
    stability_threshold = getattr(settings, "SCORE_STABILITY_THRESHOLD", 0.05)

    # Store current scores for next iteration
    if processing_metadata is None:
        processing_metadata = {}
    processing_metadata["previous_scores"] = current_scores
    processing_metadata["last_stability_check"] = datetime.now(UTC).isoformat()
    processing_metadata["max_score_change"] = max_change
    batch_state.processing_metadata = processing_metadata

    is_stable = max_change < stability_threshold

    # Record score stability metric
    business_metrics = get_business_metrics()
    score_stability_metric = business_metrics.get("cj_score_stability_changes")
    if score_stability_metric:
        score_stability_metric.observe(max_change)

    logger.info(
        f"Stability check for batch {batch_state.batch_id}: max_change={max_change:.4f}, "
        f"threshold={stability_threshold}, stable={is_stable}",
        extra={
            "correlation_id": str(correlation_id),
            "batch_id": batch_state.batch_id,
            "max_change": max_change,
            "is_stable": is_stable,
        },
    )

    return is_stable


async def _execute_action(
    action: str,
    batch_id: int,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
    correlation_id: UUID,
    batch_progress_metric: Any = None,
    batch_duration_metric: Any = None,
    score_stability_metric: Any = None,
    iterations_per_batch_metric: Any = None,
) -> None:
    """Execute the decided workflow action.

    Routes to appropriate handlers based on action string.

    Args:
        action: Action to execute (continue, check_stability, partial_scoring, complete, failed)
        batch_id: The CJ batch ID
        database: Database access protocol implementation
        event_publisher: Event publisher protocol implementation
        settings: Application settings
        correlation_id: Request correlation ID for tracing
        batch_progress_metric: Optional Prometheus histogram for batch progress
        batch_duration_metric: Optional Prometheus histogram for batch duration
        score_stability_metric: Optional Prometheus histogram for score stability
        iterations_per_batch_metric: Optional Prometheus histogram for iterations
    """
    log_extra = {
        "correlation_id": str(correlation_id),
        "batch_id": batch_id,
        "action": action,
    }

    if action == "continue":
        # Normal case - just log and return
        logger.info(
            f"Batch {batch_id} continuing normal processing",
            extra=log_extra,
        )
        return

    elif action == "check_stability":
        # Stability was already checked in _update_batch_state_and_decide
        logger.info(
            f"Batch {batch_id} completed stability check",
            extra=log_extra,
        )
        # TODO: Could trigger generation of more comparison pairs if needed
        return

    elif action == "partial_scoring":
        logger.info(
            f"Triggering partial scoring for batch {batch_id}",
            extra=log_extra,
        )
        # TODO: Implement partial scoring and result publication
        # await calculate_and_publish_partial_scores(
        #     batch_id=batch_id,
        #     database=database,
        #     event_publisher=event_publisher,
        #     correlation_id=correlation_id,
        # )
        logger.warning(
            "TODO: Implement calculate_and_publish_partial_scores",
            extra=log_extra,
        )
        # Suppress unused warnings - they will be used when implementation is added
        _ = (database, event_publisher, settings)
        return

    elif action == "complete":
        logger.info(
            f"Batch {batch_id} completed, publishing final scores",
            extra=log_extra,
        )

        # Record batch completion metrics
        async with database.session() as session:
            stmt = select(CJBatchState).where(CJBatchState.batch_id == batch_id)
            result = await session.execute(stmt)
            batch_state = result.scalar_one_or_none()

            if batch_state:
                # Record batch progress percentage
                if batch_progress_metric and batch_state.total_comparisons > 0:
                    progress_pct = (
                        batch_state.completed_comparisons / batch_state.total_comparisons
                    ) * 100
                    batch_progress_metric.observe(progress_pct)

                # Record batch processing duration
                if batch_duration_metric and batch_state.processing_metadata:
                    start_time_str = batch_state.processing_metadata.get("start_time")
                    if start_time_str:
                        from datetime import datetime

                        start_time = datetime.fromisoformat(start_time_str)
                        duration = (datetime.now(UTC) - start_time).total_seconds()
                        batch_duration_metric.observe(duration)

                # Record iterations per batch
                if iterations_per_batch_metric:
                    iterations = batch_state.current_iteration
                    iterations_per_batch_metric.observe(iterations)

        # TODO: Implement final score calculation and publication
        # await calculate_and_publish_final_scores(
        #     batch_id=batch_id,
        #     database=database,
        #     event_publisher=event_publisher,
        #     correlation_id=correlation_id,
        # )
        logger.warning(
            "TODO: Implement calculate_and_publish_final_scores",
            extra=log_extra,
        )
        return

    elif action == "failed":
        logger.error(
            f"Batch {batch_id} failed, publishing failure event",
            extra=log_extra,
        )
        # TODO: Implement failure event publication
        # await publish_batch_failure(
        #     batch_id=batch_id,
        #     event_publisher=event_publisher,
        #     correlation_id=correlation_id,
        # )
        logger.warning(
            "TODO: Implement publish_batch_failure",
            extra=log_extra,
        )
        return

    elif action == "cancelled":
        logger.info(
            f"Batch {batch_id} was cancelled, no further action",
            extra=log_extra,
        )
        return

    else:
        logger.error(
            f"Unknown action '{action}' for batch {batch_id}",
            extra=log_extra,
        )
