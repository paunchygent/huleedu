"""Workflow orchestrator for CJ Assessment Service.

This module coordinates the complete CJ assessment workflow,
delegating to specialized phase modules for content preparation,
comparison processing, and result generation.
"""

from __future__ import annotations

from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic import (
    batch_preparation,
    comparison_processing,
    scoring_ranking,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

logger = create_service_logger("cj_assessment_service.workflow_orchestrator")


async def run_cj_assessment_workflow(
    request_data: dict[str, Any],
    correlation_id: str | None,
    database: CJRepositoryProtocol,
    content_client: ContentClientProtocol,
    llm_interaction: LLMInteractionProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
) -> tuple[list[dict[str, Any]], str]:
    """Run the complete CJ assessment workflow for a batch of essays.

    Args:
        request_data: The CJ assessment request data from ELS
        correlation_id: Optional correlation ID for event tracing
        database: Database access protocol implementation
        content_client: Content client protocol implementation
        llm_interaction: LLM interaction protocol implementation
        event_publisher: Event publisher protocol implementation
        settings: Application settings

    Raises:
        Exception: If the workflow encounters an unrecoverable error
    """
    log_extra = {"correlation_id": correlation_id, "bos_batch_id": request_data.get("bos_batch_id")}
    logger.info("Starting CJ assessment workflow.", extra=log_extra)

    cj_batch_id = None
    try:
        # Phase 1: Create CJ batch and setup
        cj_batch_id = await batch_preparation.create_cj_batch(
            request_data, correlation_id, database, log_extra,
        )

        # Phase 2: Fetch content and prepare essays
        essays_for_api_model = await batch_preparation.prepare_essays_for_assessment(
            request_data, cj_batch_id, database, content_client, log_extra,
        )

        # Phase 3: Iterative Comparison Loop
        final_scores = await comparison_processing.perform_iterative_comparisons(
            essays_for_api_model,
            cj_batch_id,
            database,
            llm_interaction,
            request_data,
            settings,
            log_extra,
        )

        # Phase 4: Complete and publish results
        rankings = await _finalize_batch_results(cj_batch_id, database, final_scores, log_extra)

        logger.info(
            f"CJ assessment completed for batch {cj_batch_id}. "
            f"Rankings generated for {len(rankings)} essays.",
            extra=log_extra,
        )

        return rankings, str(cj_batch_id)

    except Exception as e:
        logger.error(f"CJ assessment workflow failed: {e}", exc_info=True)

        # Try to update batch status to error if we have a batch ID
        if cj_batch_id:
            try:
                async with database.session() as session:
                    await database.update_cj_batch_status(
                        session=session,
                        cj_batch_id=cj_batch_id,
                        status=CJBatchStatusEnum.ERROR_PROCESSING,
                    )
            except Exception as update_error:
                logger.error(f"Failed to update batch status to error: {update_error}")

        # Re-raise the original exception
        raise


async def _finalize_batch_results(
    cj_batch_id: int,
    database: CJRepositoryProtocol,
    final_scores: dict[str, float],
    log_extra: dict[str, Any],
) -> list[dict[str, Any]]:
    """Finalize batch results and determine completion status."""
    async with database.session() as session:
        # Determine final status based on how comparison process ended
        # This is simplified - the comparison_processing module can return
        # additional metadata about stability if needed
        final_status = CJBatchStatusEnum.COMPLETE_STABLE

        await database.update_cj_batch_status(
            session=session, cj_batch_id=cj_batch_id, status=final_status,
        )

        # Get final rankings
        rankings = await scoring_ranking.get_essay_rankings(session, cj_batch_id)

        logger.info(
            f"Finalized batch {cj_batch_id} with {len(rankings)} ranked essays", extra=log_extra,
        )

        return rankings
