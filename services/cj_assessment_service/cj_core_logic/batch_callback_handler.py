"""Batch callback handler for CJ Assessment Service.

This module handles LLM callback processing and integrates with existing
proven workflow logic instead of creating a parallel workflow system.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
        BatchRetryProcessor,
    )

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select

from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import BatchStatus, CJBatchStateEnum, ProcessingStage
from services.cj_assessment_service.cj_core_logic import (
    batch_completion_checker,
    scoring_ranking,
)
from services.cj_assessment_service.cj_core_logic.batch_submission import get_batch_state
from services.cj_assessment_service.cj_core_logic.callback_state_manager import (
    check_batch_completion_conditions,
    update_comparison_result,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import EssayForComparison
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
    retry_processor: BatchRetryProcessor | None = None,
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
        retry_processor: Optional retry processor for failed comparison handling
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
        batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            database=database,
            correlation_id=correlation_id,
            settings=settings,
            pool_manager=None,  # Will need proper injection
            retry_processor=retry_processor,
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
        should_continue = await check_workflow_continuation(
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
            await trigger_existing_workflow_continuation(
                batch_id=batch_id,
                database=database,
                event_publisher=event_publisher,
                settings=settings,
                correlation_id=correlation_id,
                retry_processor=retry_processor,
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


async def check_workflow_continuation(
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


async def trigger_existing_workflow_continuation(
    batch_id: int,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
    correlation_id: UUID,
    retry_processor: BatchRetryProcessor | None = None,
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
        retry_processor: Optional retry processor for failed comparison handling
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
        batch_is_completing = await check_batch_completion_conditions(
            batch_id=batch_id,
            database=database,
            session=session,
            correlation_id=correlation_id,
        )

        if batch_is_completing and retry_processor:
            logger.info(
                f"Batch {batch_id} is completing, processing remaining failed comparisons "
                f"for fairness",
                extra=log_extra,
            )

            try:
                # Process any remaining failed comparisons for fairness
                remaining_result = await retry_processor.process_remaining_failed_comparisons(
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

        # Get batch state to retrieve config overrides
        batch_state = await get_batch_state(session, batch_id, correlation_id)
        if not batch_state:
            logger.error(
                f"Batch state not found for batch {batch_id}",
                extra=log_extra,
            )
            return

        # Check if batch has reached completion and trigger scoring if ready
        completion_checker = batch_completion_checker.BatchCompletionChecker(
            database=database,
        )

        is_complete = await completion_checker.check_batch_completion(
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
            config_overrides=batch_state.config_overrides,
        )

        if is_complete:
            logger.info(
                f"Batch {batch_id} has reached completion threshold, triggering scoring",
                extra=log_extra,
            )

            await _trigger_batch_scoring_completion(
                batch_id=batch_id,
                database=database,
                event_publisher=event_publisher,
                session=session,
                correlation_id=correlation_id,
                log_extra=log_extra,
            )


async def _trigger_batch_scoring_completion(
    batch_id: int,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    session: AsyncSession,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> None:
    """Trigger Bradley-Terry scoring and completion for a batch.

    Args:
        batch_id: The CJ batch ID
        database: Database access protocol
        event_publisher: Event publishing protocol
        session: Active database session
        correlation_id: Correlation ID for tracing
        log_extra: Extra logging context
    """
    try:
        # Update batch state to SCORING
        await database.update_cj_batch_status(
            session=session,
            cj_batch_id=batch_id,
            status=CJBatchStateEnum.SCORING,
        )

        # Get batch upload for BOS batch ID
        from services.cj_assessment_service.models_db import CJBatchUpload

        batch_upload = await session.get(CJBatchUpload, batch_id)
        if not batch_upload:
            logger.error(
                f"Batch upload not found for batch {batch_id}",
                extra={**log_extra, "batch_id": batch_id},
            )
            return

        # Get all essays for scoring
        essays = await database.get_essays_for_cj_batch(
            session=session,
            cj_batch_id=batch_id,
        )

        # Convert to API model format
        essays_for_api = [
            EssayForComparison(
                id=essay.els_essay_id,
                text_content=essay.content,
                current_bt_score=essay.current_bt_score,
            )
            for essay in essays
        ]

        # Get all comparisons for this batch (already stored in DB)
        comparisons: list[Any] = []  # Comparisons are already in DB from callbacks

        # Calculate final Bradley-Terry scores
        await scoring_ranking.record_comparisons_and_update_scores(
            all_essays=essays_for_api,
            comparison_results=comparisons,
            db_session=session,
            cj_batch_id=batch_id,
            correlation_id=correlation_id,
        )

        # Update batch status to completed
        await database.update_cj_batch_status(
            session=session,
            cj_batch_id=batch_id,
            status=CJBatchStateEnum.COMPLETED,
        )

        # Get final rankings
        rankings = await scoring_ranking.get_essay_rankings(session, batch_id, correlation_id)

        # Create the event data
        event_data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_ref=EntityReference(
                entity_id=batch_upload.bos_batch_id,
                entity_type="batch",
            ),
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_upload.bos_batch_id,
                    entity_type="batch",
                ),
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.COMPLETED,
                started_at=batch_upload.created_at,
                completed_at=datetime.now(UTC),
                event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
            ),
            cj_assessment_job_id=str(batch_id),
            rankings=rankings,
        )

        # Wrap in EventEnvelope
        completion_envelope = EventEnvelope[CJAssessmentCompletedV1](
            event_type="cj_assessment.completed.v1",
            event_timestamp=datetime.now(UTC),
            source_service="cj_assessment_service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Publish completion event
        await event_publisher.publish_assessment_completed(
            completion_data=completion_envelope,
            correlation_id=correlation_id,
        )

        logger.info(
            f"Successfully completed scoring for batch {batch_id}",
            extra={
                **log_extra,
                "essay_count": len(essays),
                "status": "COMPLETED",
            },
        )

    except Exception as e:
        logger.error(
            f"Failed to trigger scoring completion for batch {batch_id}: {e}",
            extra={
                **log_extra,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        # Update batch to failed state
        try:
            await database.update_cj_batch_status(
                session=session,
                cj_batch_id=batch_id,
                status=CJBatchStateEnum.FAILED,
            )
        except Exception as update_error:
            logger.error(
                f"Failed to update batch status to FAILED: {update_error}",
                extra={**log_extra, "update_error": str(update_error)},
            )
