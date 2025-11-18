"""Comparison processing phase for CJ Assessment workflow.

This module handles the iterative comparison loop that performs
pairwise comparisons using LLM and updates Bradley-Terry scores.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from common_core.config_enums import LLMBatchingMode
from common_core.events.cj_assessment_events import LLMConfigOverrides
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import pair_generation, scoring_ranking
from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.cj_core_logic.batch_submission import (
    merge_batch_processing_metadata,
)
from services.cj_assessment_service.cj_core_logic.llm_batching import (
    build_llm_metadata_context,
    resolve_effective_llm_batching_mode,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    ComparisonTask,
    EssayForComparison,
    OriginalCJRequestMetadata,
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


def is_iterative_batching_online(settings: Settings) -> bool:
    """Determine if the stability-driven batching loop is active for this environment."""

    return (
        getattr(settings, "ENABLE_ITERATIVE_BATCHING_LOOP", False)
        and getattr(settings, "MAX_ITERATIONS", 1) > 1
        and getattr(settings, "MIN_COMPARISONS_FOR_STABILITY_CHECK", 0) > 0
        and getattr(settings, "COMPARISONS_PER_STABILITY_CHECK_ITERATION", 0) > 1
        and settings.LLM_BATCHING_MODE is not LLMBatchingMode.PER_REQUEST
    )


async def _get_current_iteration(session: AsyncSession, cj_batch_id: int) -> int | None:
    """Fetch the current iteration counter for a CJ batch."""

    from services.cj_assessment_service.models_db import CJBatchState

    batch_state = await session.get(CJBatchState, cj_batch_id)
    return batch_state.current_iteration if batch_state else None


def _build_iteration_metadata_context(
    settings: Settings,
    *,
    current_iteration: int | None,
) -> dict[str, Any] | None:
    """Return additive metadata for downstream LLM requests when iteration loop is online."""

    if not (settings.ENABLE_LLM_BATCHING_METADATA_HINTS and is_iterative_batching_online(settings)):
        return None

    iteration_value = current_iteration if current_iteration is not None else 0
    return {"comparison_iteration": iteration_value}


async def _persist_llm_overrides_if_present(
    session: AsyncSession,
    cj_batch_id: int,
    llm_config_overrides: Any | None,
    correlation_id: UUID,
) -> None:
    """Store caller-supplied LLM overrides in the batch metadata."""

    if not llm_config_overrides:
        return

    overrides_payload = llm_config_overrides.model_dump(exclude_none=True)
    if not overrides_payload:
        return

    await merge_batch_processing_metadata(
        session=session,
        cj_batch_id=cj_batch_id,
        metadata_updates={"llm_overrides": overrides_payload},
        correlation_id=correlation_id,
    )


def _resolve_requested_max_pairs(settings: Settings, request_data: CJAssessmentRequestData) -> int:
    """Determine the effective comparison budget for this batch."""

    configured_cap = settings.MAX_PAIRWISE_COMPARISONS
    override_value = request_data.max_comparisons_override

    try:
        override_int = int(override_value) if override_value is not None else None
    except (TypeError, ValueError):
        override_int = None

    if override_int and override_int > 0:
        return min(configured_cap, override_int) if configured_cap else override_int

    return configured_cap


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


def _record_llm_batching_metrics(
    effective_mode: LLMBatchingMode,
    request_count: int,
    *,
    request_type: str | None,
) -> None:
    try:
        business_metrics = get_business_metrics()
    except Exception:  # pragma: no cover - defensive
        logger.debug("Unable to retrieve business metrics for batching counters", exc_info=True)
        return

    requests_metric = business_metrics.get("cj_llm_requests_total")
    batches_metric = business_metrics.get("cj_llm_batches_started_total")

    if requests_metric and request_count > 0:
        try:
            requests_metric.labels(batching_mode=effective_mode.value).inc(request_count)
        except Exception:  # pragma: no cover - defensive
            logger.debug("Unable to increment cj_llm_requests_total metric", exc_info=True)

    if request_type == "cj_comparison" and batches_metric:
        try:
            batches_metric.labels(batching_mode=effective_mode.value).inc()
        except Exception:  # pragma: no cover - defensive
            logger.debug("Unable to increment cj_llm_batches_started_total metric", exc_info=True)


async def submit_comparisons_for_async_processing(
    essays_for_api_model: list[EssayForComparison],
    cj_batch_id: int,
    database: CJRepositoryProtocol,
    llm_interaction: LLMInteractionProtocol,
    request_data: CJAssessmentRequestData,
    settings: Settings,
    correlation_id: UUID,
    log_extra: dict[str, Any],
) -> bool:
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
    llm_config_overrides = request_data.llm_config_overrides
    model_override = None
    temperature_override = None
    max_tokens_override = None
    provider_override = None
    # Use CJ's canonical system prompt as default (can be overridden by event)
    system_prompt_override = settings.SYSTEM_PROMPT

    if llm_config_overrides:
        model_override = llm_config_overrides.model_override
        temperature_override = llm_config_overrides.temperature_override
        max_tokens_override = llm_config_overrides.max_tokens_override
        provider_override = llm_config_overrides.provider_override
        # Only override system prompt if explicitly provided (not None)
        if llm_config_overrides.system_prompt_override is not None:
            system_prompt_override = llm_config_overrides.system_prompt_override

        logger.info(
            f"Using LLM overrides - model: {model_override}, "
            f"temperature: {temperature_override}, max_tokens: {max_tokens_override}",
            extra=log_extra,
        )

    batch_config_overrides = None
    if request_data.batch_config_overrides is not None:
        batch_config_overrides = BatchConfigOverrides(**request_data.batch_config_overrides)

    effective_batching_mode = resolve_effective_llm_batching_mode(
        settings=settings,
        batch_config_overrides=batch_config_overrides,
        provider_override=provider_override,
    )

    max_pairs_cap = _resolve_requested_max_pairs(settings, request_data)
    budget_source = (
        "runner_override" if request_data.max_comparisons_override else "service_default"
    )

    log_extra_with_mode = {
        **log_extra,
        "effective_llm_batching_mode": effective_batching_mode.value,
    }

    logger.info(
        "Resolved comparison budget",
        extra={
            **log_extra_with_mode,
            "comparison_budget": max_pairs_cap,
            "comparison_budget_source": budget_source,
        },
    )

    # Generate initial comparison tasks
    async with database.session() as session:
        # Update batch status to indicate comparison processing has started
        await database.update_cj_batch_status(
            session=session,
            cj_batch_id=cj_batch_id,
            status=CJBatchStatusEnum.PERFORMING_COMPARISONS,
        )

        metadata_updates = _build_budget_metadata(
            max_pairs_cap=max_pairs_cap,
            source=budget_source,
            batch_config_overrides=batch_config_overrides,
        )
        await merge_batch_processing_metadata(
            session=session,
            cj_batch_id=cj_batch_id,
            metadata_updates=metadata_updates,
            correlation_id=correlation_id,
        )

        # Generate comparison tasks for the batch
        comparison_tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=essays_for_api_model,
            db_session=session,
            cj_batch_id=cj_batch_id,
            existing_pairs_threshold=settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION,
            max_pairwise_comparisons=max_pairs_cap,
            correlation_id=correlation_id,
        )

        if not comparison_tasks:
            logger.warning(
                f"No comparison tasks generated for batch {cj_batch_id}",
                extra=log_extra_with_mode,
            )
            return False

        _record_llm_batching_metrics(
            effective_mode=effective_batching_mode,
            request_count=len(comparison_tasks),
            request_type=request_data.cj_request_type,
        )

        # Create batch processor and submit all comparisons
        batch_processor = BatchProcessor(
            database=database,
            llm_interaction=llm_interaction,
            settings=settings,
        )

        current_iteration = await _get_current_iteration(session, cj_batch_id)
        iteration_metadata_context = _build_iteration_metadata_context(
            settings, current_iteration=current_iteration
        )

        metadata_context = build_llm_metadata_context(
            cj_batch_id=cj_batch_id,
            cj_source=request_data.cj_source,
            cj_request_type=request_data.cj_request_type,
            settings=settings,
            effective_mode=effective_batching_mode,
            iteration_metadata_context=iteration_metadata_context,
        )

        await _persist_llm_overrides_if_present(
            session=session,
            cj_batch_id=cj_batch_id,
            llm_config_overrides=llm_config_overrides,
            correlation_id=correlation_id,
        )

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
            provider_override=provider_override,
            metadata_context=metadata_context,
        )

        logger.info(
            f"Submitted {submission_result.total_submitted} comparisons for async processing",
            extra={
                **(
                    {**log_extra_with_mode, "current_iteration": current_iteration}
                    if current_iteration is not None
                    else log_extra_with_mode
                ),
                "cj_batch_id": cj_batch_id,
                "total_submitted": submission_result.total_submitted,
                "all_submitted": submission_result.all_submitted,
            },
        )

        # Workflow pauses here - batch is now in WAITING_CALLBACKS state
        # Callbacks will handle scoring and additional iterations if needed
        return True


async def _load_essays_for_batch(
    database: CJRepositoryProtocol,
    cj_batch_id: int,
) -> list[EssayForComparison]:
    """Load prepared essays (students + anchors) from the database."""

    async with database.session() as session:
        processed_essays = await database.get_essays_for_cj_batch(
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
    database: CJRepositoryProtocol,
    llm_interaction: LLMInteractionProtocol,
    settings: Settings,
    correlation_id: UUID,
    log_extra: dict[str, Any],
    llm_overrides_payload: dict[str, Any] | None,
    config_overrides_payload: dict[str, Any] | None,
    original_request_payload: dict[str, Any] | None,
) -> bool:
    """Enqueue another comparison iteration using stored essays."""

    essays_for_api_model = await _load_essays_for_batch(database=database, cj_batch_id=cj_batch_id)

    if not essays_for_api_model:
        logger.warning(
            "No prepared essays found for continuation",
            extra={**log_extra, "cj_batch_id": cj_batch_id},
        )
        return False

    # Fetch batch metadata to build request_data
    async with database.session() as session:
        batch = await database.get_cj_batch_upload(session, cj_batch_id)
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
        database=database,
        llm_interaction=llm_interaction,
        request_data=request_data,
        settings=settings,
        correlation_id=correlation_id,
        log_extra={**log_extra, "iteration": "continuation"},
    )


async def _process_comparison_iteration(
    essays_for_api_model: list[EssayForComparison],
    cj_batch_id: int,
    session: AsyncSession,
    llm_interaction: LLMInteractionProtocol,
    database: CJRepositoryProtocol,
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
        db_session=session,
        cj_batch_id=cj_batch_id,
        existing_pairs_threshold=settings.COMPARISONS_PER_STABILITY_CHECK_ITERATION,
        max_pairwise_comparisons=settings.MAX_PAIRWISE_COMPARISONS,
        correlation_id=correlation_id,
    )

    if not comparison_tasks_for_llm:
        return None

    # Extract batch config overrides and LLM overrides to determine effective batching mode
    batch_config_overrides = None
    if request_data.batch_config_overrides is not None:
        batch_config_overrides = BatchConfigOverrides(**request_data.batch_config_overrides)

    llm_config_overrides = request_data.llm_config_overrides
    # Use CJ's canonical system prompt as default (can be overridden by event)
    system_prompt_override = settings.SYSTEM_PROMPT
    provider_override = None
    if llm_config_overrides:
        # Only override system prompt if explicitly provided (not None)
        if llm_config_overrides.system_prompt_override is not None:
            system_prompt_override = llm_config_overrides.system_prompt_override
        provider_override = llm_config_overrides.provider_override

    effective_batching_mode = resolve_effective_llm_batching_mode(
        settings=settings,
        batch_config_overrides=batch_config_overrides,
        provider_override=provider_override,
    )

    _record_llm_batching_metrics(
        effective_mode=effective_batching_mode,
        request_count=len(comparison_tasks_for_llm),
        request_type=request_data.cj_request_type,
    )

    # Create batch processor and submit batch for async processing
    batch_processor = BatchProcessor(
        database=database,
        llm_interaction=llm_interaction,
        settings=settings,
    )

    iteration_metadata_context = _build_iteration_metadata_context(
        settings, current_iteration=current_iteration
    )

    metadata_context = build_llm_metadata_context(
        cj_batch_id=cj_batch_id,
        cj_source=request_data.cj_source,
        cj_request_type=request_data.cj_request_type,
        settings=settings,
        effective_mode=effective_batching_mode,
        iteration_metadata_context=iteration_metadata_context,
    )

    await _persist_llm_overrides_if_present(
        session=session,
        cj_batch_id=cj_batch_id,
        llm_config_overrides=llm_config_overrides,
        correlation_id=correlation_id,
    )

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
        provider_override=provider_override,
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
