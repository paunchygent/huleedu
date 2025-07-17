"""Callback state management utilities for CJ Assessment Service.

This module handles state updates, batch completion detection, and callback-related
database operations for the LLM callback processing system.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.batch_pool_manager import BatchPoolManager
    from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
        BatchRetryProcessor,
    )

from common_core.events.llm_provider_events import LLMComparisonResultV1
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair
from services.cj_assessment_service.protocols import CJRepositoryProtocol

logger = create_service_logger("cj_assessment_service.callback_state_manager")


async def update_comparison_result(
    comparison_result: LLMComparisonResultV1,
    database: CJRepositoryProtocol,
    correlation_id: UUID,
    settings: Settings,
    pool_manager: BatchPoolManager | None = None,
    retry_processor: BatchRetryProcessor | None = None,
) -> int | None:
    """Update comparison pair with LLM callback result.

    Finds ComparisonPair by request_correlation_id and updates with
    success data or error details. Implements idempotency check.

    Args:
        comparison_result: The LLM comparison result callback data
        database: Database access protocol implementation
        correlation_id: Request correlation ID for tracing
        settings: Application settings
        pool_manager: Optional pool manager for failed comparison handling
        retry_processor: Optional retry processor for failed comparison handling

    Returns:
        The batch_id of the updated comparison, or None if not found
    """
    async with database.session() as session:
        # Find comparison pair by request correlation ID
        stmt = select(ComparisonPair).where(ComparisonPair.request_correlation_id == correlation_id)
        result = await session.execute(stmt)
        comparison_pair = result.scalar_one_or_none()

        # DEBUG: Temporarily removed debug output

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

            # Add to failed comparison pool if pool manager is available
            if pool_manager and retry_processor and settings.ENABLE_FAILED_COMPARISON_RETRY:
                await add_failed_comparison_to_pool(
                    pool_manager=pool_manager,
                    retry_processor=retry_processor,
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
            if pool_manager and settings.ENABLE_FAILED_COMPARISON_RETRY:
                await handle_successful_retry(
                    pool_manager=pool_manager,
                    comparison_pair=comparison_pair,
                    correlation_id=correlation_id,
                )

        # Update batch state aggregation counters - CRITICAL FOR BATCH COMPLETION TRACKING
        await _update_batch_completion_counters(
            session=session,
            batch_id=comparison_pair.cj_batch_id,
            is_error=comparison_result.is_error,
            correlation_id=correlation_id,
        )

        await session.commit()
        return comparison_pair.cj_batch_id


async def check_batch_completion_conditions(
    batch_id: int,
    database: CJRepositoryProtocol,
    session: AsyncSession,
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


async def add_failed_comparison_to_pool(
    pool_manager: BatchPoolManager,
    retry_processor: BatchRetryProcessor,
    comparison_pair: ComparisonPair,
    comparison_result: LLMComparisonResultV1,
    correlation_id: UUID,
) -> None:
    """Add failed comparison to the retry pool and check for retry batch need.

    Args:
        pool_manager: Pool manager instance for failed comparison handling
        retry_processor: Retry processor instance for batch submission
        comparison_pair: Failed comparison pair from database
        comparison_result: LLM comparison result with error
        correlation_id: Request correlation ID for tracing
    """
    try:
        # Reconstruct the original comparison task from the database record
        # Note: We need to fetch the essay content from the database
        # This is a simplified version - in practice, you'd want to fetch the full essay data
        comparison_task = await reconstruct_comparison_task(
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
            await pool_manager.add_to_failed_pool(
                cj_batch_id=comparison_pair.cj_batch_id,
                comparison_task=comparison_task,
                failure_reason=failure_reason,
                correlation_id=correlation_id,
            )

            # Check if retry batch needed
            retry_needed = await pool_manager.check_retry_batch_needed(
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
                await retry_processor.submit_retry_batch(
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


async def reconstruct_comparison_task(
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


async def handle_successful_retry(
    pool_manager: BatchPoolManager,
    comparison_pair: ComparisonPair,
    correlation_id: UUID,
) -> None:
    """Handle successful retry by updating pool statistics.

    Args:
        pool_manager: Pool manager instance for failed comparison handling
        comparison_pair: Successful comparison pair from database
        correlation_id: Request correlation ID for tracing
    """
    try:
        # For successful retries, we need to update the pool statistics
        # This is a simplified implementation - in practice, you'd want to
        # track which comparisons were retries and update accordingly

        # Get current batch state and check if there's an active failed pool
        from .batch_submission import get_batch_state

        async with pool_manager.database.session() as session:
            batch_state = await get_batch_state(
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
                    from .batch_submission import update_batch_processing_metadata

                    await update_batch_processing_metadata(
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


async def _update_batch_completion_counters(
    session: AsyncSession,
    batch_id: int,
    is_error: bool,
    correlation_id: UUID,
) -> None:
    """Update batch state aggregation counters for callback completion.

    This is CRITICAL for batch completion tracking. Updates either
    completed_comparisons or failed_comparisons atomically.
    """
    from services.cj_assessment_service.models_db import CJBatchState

    try:
        # Get current batch state using the SAME session (no separate locking)
        stmt = select(CJBatchState).where(CJBatchState.batch_id == batch_id)
        result = await session.execute(stmt)
        batch_state = result.scalar_one_or_none()

        if not batch_state:
            logger.error(f"Batch state not found for batch {batch_id}")
            return

        # Atomically increment the appropriate counter
        if is_error:
            batch_state.failed_comparisons += 1
            logger.info(f"Batch {batch_id} failed_comparisons: {batch_state.failed_comparisons}")
        else:
            batch_state.completed_comparisons += 1
            logger.info(
                f"Batch {batch_id} completed_comparisons: {batch_state.completed_comparisons}"
            )

        # Check for partial scoring trigger (80% completion threshold)
        if (
            batch_state.total_comparisons > 0
            and not batch_state.partial_scoring_triggered
            and batch_state.completed_comparisons
            >= batch_state.total_comparisons * batch_state.completion_threshold_pct / 100
        ):
            batch_state.partial_scoring_triggered = True
            logger.info(
                f"Batch {batch_id} partial scoring triggered at "
                f"{batch_state.completion_threshold_pct}% completion"
            )

    except Exception as e:
        logger.error(
            f"Failed to update batch completion counters for batch {batch_id}: {e}", exc_info=True
        )
