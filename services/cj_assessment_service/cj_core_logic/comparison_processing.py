"""Comparison processing phase for CJ Assessment workflow.

This module handles the iterative comparison loop that performs
pairwise comparisons using LLM and updates Bradley-Terry scores.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from common_core import EssayComparisonWinner
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    EssayForComparison,
)
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)

from . import pair_generation, scoring_ranking

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


async def perform_iterative_comparisons(
    essays_for_api_model: list[EssayForComparison],
    cj_batch_id: int,
    database: CJRepositoryProtocol,
    llm_interaction: LLMInteractionProtocol,
    request_data: dict[str, Any],
    settings: Settings,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> dict[str, float]:
    """Perform iterative comparison processing with LLM.

    Args:
        essays_for_api_model: List of essays prepared for comparison
        cj_batch_id: The CJ batch ID
        database: Database access protocol implementation
        llm_interaction: LLM interaction protocol implementation
        request_data: Original request data containing LLM config overrides
        settings: Application settings
        log_extra: Logging context data

    Returns:
        Final Bradley-Terry scores for all essays
    """
    # Extract LLM config overrides from request data
    llm_config_overrides = request_data.get("llm_config_overrides")
    model_override = None
    temperature_override = None
    max_tokens_override = None

    if llm_config_overrides:
        model_override = llm_config_overrides.model_override
        temperature_override = llm_config_overrides.temperature_override
        max_tokens_override = llm_config_overrides.max_tokens_override

        logger.info(
            f"Using LLM overrides - model: {model_override}, "
            f"temperature: {temperature_override}, max_tokens: {max_tokens_override}",
            extra=log_extra,
        )

    # Update batch status to indicate comparison processing has started
    async with database.session() as session:
        await database.update_cj_batch_status(
            session=session,
            cj_batch_id=cj_batch_id,
            status=CJBatchStatusEnum.PERFORMING_COMPARISONS,
        )

    previous_bt_scores: dict[str, float] = {
        essay_api.id: essay_api.current_bt_score
        for essay_api in essays_for_api_model
        if essay_api.current_bt_score is not None
    }
    total_comparisons_performed = 0
    current_iteration = 0
    scores_are_stable = False

    while total_comparisons_performed < settings.MAX_PAIRWISE_COMPARISONS and not scores_are_stable:
        current_iteration += 1
        logger.info(f"Starting CJ Iteration {current_iteration}", extra=log_extra)

        # Each iteration gets its own session/transaction to ensure reads see previous writes
        async with database.session() as session:
            # Process single iteration
            iteration_result = await _process_comparison_iteration(
                essays_for_api_model=essays_for_api_model,
                cj_batch_id=cj_batch_id,
                session=session,
                llm_interaction=llm_interaction,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
                settings=settings,
                current_iteration=current_iteration,
                correlation_id=correlation_id,
                log_extra=log_extra,
            )

            if not iteration_result:
                logger.info(
                    "No new comparison tasks generated. Ending comparisons.",
                    extra=log_extra,
                )
                break

            total_comparisons_performed += iteration_result.valid_results_count

            # Update scores in the local essays_for_api_model for next iteration
            for essay_api_item in essays_for_api_model:
                if essay_api_item.id in iteration_result.updated_scores:
                    essay_api_item.current_bt_score = iteration_result.updated_scores[
                        essay_api_item.id
                    ]

            # Check for score stability
            scores_are_stable = _check_iteration_stability(
                total_comparisons_performed=total_comparisons_performed,
                current_bt_scores_dict=iteration_result.updated_scores,
                previous_bt_scores=previous_bt_scores,
                settings=settings,
                current_iteration=current_iteration,
                log_extra=log_extra,
            )

            previous_bt_scores = iteration_result.updated_scores.copy()
            # Session auto-commits at end of context - no manual transaction management needed

    final_scores = {essay.id: essay.current_bt_score or 0.0 for essay in essays_for_api_model}

    logger.info(
        f"Comparison processing completed after {current_iteration} iterations, "
        f"{total_comparisons_performed} total comparisons",
        extra=log_extra,
    )

    return final_scores


async def _process_comparison_iteration(
    essays_for_api_model: list[EssayForComparison],
    cj_batch_id: int,
    session: AsyncSession,
    llm_interaction: LLMInteractionProtocol,
    model_override: str | None,
    temperature_override: float | None,
    max_tokens_override: int | None,
    settings: Settings,
    current_iteration: int,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> ComparisonIterationResult | None:
    """Process a single comparison iteration.

    Returns:
        Tuple of (valid_results_count, updated_scores) or None if no tasks generated
    """
    # Generate comparison tasks
    generate_comparison_tasks_coro = pair_generation.generate_comparison_tasks
    comparison_tasks_for_llm: list[ComparisonTask] = await generate_comparison_tasks_coro(
        essays_for_comparison=essays_for_api_model,
        db_session=session,
        cj_batch_id=cj_batch_id,
        existing_pairs_threshold=getattr(settings, "comparisons_per_stability_check_iteration", 5),
        correlation_id=correlation_id,
    )

    if not comparison_tasks_for_llm:
        return None

    # Process comparisons using LLMInteractionProtocol
    perform_comparisons_coro = llm_interaction.perform_comparisons
    llm_comparison_results: list[ComparisonResult] = await perform_comparisons_coro(
        comparison_tasks_for_llm,
        model_override=model_override,
        temperature_override=temperature_override,
        max_tokens_override=max_tokens_override,
        correlation_id=correlation_id,
    )

    # Filter out tasks that resulted in an error from the LLM
    valid_llm_results = [
        res
        for res in llm_comparison_results
        if res.llm_assessment and res.llm_assessment.winner != EssayComparisonWinner.ERROR
    ]

    logger.info(
        f"Iteration {current_iteration}: Received {len(valid_llm_results)} valid LLM results "
        f"from {len(llm_comparison_results)} tasks.",
        extra=log_extra,
    )

    # Record valid results and update scores
    record_scores = scoring_ranking.record_comparisons_and_update_scores
    current_bt_scores_dict: dict[str, float] = await record_scores(
        all_essays=essays_for_api_model,
        comparison_results=valid_llm_results,
        db_session=session,
        cj_batch_id=cj_batch_id,
        correlation_id=correlation_id,
    )

    return ComparisonIterationResult(
        valid_results_count=len(valid_llm_results), updated_scores=current_bt_scores_dict
    )


def _check_iteration_stability(
    total_comparisons_performed: int,
    current_bt_scores_dict: dict[str, float],
    previous_bt_scores: dict[str, float],
    settings: Settings,
    current_iteration: int,
    log_extra: dict[str, Any],
) -> bool:
    """Check if scores have stabilized between iterations."""
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
