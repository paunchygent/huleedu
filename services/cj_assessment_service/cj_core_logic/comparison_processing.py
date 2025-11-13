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

from services.cj_assessment_service.cj_core_logic import pair_generation, scoring_ranking
from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    EssayForComparison,
)
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    LLMInteractionProtocol,
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
    database: CJRepositoryProtocol,
    llm_interaction: LLMInteractionProtocol,
    request_data: dict[str, Any],
    settings: Settings,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> None:
    """Submit essay comparisons for async LLM processing.

    This function submits all comparison tasks and transitions the batch to
    WAITING_CALLBACKS state. ALL LLM processing is async - results arrive via
    Kafka callbacks which trigger scoring and completion.

    Args:
        essays_for_api_model: List of essays prepared for comparison
        cj_batch_id: The CJ batch ID
        database: Database access protocol implementation
        llm_interaction: LLM interaction protocol implementation
        request_data: Original request data containing LLM config overrides
        settings: Application settings
        correlation_id: Request correlation ID
        log_extra: Logging context data
    """
    # Extract LLM config overrides from request data
    llm_config_overrides = request_data.get("llm_config_overrides")
    model_override = None
    temperature_override = None
    max_tokens_override = None
    system_prompt_override = None

    if llm_config_overrides:
        model_override = llm_config_overrides.model_override
        temperature_override = llm_config_overrides.temperature_override
        max_tokens_override = llm_config_overrides.max_tokens_override
        system_prompt_override = llm_config_overrides.system_prompt_override

        logger.info(
            f"Using LLM overrides - model: {model_override}, "
            f"temperature: {temperature_override}, max_tokens: {max_tokens_override}",
            extra=log_extra,
        )

    # Generate initial comparison tasks
    async with database.session() as session:
        # Update batch status to indicate comparison processing has started
        await database.update_cj_batch_status(
            session=session,
            cj_batch_id=cj_batch_id,
            status=CJBatchStatusEnum.PERFORMING_COMPARISONS,
        )

        # Generate comparison tasks for the batch
        comparison_tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=essays_for_api_model,
            db_session=session,
            cj_batch_id=cj_batch_id,
            existing_pairs_threshold=getattr(
                settings, "comparisons_per_stability_check_iteration", 5
            ),
            correlation_id=correlation_id,
        )

        if not comparison_tasks:
            logger.warning(
                f"No comparison tasks generated for batch {cj_batch_id}",
                extra=log_extra,
            )
            return

        # Create batch processor and submit all comparisons
        batch_processor = BatchProcessor(
            database=database,
            llm_interaction=llm_interaction,
            settings=settings,
        )

        # Extract batch config overrides if available
        batch_config_overrides = None
        if "batch_config_overrides" in request_data:
            batch_config_overrides = BatchConfigOverrides(**request_data["batch_config_overrides"])

        # Submit batch for async processing - this will set state to WAITING_CALLBACKS
        submission_result = await batch_processor.submit_comparison_batch(
            cj_batch_id=cj_batch_id,
            comparison_tasks=comparison_tasks,
            correlation_id=correlation_id,
            config_overrides=batch_config_overrides,
            model_override=model_override,
            temperature_override=temperature_override,
            max_tokens_override=max_tokens_override,
            system_prompt_override=system_prompt_override,
        )

        logger.info(
            f"Submitted {submission_result.total_submitted} comparisons for async processing",
            extra={
                **log_extra,
                "cj_batch_id": cj_batch_id,
                "total_submitted": submission_result.total_submitted,
                "all_submitted": submission_result.all_submitted,
            },
        )

        # Workflow pauses here - batch is now in WAITING_CALLBACKS state
        # Callbacks will handle scoring and additional iterations if needed


async def _process_comparison_iteration(
    essays_for_api_model: list[EssayForComparison],
    cj_batch_id: int,
    session: AsyncSession,
    llm_interaction: LLMInteractionProtocol,
    database: CJRepositoryProtocol,
    request_data: dict[str, Any],
    settings: Settings,
    model_override: str | None,
    temperature_override: float | None,
    max_tokens_override: int | None,
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

    # Create batch processor and submit batch for async processing
    batch_processor = BatchProcessor(
        database=database,
        llm_interaction=llm_interaction,
        settings=settings,
    )

    # Extract batch config overrides from request_data if available
    batch_config_overrides = None
    if "batch_config_overrides" in request_data:
        batch_config_overrides = BatchConfigOverrides(**request_data["batch_config_overrides"])

    # Extract system_prompt_override from request_data if available
    system_prompt_override = None
    llm_config_overrides = request_data.get("llm_config_overrides")
    if llm_config_overrides:
        system_prompt_override = llm_config_overrides.system_prompt_override

    # Submit batch and update state to WAITING_CALLBACKS
    submission_result = await batch_processor.submit_comparison_batch(
        cj_batch_id=cj_batch_id,
        comparison_tasks=comparison_tasks_for_llm,
        correlation_id=correlation_id,
        config_overrides=batch_config_overrides,
        model_override=model_override,
        temperature_override=temperature_override,
        max_tokens_override=max_tokens_override,
        system_prompt_override=system_prompt_override,
    )

    logger.info(
        f"Batch submitted for async processing: {submission_result.total_submitted} tasks",
        extra={
            **log_extra,
            "cj_batch_id": cj_batch_id,
            "total_submitted": submission_result.total_submitted,
            "all_submitted": submission_result.all_submitted,
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
