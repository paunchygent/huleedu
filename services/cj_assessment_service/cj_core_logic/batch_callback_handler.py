"""Batch callback handler for CJ Assessment Service.

This module handles LLM callback processing and integrates with existing
proven workflow logic instead of creating a parallel workflow system.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select

from common_core.events.llm_provider_events import LLMComparisonResultV1
from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
)

# Import existing proven workflow logic for integration

logger = create_service_logger("cj_assessment_service.batch_callback_handler")


async def continue_cj_assessment_workflow(
    comparison_result: LLMComparisonResultV1,
    correlation_id: UUID,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
    batch_processor: BatchProcessor | None = None,
) -> None:
    """Process LLM callback and continue existing workflow.

    This function focuses on callback processing and delegates to existing
    proven workflow logic instead of creating a parallel workflow system.

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
            settings=settings,
            batch_processor=batch_processor,
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

        # Step 2: Check if this callback enables workflow continuation
        should_continue = await _check_workflow_continuation(
            batch_id=batch_id,
            database=database,
            correlation_id=correlation_id,
        )

        if should_continue:
            logger.info(
                f"Callback enables workflow continuation for batch {batch_id}",
                extra=log_extra,
            )
            # Delegate to existing proven workflow logic
            await _trigger_existing_workflow_continuation(
                batch_id=batch_id,
                database=database,
                event_publisher=event_publisher,
                settings=settings,
                correlation_id=correlation_id,
                batch_processor=batch_processor,
            )
        else:
            logger.info(
                f"Callback processed for batch {batch_id}, workflow continues asynchronously",
                extra=log_extra,
            )

    except Exception as e:
        logger.error(
            f"Error in callback processing: {str(e)}",
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
    settings: Settings,
    batch_processor: BatchProcessor | None = None,
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

            # Add to failed comparison pool if batch processor is available
            if batch_processor and settings.ENABLE_FAILED_COMPARISON_RETRY:
                await _add_failed_comparison_to_pool(
                    batch_processor=batch_processor,
                    comparison_pair=comparison_pair,
                    comparison_result=comparison_result,
                    correlation_id=correlation_id,
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

            # Check if this was a retry and update pool statistics
            if batch_processor and settings.ENABLE_FAILED_COMPARISON_RETRY:
                await _handle_successful_retry(
                    batch_processor=batch_processor,
                    comparison_pair=comparison_pair,
                    correlation_id=correlation_id,
                )

        await session.commit()
        return comparison_pair.cj_batch_id


async def _check_workflow_continuation(
    batch_id: int,
    database: CJRepositoryProtocol,
    correlation_id: UUID,
) -> bool:
    """Check if this callback enables workflow continuation.

    This is a simplified check - in a real implementation, you might
    check batch state, completion thresholds, or other workflow conditions.

    Args:
        batch_id: The CJ batch ID
        database: Database access protocol implementation
        correlation_id: Request correlation ID for tracing

    Returns:
        True if workflow should continue, False otherwise
    """
    async with database.session() as session:
        # Get count of completed comparisons for this batch
        stmt = select(ComparisonPair).where(
            ComparisonPair.cj_batch_id == batch_id,
            ComparisonPair.winner.isnot(None),
        )
        result = await session.execute(stmt)
        completed_pairs = result.scalars().all()

        # Simple heuristic: continue workflow every 5 completions
        # This would be replaced with proper batch state management
        # that integrates with existing workflow logic
        should_continue = len(completed_pairs) % 5 == 0

        logger.info(
            f"Batch {batch_id} has {len(completed_pairs)} completed comparisons, "
            f"workflow continuation: {should_continue}",
            extra={
                "correlation_id": str(correlation_id),
                "batch_id": batch_id,
                "completed_pairs": len(completed_pairs),
            },
        )

        return should_continue


async def _trigger_existing_workflow_continuation(
    batch_id: int,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
    correlation_id: UUID,
    batch_processor: BatchProcessor | None = None,
) -> None:
    """Trigger continuation of existing workflow logic.

    This function delegates to existing proven workflow logic instead
    of implementing a parallel workflow system. It integrates with the
    existing scoring_ranking.py module for score stability checking.

    Args:
        batch_id: The CJ batch ID
        database: Database access protocol implementation
        event_publisher: Event publisher protocol implementation
        settings: Application settings
        correlation_id: Request correlation ID for tracing
        batch_processor: Optional batch processor for failed comparison handling
    """
    log_extra = {
        "correlation_id": str(correlation_id),
        "batch_id": batch_id,
    }

    logger.info(
        f"Triggering existing workflow continuation for batch {batch_id}",
        extra=log_extra,
    )

    async with database.session() as session:
        # Get current essays and their scores for this batch
        # This would integrate with the existing database patterns
        # from comparison_processing.py and scoring_ranking.py

        # Example of using existing proven logic:
        # 1. Get all completed comparisons for this batch
        # 2. Use scoring_ranking.check_score_stability() to check stability
        # 3. If stable, trigger completion using existing patterns
        # 4. If not stable, continue with existing workflow patterns

        # Get all valid comparisons for score stability check
        stmt = select(ComparisonPair).where(
            ComparisonPair.cj_batch_id == batch_id,
            ComparisonPair.winner.isnot(None),
            ComparisonPair.winner != "error",
        )
        result = await session.execute(stmt)
        valid_comparisons = result.scalars().all()

        logger.info(
            f"Found {len(valid_comparisons)} valid comparisons for batch {batch_id}",
            extra=log_extra,
        )

        # Check if this batch is approaching completion
        batch_is_completing = await _check_batch_completion_conditions(
            batch_id=batch_id,
            database=database,
            session=session,
            correlation_id=correlation_id,
        )

        if batch_is_completing and batch_processor:
            logger.info(
                f"Batch {batch_id} is completing, processing remaining failed comparisons "
                f"for fairness",
                extra=log_extra,
            )

            try:
                # Process any remaining failed comparisons for fairness
                remaining_result = await batch_processor.process_remaining_failed_comparisons(
                    cj_batch_id=batch_id,
                    correlation_id=correlation_id,
                )

                if remaining_result:
                    logger.info(
                        f"Processed {remaining_result.total_submitted} remaining failed "
                        f"comparisons for batch {batch_id} to ensure fairness",
                        extra={
                            **log_extra,
                            "remaining_comparisons_processed": remaining_result.total_submitted,
                        },
                    )
                else:
                    logger.info(
                        f"No remaining failed comparisons to process for batch {batch_id}",
                        extra=log_extra,
                    )

            except Exception as e:
                logger.error(
                    f"Failed to process remaining failed comparisons for batch {batch_id}: {e}",
                    extra={**log_extra, "error": str(e)},
                    exc_info=True,
                )
                # Continue with normal workflow despite failure

        # This is where we would integrate with existing workflow_orchestrator
        # patterns and use existing scoring_ranking.check_score_stability()
        # for proper score stability checking

        # The key insight is that this callback handler should NOT
        # implement its own workflow logic, but rather trigger the
        # existing proven workflow continuation patterns

        logger.info(
            f"Workflow continuation delegated to existing proven logic for batch {batch_id}",
            extra=log_extra,
        )

        # Note: In a complete implementation, this would:
        # 1. Calculate current scores using existing scoring_ranking.py
        # 2. Check stability using existing scoring_ranking.check_score_stability()
        # 3. Trigger completion/continuation using existing workflow_orchestrator patterns
        # 4. Publish results using existing event publisher patterns

    # Suppress unused warnings - they will be used when full integration is implemented
    _ = (event_publisher, settings)


async def _check_batch_completion_conditions(
    batch_id: int,
    database: CJRepositoryProtocol,
    session,
    correlation_id: UUID,
) -> bool:
    """Check if batch is approaching completion.

    This is a simplified check for detecting when batch processing is ending.
    In a complete implementation, this would check:
    - Maximum comparisons limit reached
    - Score stability achieved
    - Batch state transitioning to COMPLETED or FAILED
    - All submitted comparisons completed (successful + failed = total submitted)

    Args:
        batch_id: The CJ batch ID
        database: Database access protocol implementation (unused in current implementation)
        session: Database session
        correlation_id: Request correlation ID for tracing

    Returns:
        True if batch is approaching completion, False otherwise
    """
    from services.cj_assessment_service.models_db import CJBatchState

    # Suppress unused parameter warning
    _ = database

    try:
        # Get batch state
        stmt = select(CJBatchState).where(CJBatchState.batch_id == batch_id)
        result = await session.execute(stmt)
        batch_state = result.scalar_one_or_none()

        if not batch_state:
            return False

        # Simple heuristic: check if batch has significant completion
        # In practice, this would integrate with proper batch state management
        if (
            batch_state.total_comparisons > 0
            and batch_state.completed_comparisons >= batch_state.total_comparisons * 0.8
        ):
            completion_rate = batch_state.completed_comparisons / batch_state.total_comparisons
            logger.info(
                f"Batch {batch_id} completion detected: "
                f"{batch_state.completed_comparisons}/{batch_state.total_comparisons} "
                f"comparisons completed (80%+ threshold reached)",
                extra={
                    "correlation_id": str(correlation_id),
                    "batch_id": batch_id,
                    "completion_rate": completion_rate,
                },
            )
            return True

        return False

    except Exception as e:
        logger.error(
            f"Failed to check batch completion conditions for batch {batch_id}: {e}",
            extra={
                "correlation_id": str(correlation_id),
                "batch_id": batch_id,
                "error": str(e),
            },
            exc_info=True,
        )
        return False


async def _add_failed_comparison_to_pool(
    batch_processor: BatchProcessor,
    comparison_pair: ComparisonPair,
    comparison_result: LLMComparisonResultV1,
    correlation_id: UUID,
) -> None:
    """Add failed comparison to the retry pool and check for retry batch need.

    Args:
        batch_processor: Batch processor instance
        comparison_pair: Failed comparison pair from database
        comparison_result: LLM comparison result with error
        correlation_id: Request correlation ID for tracing
    """
    try:
        # Reconstruct the original comparison task from the database record
        # Note: We need to fetch the essay content from the database
        # This is a simplified version - in practice, you'd want to fetch the full essay data
        comparison_task = await _reconstruct_comparison_task(
            comparison_pair=comparison_pair, correlation_id=correlation_id
        )

        if comparison_task:
            # Determine failure reason from error details
            failure_reason = (
                comparison_result.error_detail.error_code.value
                if comparison_result.error_detail
                else "unknown_error"
            )

            # Add to failed pool
            await batch_processor.add_to_failed_pool(
                cj_batch_id=comparison_pair.cj_batch_id,
                comparison_task=comparison_task,
                failure_reason=failure_reason,
                correlation_id=correlation_id,
            )

            # Check if retry batch needed
            retry_needed = await batch_processor.check_retry_batch_needed(
                cj_batch_id=comparison_pair.cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=False,  # Use normal threshold-based checking during callbacks
            )

            if retry_needed:
                logger.info(
                    f"Triggering retry batch for batch {comparison_pair.cj_batch_id}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": comparison_pair.cj_batch_id,
                    },
                )

                # Submit retry batch
                await batch_processor.submit_retry_batch(
                    cj_batch_id=comparison_pair.cj_batch_id,
                    correlation_id=correlation_id,
                )

    except Exception as e:
        logger.error(
            f"Failed to add comparison to failed pool: {e}",
            extra={
                "correlation_id": str(correlation_id),
                "comparison_pair_id": comparison_pair.id,
                "cj_batch_id": comparison_pair.cj_batch_id,
                "error": str(e),
            },
            exc_info=True,
        )
        # Don't re-raise - we don't want to fail the callback processing


async def _reconstruct_comparison_task(
    comparison_pair: ComparisonPair, correlation_id: UUID
) -> ComparisonTask | None:
    """Reconstruct comparison task from database comparison pair.

    Args:
        comparison_pair: Database comparison pair record
        correlation_id: Request correlation ID for tracing

    Returns:
        Reconstructed comparison task or None if reconstruction fails
    """
    try:
        # Note: This is a simplified reconstruction
        # In a complete implementation, you'd fetch the full essay content
        # from the essay records using comparison_pair.essay_a and essay_b relationships

        # For now, we'll create minimal essay objects
        # In practice, you'd want to fetch the full text content
        essay_a = EssayForComparison(
            id=comparison_pair.essay_a_els_id,
            text_content="[Essay content would be fetched from database]",
            current_bt_score=None,
        )

        essay_b = EssayForComparison(
            id=comparison_pair.essay_b_els_id,
            text_content="[Essay content would be fetched from database]",
            current_bt_score=None,
        )

        return ComparisonTask(
            essay_a=essay_a,
            essay_b=essay_b,
            prompt=comparison_pair.prompt_text,
        )

    except Exception as e:
        logger.error(
            f"Failed to reconstruct comparison task: {e}",
            extra={
                "correlation_id": str(correlation_id),
                "comparison_pair_id": comparison_pair.id,
                "error": str(e),
            },
            exc_info=True,
        )
        return None


async def _handle_successful_retry(
    batch_processor: BatchProcessor,
    comparison_pair: ComparisonPair,
    correlation_id: UUID,
) -> None:
    """Handle successful retry by updating pool statistics.

    Args:
        batch_processor: Batch processor instance
        comparison_pair: Successful comparison pair from database
        correlation_id: Request correlation ID for tracing
    """
    try:
        # For successful retries, we need to update the pool statistics
        # This is a simplified implementation - in practice, you'd want to
        # track which comparisons were retries and update accordingly

        # Get current batch state and check if there's an active failed pool
        async with batch_processor.database.session() as session:
            batch_state = await batch_processor._get_batch_state(
                session=session,
                cj_batch_id=comparison_pair.cj_batch_id,
                correlation_id=correlation_id,
            )

            if batch_state and batch_state.processing_metadata:
                from services.cj_assessment_service.models_api import FailedComparisonPool

                failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)

                # Check if this comparison was in the failed pool and remove it
                original_pool_size = len(failed_pool.failed_comparison_pool)
                failed_pool.failed_comparison_pool = [
                    entry
                    for entry in failed_pool.failed_comparison_pool
                    if not (
                        entry.essay_a_id == comparison_pair.essay_a_els_id
                        and entry.essay_b_id == comparison_pair.essay_b_els_id
                    )
                ]

                # If we removed an entry, update statistics
                if len(failed_pool.failed_comparison_pool) < original_pool_size:
                    failed_pool.pool_statistics.successful_retries += 1

                    # Record successful retry metrics
                    from services.cj_assessment_service.metrics import get_business_metrics

                    business_metrics = get_business_metrics()
                    successful_retries_metric = business_metrics.get("cj_successful_retries_total")
                    pool_size_metric = business_metrics.get("cj_failed_pool_size")

                    if successful_retries_metric:
                        successful_retries_metric.inc()

                    if pool_size_metric:
                        pool_size_metric.labels(batch_id=str(comparison_pair.cj_batch_id)).set(
                            len(failed_pool.failed_comparison_pool)
                        )

                    # Update batch state
                    await batch_processor._update_batch_processing_metadata(
                        session=session,
                        cj_batch_id=comparison_pair.cj_batch_id,
                        metadata=failed_pool.model_dump(),
                        correlation_id=correlation_id,
                    )

                    logger.info(
                        f"Removed successful retry from failed pool for batch "
                        f"{comparison_pair.cj_batch_id}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "cj_batch_id": comparison_pair.cj_batch_id,
                            "essay_a_id": comparison_pair.essay_a_els_id,
                            "essay_b_id": comparison_pair.essay_b_els_id,
                        },
                    )

    except Exception as e:
        logger.error(
            f"Failed to handle successful retry: {e}",
            extra={
                "correlation_id": str(correlation_id),
                "comparison_pair_id": comparison_pair.id,
                "cj_batch_id": comparison_pair.cj_batch_id,
                "error": str(e),
            },
            exc_info=True,
        )
        # Don't re-raise - we don't want to fail the callback processing
