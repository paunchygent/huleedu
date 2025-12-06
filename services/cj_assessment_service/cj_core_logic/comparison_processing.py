"""Comparison processing phase for CJ Assessment workflow.

This module handles the iterative comparison loop that performs
pairwise comparisons using LLM and updates Bradley-Terry scores.
"""

from __future__ import annotations

from random import Random
from typing import Any
from uuid import UUID

from common_core.events.cj_assessment_events import LLMConfigOverrides
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field

from services.cj_assessment_service.cj_core_logic import pair_generation
from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.cj_core_logic.comparison_batch_orchestrator import (
    ComparisonBatchOrchestrator,
)
from services.cj_assessment_service.cj_core_logic.comparison_request_normalizer import (
    ComparisonRequestNormalizer,
)
from services.cj_assessment_service.cj_core_logic.llm_batching_service import (
    BatchingModeService,
)
from services.cj_assessment_service.cj_core_logic.pair_orientation import (
    FairComplementOrientationStrategy,
    PairOrientationStrategyProtocol,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    EssayForComparison,
    OriginalCJRequestMetadata,
)
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    LLMInteractionProtocol,
    PairMatchingStrategyProtocol,
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
    matching_strategy: PairMatchingStrategyProtocol,
    request_data: CJAssessmentRequestData,
    settings: Settings,
    correlation_id: UUID,
    log_extra: dict[str, Any],
    mode: pair_generation.PairGenerationMode = pair_generation.PairGenerationMode.COVERAGE,
    orientation_strategy: PairOrientationStrategyProtocol | None = None,
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
        matching_strategy: DI-injected strategy for computing optimal pairs
        orientation_strategy: DI-injected strategy for deciding A/B orientation.
            When None (or omitted), a default FairComplementOrientationStrategy is used.
        request_data: CJ assessment request data
        settings: Application settings
        correlation_id: Request correlation ID
        log_extra: Logging context
        mode: Pair generation mode (COVERAGE or RESAMPLING)

    Returns:
        True if submission successful, False otherwise
    """
    if orientation_strategy is None:
        orientation_strategy = FairComplementOrientationStrategy()

    batching_service = BatchingModeService(settings)
    orchestrator = ComparisonBatchOrchestrator(
        batch_repository=batch_repository,
        session_provider=session_provider,
        comparison_repository=comparison_repository,
        instruction_repository=instruction_repository,
        llm_interaction=llm_interaction,
        matching_strategy=matching_strategy,
        orientation_strategy=orientation_strategy,
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
        pair_generation_mode=mode,
    )


async def _load_essays_for_batch(
    session_provider: SessionProviderProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    cj_batch_id: int,
    settings: Settings,
) -> list[EssayForComparison]:
    """Load prepared essays (students + anchors) from the database.

    Sorts essays by comparison_count ascending (fairness) with random shuffling
    for ties, ensuring under-sampled essays are prioritized for new pairs.

    Args:
        session_provider: Session provider for database transactions
        essay_repository: Essay repository for essay operations
        cj_batch_id: The CJ batch identifier
        settings: Application settings (for random seed)

    Returns:
        List of essays prepared for comparison with current BT scores
    """
    async with session_provider.session() as session:
        processed_essays = await essay_repository.get_essays_for_cj_batch(
            session=session, cj_batch_id=cj_batch_id
        )

    # Fairness-aware sorting:
    # 1. Shuffle the list first to randomize ties (Python sort is stable)
    # 2. Sort by comparison_count ascending to prioritize under-sampled essays
    rng = Random(settings.PAIR_GENERATION_SEED)
    # Convert to list if it's not already, though get_essays_for_cj_batch usually returns list
    processed_essays_list = list(processed_essays)
    rng.shuffle(processed_essays_list)
    processed_essays_list.sort(key=lambda e: e.comparison_count or 0)

    essays_for_api_model: list[EssayForComparison] = []
    for processed in processed_essays_list:
        essays_for_api_model.append(
            EssayForComparison(
                id=processed.els_essay_id,
                text_content=processed.assessment_input_text,
                current_bt_score=processed.current_bt_score or 0.0,
                is_anchor=processed.is_anchor,
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
    matching_strategy: PairMatchingStrategyProtocol,
    orientation_strategy: PairOrientationStrategyProtocol | None = None,
    settings: Settings,
    correlation_id: UUID,
    log_extra: dict[str, Any],
    llm_overrides_payload: dict[str, Any] | None,
    config_overrides_payload: dict[str, Any] | None,
    original_request_payload: dict[str, Any] | None,
    mode: pair_generation.PairGenerationMode = pair_generation.PairGenerationMode.COVERAGE,
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
        matching_strategy: DI-injected strategy for computing optimal pairs
        orientation_strategy: DI-injected strategy for deciding A/B orientation.
            When None (or omitted), a default FairComplementOrientationStrategy is used.
        settings: Application settings
        correlation_id: Request correlation ID
        log_extra: Logging context
        llm_overrides_payload: LLM config overrides payload
        config_overrides_payload: Batch config overrides payload
        original_request_payload: Original request metadata payload
        mode: Pair generation mode (COVERAGE or RESAMPLING)

    Returns:
        True if submission successful, False otherwise
    """
    essays_for_api_model = await _load_essays_for_batch(
        session_provider=session_provider,
        essay_repository=essay_repository,
        cj_batch_id=cj_batch_id,
        settings=settings,
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

    if orientation_strategy is None:
        orientation_strategy = FairComplementOrientationStrategy()

    return await submit_comparisons_for_async_processing(
        essays_for_api_model=essays_for_api_model,
        cj_batch_id=cj_batch_id,
        session_provider=session_provider,
        batch_repository=batch_repository,
        comparison_repository=comparison_repository,
        instruction_repository=instruction_repository,
        llm_interaction=llm_interaction,
        matching_strategy=matching_strategy,
        orientation_strategy=orientation_strategy,
        request_data=request_data,
        settings=settings,
        correlation_id=correlation_id,
        log_extra={**log_extra, "iteration": "continuation"},
        mode=mode,
    )


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
