"""Workflow orchestrator for CJ Assessment Service.

This module coordinates the complete CJ assessment workflow,
delegating to specialized phase modules for content preparation,
comparison processing, and result generation.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field

from services.cj_assessment_service.cj_core_logic import (
    batch_preparation,
    comparison_processing,
    scoring_ranking,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import CJAssessmentRequestData
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    PairMatchingStrategyProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment_service.workflow_orchestrator")


class CJAssessmentWorkflowResult(BaseModel):
    """Result of a complete CJ assessment workflow execution.

    This model encapsulates the final output of the CJ assessment process,
    including essay rankings and the associated batch identifier.
    """

    rankings: list[dict[str, Any]] = Field(
        description="Ordered list of essay rankings with scores and metadata", default_factory=list
    )
    batch_id: str = Field(
        description="String identifier of the CJ batch that was processed", min_length=1
    )


async def run_cj_assessment_workflow(
    request_data: CJAssessmentRequestData,
    correlation_id: UUID,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    anchor_repository: AnchorRepositoryProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    content_client: ContentClientProtocol,
    llm_interaction: LLMInteractionProtocol,
    matching_strategy: PairMatchingStrategyProtocol,
    event_publisher: CJEventPublisherProtocol,
    settings: Settings,
    grade_projector: GradeProjector,
) -> CJAssessmentWorkflowResult:
    """Run the complete CJ assessment workflow for a batch of essays.

    Args:
        request_data: The CJ assessment request data from ELS
        correlation_id: Optional correlation ID for event tracing
        session_provider: Session provider for database transactions
        batch_repository: Batch repository for batch-level operations
        essay_repository: Essay repository for essay operations
        instruction_repository: Instruction repository for assessment instructions
        anchor_repository: Anchor repository for anchor essay management
        comparison_repository: Comparison repository for comparison pair operations
        content_client: Content client protocol implementation
        llm_interaction: LLM interaction protocol implementation
        matching_strategy: DI-injected strategy for computing optimal pairs
        event_publisher: Event publisher protocol implementation
        settings: Application settings
        grade_projector: Grade projector for grade predictions

    Raises:
        Exception: If the workflow encounters an unrecoverable error
    """
    log_extra = {"correlation_id": correlation_id, "bos_batch_id": request_data.bos_batch_id}
    logger.info("Starting CJ assessment workflow.", extra=log_extra)

    cj_batch_id = None
    try:
        # Phase 1: Create CJ batch and setup
        cj_batch_id = await batch_preparation.create_cj_batch(
            request_data,
            correlation_id,
            session_provider,
            batch_repository,
            instruction_repository,
            content_client,
            log_extra,
        )

        # Phase 2: Fetch content and prepare essays
        essays_for_api_model = await batch_preparation.prepare_essays_for_assessment(
            request_data,
            cj_batch_id,
            session_provider,
            batch_repository,
            essay_repository,
            instruction_repository,
            anchor_repository,
            content_client,
            correlation_id,
            log_extra,
        )

        # Short-circuit for single-essay batches (no comparisons possible)
        student_count = sum(1 for e in essays_for_api_model if not e.id.startswith("ANCHOR_"))
        if student_count < 2:
            logger.info(
                "Detected <2 student essays; finalizing batch without comparisons",
                extra={**log_extra, "cj_batch_id": cj_batch_id, "student_count": student_count},
            )

            # Use centralized finalizer in single_essay mode
            from services.cj_assessment_service.cj_core_logic.batch_finalizer import (
                BatchFinalizer,
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
            await finalizer.finalize_single_essay(
                batch_id=cj_batch_id,
                correlation_id=correlation_id,
                log_extra=log_extra,
            )

            # Return empty result; events published via outbox
            return CJAssessmentWorkflowResult(rankings=[], batch_id=str(cj_batch_id))

        # Phase 3: Submit Comparisons for Async Processing
        # ALL LLM calls are async - workflow ALWAYS pauses here
        # Results arrive via Kafka callbacks which trigger completion
        await comparison_processing.submit_comparisons_for_async_processing(
            essays_for_api_model=essays_for_api_model,
            cj_batch_id=cj_batch_id,
            session_provider=session_provider,
            batch_repository=batch_repository,
            comparison_repository=comparison_repository,
            instruction_repository=instruction_repository,
            llm_interaction=llm_interaction,
            matching_strategy=matching_strategy,
            request_data=request_data,
            settings=settings,
            correlation_id=correlation_id,
            log_extra=log_extra,
        )

        # Workflow pauses here - batch is now in WAITING_CALLBACKS state
        # Callbacks will trigger scoring and event publishing via batch_callback_handler
        logger.info(
            f"CJ batch {cj_batch_id} comparisons submitted for async processing. "
            "Workflow will continue via callback handler when LLM results arrive.",
            extra=log_extra,
        )

        # Return empty result - actual results will be published by callback handler
        return CJAssessmentWorkflowResult(rankings=[], batch_id=str(cj_batch_id))

    except Exception as e:
        logger.error(
            f"CJ assessment workflow failed: {e}",
            extra={
                "correlation_id": correlation_id,
                "cj_batch_id": cj_batch_id,
                "exception_type": type(e).__name__,
            },
            exc_info=True,
        )

        # Try to update batch status to error if we have a batch ID
        if cj_batch_id:
            try:
                async with session_provider.session() as session:
                    await batch_repository.update_cj_batch_status(
                        session=session,
                        cj_batch_id=cj_batch_id,
                        status=CJBatchStatusEnum.ERROR_PROCESSING,
                    )
            except Exception as update_error:
                logger.error(
                    f"Failed to update batch status to error: {update_error}",
                    extra={
                        "correlation_id": correlation_id,
                        "cj_batch_id": cj_batch_id,
                        "update_error_type": type(update_error).__name__,
                    },
                )

        # Re-raise the original exception
        raise


async def _finalize_batch_results(
    cj_batch_id: int,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    final_scores: dict[str, float],
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> list[dict[str, Any]]:
    """Finalize batch results and determine completion status."""
    async with session_provider.session() as session:
        # Determine final status based on how comparison process ended
        # This is simplified - the comparison_processing module can return
        # additional metadata about stability if needed
        final_status = CJBatchStatusEnum.COMPLETE_STABLE

        await batch_repository.update_cj_batch_status(
            session=session,
            cj_batch_id=cj_batch_id,
            status=final_status,
        )

        # Get final rankings
        rankings = await scoring_ranking.get_essay_rankings(
            session_provider, essay_repository, cj_batch_id, correlation_id
        )

        logger.info(
            f"Finalized batch {cj_batch_id} with {len(rankings)} ranked essays",
            extra=log_extra,
        )

        return rankings
