"""LLM interaction orchestration implementation.

Extracted and adapted from llm_caller.py process_comparison_tasks_async function
to follow clean architecture with protocol-based dependency injection.

Cache system removed to preserve CJ Assessment methodology integrity.
"""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import UUID

from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from huleedu_service_libs.logging_utils import create_service_logger

from common_core import LLMProviderType
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail as CanonicalErrorDetail
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    ErrorDetail,
    LLMAssessmentResponseSchema,
)
from services.cj_assessment_service.protocols import (
    LLMInteractionProtocol,
    LLMProviderProtocol,
)

logger = create_service_logger("cj_assessment_service.llm_interaction_impl")


def _convert_to_local_error_detail(canonical_error: CanonicalErrorDetail) -> ErrorDetail:
    """Convert canonical ErrorDetail to local service ErrorDetail."""
    return ErrorDetail(
        error_code=canonical_error.error_code,
        message=canonical_error.message,
        correlation_id=canonical_error.correlation_id,
        timestamp=canonical_error.timestamp,
        service=canonical_error.service,
        details=canonical_error.details,
    )


class LLMInteractionImpl(LLMInteractionProtocol):
    """Implementation of LLMInteractionProtocol for orchestrating LLM comparisons."""

    def __init__(
        self,
        providers: dict[LLMProviderType, LLMProviderProtocol],
        settings: Settings,
    ) -> None:
        """Initialize LLM interaction orchestrator.

        Args:
            providers: Dictionary of available LLM providers.
            settings: Application settings.
        """
        self.providers = providers
        self.settings = settings

    def _get_provider_for_model(self) -> LLMProviderProtocol:
        """Get the appropriate provider for the configured model."""
        # Use the default provider from structured configuration
        provider_key = self.settings.DEFAULT_LLM_PROVIDER

        if provider_key not in self.providers:
            available_providers = list(self.providers.keys())
            logger.warning(
                f"Default provider '{provider_key}' not available. Available providers: "
                f"{available_providers}. Using first available provider.",
            )
            provider_key = available_providers[0] if available_providers else LLMProviderType.OPENAI

        logger.debug(
            f"Using provider '{provider_key}' with model '{self.settings.DEFAULT_LLM_MODEL}'",
        )
        return self.providers[provider_key]

    async def perform_comparisons(
        self,
        tasks: list[ComparisonTask],
        correlation_id: UUID,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> list[ComparisonResult]:
        """Perform multiple comparison tasks using configured LLM providers.

        Args:
            tasks: List of comparison tasks to process.
            correlation_id: Request correlation ID for tracing
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override

        Returns:
            List of comparison results corresponding to the input tasks.
        """
        if not tasks:
            logger.warning("No comparison tasks provided")
            return []

        logger.info(f"Processing {len(tasks)} comparison tasks")

        # Get the provider for the current model configuration
        provider = self._get_provider_for_model()

        # Get business metrics for recording LLM operations
        business_metrics = get_business_metrics()
        llm_api_calls_metric = business_metrics.get("llm_api_calls")

        # Create semaphore for concurrency control
        max_concurrent_requests = getattr(self.settings, "max_concurrent_llm_requests", 3)
        semaphore = asyncio.Semaphore(max_concurrent_requests)

        async def process_task(task: ComparisonTask) -> ComparisonResult:
            """Process a single comparison task with direct LLM call."""
            async with semaphore:
                logger.info(
                    f"Processing comparison for essays {task.essay_a.id} vs {task.essay_b.id}",
                )

                # Make direct LLM API request - no caching
                try:
                    response_data = await provider.generate_comparison(
                        user_prompt=task.prompt,
                        correlation_id=correlation_id,
                        system_prompt_override=None,
                        model_override=model_override,
                        temperature_override=temperature_override,
                        max_tokens_override=max_tokens_override,
                    )

                    # Record successful LLM API call metric
                    if llm_api_calls_metric:
                        llm_api_calls_metric.labels(
                            provider=self.settings.DEFAULT_LLM_PROVIDER.value,
                            model=model_override or self.settings.DEFAULT_LLM_MODEL,
                            status="success",
                        ).inc()

                    logger.info(
                        f"LLM Response for essays {task.essay_a.id} vs {task.essay_b.id}: "
                        f"Winner -> {response_data.get('winner')}",
                    )

                    llm_assessment = LLMAssessmentResponseSchema(**response_data)
                    return ComparisonResult(
                        task=task,
                        llm_assessment=llm_assessment,
                        error_detail=None,
                        raw_llm_response_content=None,
                    )

                except Exception as e:
                    # Record failed LLM API call metric
                    if llm_api_calls_metric:
                        llm_api_calls_metric.labels(
                            provider=self.settings.DEFAULT_LLM_PROVIDER.value,
                            model=model_override or self.settings.DEFAULT_LLM_MODEL,
                            status="error",
                        ).inc()

                    logger.error(
                        f"Unexpected error processing task {task.essay_a.id}-{task.essay_b.id}: "
                        f"{e}",
                        exc_info=True,
                    )
                    return ComparisonResult(
                        task=task,
                        llm_assessment=None,
                        error_detail=_convert_to_local_error_detail(
                            create_error_detail_with_context(
                                error_code=ErrorCode.PROCESSING_ERROR,
                                message=f"Unexpected error processing task: {e!s}",
                                service="cj_assessment_service",
                                operation="process_comparison_task",
                                correlation_id=correlation_id,
                                details={
                                    "essay_a_id": task.essay_a.id,
                                    "essay_b_id": task.essay_b.id,
                                },
                            )
                        ),
                        raw_llm_response_content=None,
                    )

        # Process all tasks concurrently
        try:
            results = await asyncio.gather(
                *[process_task(task) for task in tasks],
                return_exceptions=True,
            )

            # Handle any exceptions from gather
            final_results: list[ComparisonResult] = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Task with essays {tasks[i].essay_a.id}-{tasks[i].essay_b.id} "
                        f"raised an exception: {result}",
                        exc_info=result,
                    )
                    final_results.append(
                        ComparisonResult(
                            task=tasks[i],
                            llm_assessment=None,
                            error_detail=_convert_to_local_error_detail(
                                create_error_detail_with_context(
                                    error_code=ErrorCode.PROCESSING_ERROR,
                                    message=f"Task execution failed: {result!s}",
                                    service="cj_assessment_service",
                                    operation="process_comparisons_batch",
                                    correlation_id=correlation_id,
                                    details={
                                        "essay_a_id": tasks[i].essay_a.id,
                                        "essay_b_id": tasks[i].essay_b.id,
                                    },
                                )
                            ),
                            raw_llm_response_content=None,
                        ),
                    )
                else:
                    # Type guard: result is ComparisonResult at this point
                    comparison_result = cast(ComparisonResult, result)
                    final_results.append(comparison_result)

            # Log summary
            successful_tasks = sum(1 for r in final_results if r.llm_assessment is not None)
            logger.info(
                f"Completed {len(tasks)} comparison tasks. "
                f"Successful: {successful_tasks}, Failed: {len(tasks) - successful_tasks}",
            )

            return final_results

        except Exception as e:
            logger.error(
                f"Critical error during comparison processing: {e}",
                exc_info=True,
            )
            # Return error results for all tasks
            return [
                ComparisonResult(
                    task=task,
                    llm_assessment=None,
                    error_detail=_convert_to_local_error_detail(
                        create_error_detail_with_context(
                            error_code=ErrorCode.PROCESSING_ERROR,
                            message=f"Critical processing error: {e!s}",
                            service="cj_assessment_service",
                            operation="process_comparisons_critical_error",
                            correlation_id=correlation_id,
                            details={"essay_a_id": task.essay_a.id, "essay_b_id": task.essay_b.id},
                        )
                    ),
                    raw_llm_response_content=None,
                )
                for task in tasks
            ]
