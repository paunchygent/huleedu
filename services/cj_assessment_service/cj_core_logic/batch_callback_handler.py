"""Batch callback handler for CJ Assessment Service.

This module handles LLM callback processing and integrates with existing
proven workflow logic instead of creating a parallel workflow system.
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING
from uuid import UUID

from common_core.events.llm_provider_events import LLMComparisonResultV1
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.callback_state_manager import (
    update_comparison_result,
)
from services.cj_assessment_service.cj_core_logic.workflow_continuation import (
    check_workflow_continuation,
    trigger_existing_workflow_continuation,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
)

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
        BatchRetryProcessor,
    )

# Module-level placeholders for lazy imports to satisfy type checking
scoring_ranking: types.ModuleType | None = None
grade_projector: types.ModuleType | None = None

# Import existing proven workflow logic for integration

logger = create_service_logger("cj_assessment_service.batch_callback_handler")


async def continue_cj_assessment_workflow(
    comparison_result: LLMComparisonResultV1,
    correlation_id: UUID,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
    content_client: ContentClientProtocol,
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
        content_client: Content client for fetching anchor essays
        retry_processor: Optional retry processor for failed comparison handling
    """
    # Lazy imports to avoid scipy/coverage conflict at module initialization
    global scoring_ranking, grade_projector
    if scoring_ranking is None:
        from services.cj_assessment_service.cj_core_logic import scoring_ranking as _sr

        scoring_ranking = _sr
    if grade_projector is None:
        from services.cj_assessment_service.cj_core_logic import grade_projector as _gp

        grade_projector = _gp

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
        # Use the correlation_id from the callback event (which is the request_correlation_id)
        batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            database=database,
            correlation_id=comparison_result.correlation_id,  # Use callback's correlation_id
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
                content_client=content_client,
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


# extracted to workflow_continuation.py
