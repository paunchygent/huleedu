"""Comparison processing phase for CJ Assessment workflow.

This module handles the iterative comparison loop that performs
pairwise comparisons using LLM and updates Bradley-Terry scores.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from common_core.events.cj_assessment_events import LLMConfigOverrides
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field

from services.cj_assessment_service.cj_core_logic import pair_generation, scoring_ranking
from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.cj_core_logic.batch_submission import (
    merge_batch_processing_metadata,
)
from services.cj_assessment_service.cj_core_logic.comparison_batch_orchestrator import (
    ComparisonBatchOrchestrator,
)
from services.cj_assessment_service.cj_core_logic.comparison_request_normalizer import (
    ComparisonRequestNormalizer,
)
from services.cj_assessment_service.cj_core_logic.llm_batching_service import (
    BatchingModeService,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    ComparisonTask,
    EssayForComparison,
    OriginalCJRequestMetadata,
)
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    LLMInteractionProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment_service.comparison_processing")


class ComparisonIterationResult(BaseModel):
    """Result of a single comparison iteration with LLM comparisons and score updates.

    This model encapsulates the outcome of processing a batch of comparison tasks,
    including the count of valid results and the updated Bradley-Terry scores.
    """

    valid_results_count: int = Field(
        description="Number of valid LLM comparison results processed", ge=0
    )
    updated_scores: dict[str, float] = Field(
        description="Updated Bradley-Terry scores mapped by essay ID", default_factory=dict
    )


async def submit_comparisons_for_async_processing(
    essays_for_api_model: list[EssayForComparison],
    cj_batch_id: int,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    llm_interaction: LLMInteractionProtocol,
    request_data: CJAssessmentRequestData,
    settings: Settings,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> bool:
    """Submit initial comparison batch for async LLM processing.

    Args:
        essays_for_api_model: Essays prepared for comparison
        cj_batch_id: The CJ batch identifier
        session_provider: Session provider for database transactions
        batch_repository: Repository for batch operations
        comparison_repository: Repository for comparison pair operations
        instruction_repository: Repository for assessment instruction operations
        llm_interaction: LLM interaction protocol
        request_data: CJ assessment request data
        settings: Application settings
        correlation_id: Request correlation ID
        log_extra: Logging context

    Returns:
        True if submission successful, False otherwise
    """
    batching_service = BatchingModeService(settings)
    orchestrator = ComparisonBatchOrchestrator(
        batch_repository=batch_repository,
        session_provider=session_provider,
        comparison_repository=comparison_repository,
        instruction_repository=instruction_repository,
        llm_interaction=llm_interaction,
        settings=settings,
        batching_service=batching_service,
        request_normalizer=ComparisonRequestNormalizer(settings),
    )

    return await orchestrator.submit_initial_batch(
        essays_for_api_model=essays_for_api_model,
        cj_batch_id=cj_batch_id,
        request_data=request_data,
        correlation_id=correlation_id,
        log_extra=log_extra,
    )


async def _load_essays_for_batch(
    session_provider: SessionProviderProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    cj_batch_id: int,
) -> list[EssayForComparison]:
    """Load prepared essays (students + anchors) from the database.

    Args:
        session_provider: Session provider for database transactions
        essay_repository: Essay repository for essay operations
        cj_batch_id: The CJ batch identifier

    Returns:
        List of essays prepared for comparison with current BT scores
    """
    async with session_provider.session() as session:
        processed_essays = await essay_repository.get_essays_for_cj_batch(
            session=session, cj_batch_id=cj_batch_id
        )

    essays_for_api_model: list[EssayForComparison] = []
    for processed in processed_essays:
        essays_for_api_model.append(
            EssayForComparison(
                id=processed.els_essay_id,
                text_content=processed.assessment_input_text,
                current_bt_score=processed.current_bt_score or 0.0,
            )
        )

    return essays_for_api_model


async def request_additional_comparisons_for_batch(
    *,
    cj_batch_id: int,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    llm_interaction: LLMInteractionProtocol,
    settings: Settings,
    correlation_id: UUID,
    log_extra: dict[str, Any],
    llm_overrides_payload: dict[str, Any] | None,
    config_overrides_payload: dict[str, Any] | None,
    original_request_payload: dict[str, Any] | None,
) -> bool:
    """Enqueue another comparison iteration using stored essays.

    Args:
        cj_batch_id: The CJ batch identifier
        session_provider: Session provider for database transactions
        batch_repository: Batch repository for batch operations
        essay_repository: Essay repository for essay operations
        comparison_repository: Repository for comparison pair operations
        instruction_repository: Repository for assessment instruction operations
        llm_interaction: LLM interaction protocol
        settings: Application settings
        correlation_id: Request correlation ID
        log_extra: Logging context
        llm_overrides_payload: LLM config overrides payload
        config_overrides_payload: Batch config overrides payload
        original_request_payload: Original request metadata payload

    Returns:
        True if submission successful, False otherwise
    """
    essays_for_api_model = await _load_essays_for_batch(
        session_provider=session_provider,
        essay_repository=essay_repository,
        cj_batch_id=cj_batch_id,
    )

    if not essays_for_api_model:
        logger.warning(
            "No prepared essays found for continuation",
            extra={**log_extra, "cj_batch_id": cj_batch_id},
        )
        return False

    # Fetch batch metadata to build request_data
    async with session_provider.session() as session:
        batch = await batch_repository.get_cj_batch_upload(session, cj_batch_id)
        if not batch:
            logger.error(
                "CJ batch not found for continuation",
                extra={**log_extra, "cj_batch_id": cj_batch_id},
            )
            return False

    # Build minimal request_data for continuation
    # Convert essays to EssayToProcess format
    from services.cj_assessment_service.models_api import EssayToProcess

    essays_to_process = [
        EssayToProcess(
            els_essay_id=essay.id,
            text_storage_id="",  # Not needed for continuation
        )
        for essay in essays_for_api_model
    ]

    original_request = None
    if original_request_payload:
        try:
            original_request = OriginalCJRequestMetadata(**original_request_payload)
        except Exception as exc:  # Validation errors shouldn't block continuation
            logger.warning(
                "Failed to deserialize stored original_request payload; "
                "falling back to batch defaults",
                extra={**log_extra, "error": str(exc)},
            )

    llm_config_override = None
    if original_request and original_request.llm_config_overrides:
        llm_config_override = original_request.llm_config_overrides
    elif llm_overrides_payload:
        try:
            llm_config_override = LLMConfigOverrides(**llm_overrides_payload)
        except Exception as exc:  # Validation errors shouldn't block continuation
            logger.warning(
                "Failed to deserialize stored LLM overrides; continuing with defaults",
                extra={**log_extra, "error": str(exc)},
            )

    config_overrides = None
    if original_request and original_request.batch_config_overrides:
        config_overrides = original_request.batch_config_overrides
    elif isinstance(config_overrides_payload, dict):
        config_overrides = config_overrides_payload

    prompt_context = (
        batch.processing_metadata if isinstance(batch.processing_metadata, dict) else {}
    )

    request_data = CJAssessmentRequestData(
        bos_batch_id=batch.bos_batch_id,
        assignment_id=original_request.assignment_id if original_request else batch.assignment_id,
        essays_to_process=essays_to_process,
        language=original_request.language if original_request else batch.language,
        course_code=original_request.course_code if original_request else batch.course_code,
        cj_source=original_request.cj_source if original_request else "els",
        cj_request_type="cj_retry",
        student_prompt_text=(
            original_request.student_prompt_text
            if original_request
            else prompt_context.get("student_prompt_text")
        ),
        student_prompt_storage_id=(
            original_request.student_prompt_storage_id
            if original_request
            else prompt_context.get("student_prompt_storage_id")
        ),
        judge_rubric_text=(
            original_request.judge_rubric_text
            if original_request
            else prompt_context.get("judge_rubric_text")
        ),
        judge_rubric_storage_id=(
            original_request.judge_rubric_storage_id
            if original_request
            else prompt_context.get("judge_rubric_storage_id")
        ),
        llm_config_overrides=llm_config_override,
        batch_config_overrides=config_overrides,
        max_comparisons_override=(
            original_request.max_comparisons_override if original_request else None
        ),
        user_id=original_request.user_id if original_request else batch.user_id,
        org_id=original_request.org_id if original_request else batch.org_id,
    )

    logger.info(
        "Requesting additional comparisons for batch",
        extra={**log_extra, "cj_batch_id": cj_batch_id},
    )

    return await submit_comparisons_for_async_processing(
        essays_for_api_model=essays_for_api_model,
        cj_batch_id=cj_batch_id,
        session_provider=session_provider,
        batch_repository=batch_repository,
        comparison_repository=comparison_repository,
        instruction_repository=instruction_repository,
        llm_interaction=llm_interaction,
        request_data=request_data,
        settings=settings,
        correlation_id=correlation_id,
        log_extra={**log_extra, "iteration": "continuation"},
    )


async def _process_comparison_iteration(
    essays_for_api_model: list[EssayForComparison],
    cj_batch_id: int,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    llm_interaction: LLMInteractionProtocol,
    request_data: CJAssessmentRequestData,
    settings: Settings,
    model_override: str | None,
    temperature_override: float | None,
    max_tokens_override: int | None,
    current_iteration: int,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> ComparisonIterationResult | None:
    """Submit one bundled comparison iteration for a CJ batch.

    NOTE:
    - Prepared infrastructure for bundled, stability-driven BT convergence.
    - Currently **unused** and not wired into workflow_continuation; it does
      submission only (no score recomputation or stability decision yet).
    - Target behavior is defined in
      .claude/tasks/TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION*.md
      under the "bundled (iterative, stability-driven)" mode.

    TODO[TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION]:
    Wire this into the callback/continuation path so that each bundle:
      1) recomputes BT scores,
      2) runs a stability check, and
      3) decides whether to request another bundle or finalize.

    Returns:
        ComparisonIterationResult or None if no tasks generated
    """
    # Generate comparison tasks
    generate_comparison_tasks_coro = pair_generation.generate_comparison_tasks
    comparison_tasks_for_llm: list[ComparisonTask] = await generate_comparison_tasks_coro(
        essays_for_comparison=essays_for_api_model,
        session_provider=session_provider,
        comparison_repository=comparison_repository,
        instruction_repository=instruction_repository,
        cj_batch_id=cj_batch_id,
        existing_pairs_threshold=settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION,
        max_pairwise_comparisons=settings.MAX_PAIRWISE_COMPARISONS,
        correlation_id=correlation_id,
        randomization_seed=settings.PAIR_GENERATION_SEED,
    )

    if not comparison_tasks_for_llm:
        return None

    batching_service = BatchingModeService(settings)
    request_normalizer = ComparisonRequestNormalizer(settings)
    normalized = request_normalizer.normalize(request_data)

    effective_batching_mode = batching_service.resolve_effective_mode(
        batch_config_overrides=normalized.batch_config_overrides,
        provider_override=normalized.provider_override,
    )

    batching_service.record_metrics(
        effective_mode=effective_batching_mode,
        request_count=len(comparison_tasks_for_llm),
        request_type=request_data.cj_request_type,
    )

    # Create batch processor and submit batch for async processing
    batch_processor = BatchProcessor(
        session_provider=session_provider,
        llm_interaction=llm_interaction,
        settings=settings,
        batch_repository=batch_repository,
    )

    iteration_metadata_context = batching_service.build_iteration_metadata_context(
        current_iteration=current_iteration
    )

    metadata_context = batching_service.build_metadata_context(
        cj_batch_id=cj_batch_id,
        cj_source=request_data.cj_source or "",
        cj_request_type=request_data.cj_request_type or "",
        effective_mode=effective_batching_mode,
        iteration_metadata_context=iteration_metadata_context,
    )

    await merge_batch_processing_metadata(
        session_provider=session_provider,
        cj_batch_id=cj_batch_id,
        metadata_updates={
            "llm_overrides": normalized.llm_config_overrides.model_dump(exclude_none=True)
        }
        if normalized.llm_config_overrides
        else {},
        correlation_id=correlation_id,
    )

    # Submit batch and update state to WAITING_CALLBACKS
    submission_result = await batch_processor.submit_comparison_batch(
        cj_batch_id=cj_batch_id,
        comparison_tasks=comparison_tasks_for_llm,
        correlation_id=correlation_id,
        config_overrides=normalized.batch_config_overrides,
        model_override=model_override,
        temperature_override=temperature_override,
        max_tokens_override=max_tokens_override,
        system_prompt_override=normalized.system_prompt_override,
        provider_override=normalized.provider_override,
        metadata_context=metadata_context,
    )

    logger.info(
        f"Batch submitted for async processing: {submission_result.total_submitted} tasks",
        extra={
            **log_extra,
            "cj_batch_id": cj_batch_id,
            "total_submitted": submission_result.total_submitted,
            "all_submitted": submission_result.all_submitted,
            "current_iteration": current_iteration,
        },
    )

    # Return None to indicate async processing - workflow continues via callbacks
    return None


def _check_iteration_stability(
    total_comparisons_performed: int,
    current_bt_scores_dict: dict[str, float],
    previous_bt_scores: dict[str, float],
    settings: Settings,
    current_iteration: int,
    log_extra: dict[str, Any],
) -> bool:
    """Evaluate BT score stability between iterations.

    Uses MIN_COMPARISONS_FOR_STABILITY_CHECK and
    SCORE_STABILITY_THRESHOLD from Settings to determine whether the
    Bradley-Terry scores have 'converged enough' to stop requesting
    more comparisons.

    NOTE:
    - Prepared for the iterative bundled mode described in
      TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION*.md.
    - Not currently called from any production workflow.

    TODO[TASK-LLM-BATCH-STRATEGY-IMPLEMENTATION]:
    Call this from the continuation/iteration loop once iterative
    convergence is wired into workflow_continuation instead of relying
    solely on completion thresholds.
    """
    if (
        total_comparisons_performed >= getattr(settings, "MIN_COMPARISONS_FOR_STABILITY_CHECK", 10)
        and previous_bt_scores
    ):
        max_score_change = scoring_ranking.check_score_stability(
            current_bt_scores_dict,
            previous_bt_scores,
            stability_threshold=getattr(settings, "SCORE_STABILITY_THRESHOLD", 0.05),
        )
        logger.info(
            f"Iteration {current_iteration}: Max score change is {max_score_change:.5f}",
            extra=log_extra,
        )
        if max_score_change < getattr(settings, "SCORE_STABILITY_THRESHOLD", 0.05):
            logger.info("Score stability reached. Ending comparison loop.", extra=log_extra)
            return True

    return False


def _resolve_requested_max_pairs(settings: Settings, request_data: CJAssessmentRequestData) -> int:
    """Compatibility wrapper delegating to the comparison request normalizer."""

    return ComparisonRequestNormalizer(settings).normalize(request_data).max_pairs_cap


def _build_budget_metadata(
    *,
    max_pairs_cap: int,
    source: str,
    batch_config_overrides: BatchConfigOverrides | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "comparison_budget": {
            "max_pairs_requested": max_pairs_cap,
            "source": source,
        }
    }
    if batch_config_overrides:
        metadata["config_overrides"] = batch_config_overrides.model_dump(exclude_none=True)
    return metadata
