"""Workflow continuation logic for CJ Assessment Service.

Isolates continuation checks and scoring trigger away from callback handler
to improve SRP and keep modules small and focused.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select

from services.cj_assessment_service.cj_core_logic.batch_completion_checker import (
    BatchCompletionChecker,
)
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
    """Check if this callback enables workflow continuation.

    Uses both periodic thresholds and configured completion thresholds.
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
        stmt = select(ComparisonPair).where(
            ComparisonPair.cj_batch_id == batch_id,
            ComparisonPair.winner.isnot(None),
        )
        result = await session.execute(stmt)
        completed_pairs = result.scalars().all()
        completed_count = len(completed_pairs)

        # Support both periodic continuation (every 5) and threshold-based
        should_continue: bool = False
        if batch_state.total_comparisons > 0:
            # Periodic continuation every 5 completions
            if completed_count > 0 and completed_count % 5 == 0:
                should_continue = True
            # Also check completion threshold if configured
            if (
                not should_continue
                and batch_state.completion_threshold_pct
                and batch_state.completion_threshold_pct > 0
            ):
                completion_percentage = (completed_count / batch_state.total_comparisons) * 100
                if completion_percentage >= batch_state.completion_threshold_pct:
                    should_continue = True

        logger.info(
            "Continuation check computed",
            extra={
                "correlation_id": str(correlation_id),
                "batch_id": batch_id,
                "completed_pairs": completed_count,
                "total_comparisons": batch_state.total_comparisons,
                "should_continue": should_continue,
            },
        )

        return should_continue


async def trigger_existing_workflow_continuation(
    batch_id: int,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: "Settings",
    content_client: ContentClientProtocol,
    correlation_id: UUID,
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
        stmt = select(ComparisonPair).where(
            ComparisonPair.cj_batch_id == batch_id,
            ComparisonPair.winner.isnot(None),
            ComparisonPair.winner != "error",
        )
        result = await session.execute(stmt)
        valid_comparisons = result.scalars().all()

        logger.info(
            "Valid comparisons found",
            extra={**log_extra, "valid_comparisons": len(valid_comparisons)},
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

        # Check completion threshold and trigger finalization
        completion_checker = BatchCompletionChecker(database=database)
        config_overrides = None
        if batch_state.processing_metadata and isinstance(batch_state.processing_metadata, dict):
            config_overrides = batch_state.processing_metadata.get("config_overrides")

        is_complete = await completion_checker.check_batch_completion(
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
            config_overrides=config_overrides,
        )

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
