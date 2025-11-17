"""LLM interaction orchestration implementation.

Extracted and adapted from llm_caller.py process_comparison_tasks_async function
to follow clean architecture with protocol-based dependency injection.

Cache system removed to preserve CJ Assessment methodology integrity.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import UUID

from common_core import LLMProviderType
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail as CanonicalErrorDetail
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import (
    CJLLMComparisonMetadata,
    ComparisonResult,
    ComparisonTask,
    ErrorDetail,
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
        tracking_map: dict[tuple[str, str], UUID] | None = None,
        bos_batch_id: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        system_prompt_override: str | None = None,
        provider_override: str | LLMProviderType | None = None,
        metadata_context: dict[str, Any] | None = None,
    ) -> list[ComparisonResult]:
        """Perform multiple comparison tasks using configured LLM providers.

        Args:
            tasks: List of comparison tasks to process.
            correlation_id: Request correlation ID for tracing
            tracking_map: Optional map of (essay_a_id, essay_b_id) to unique correlation IDs
            bos_batch_id: Optional BOS batch identifier propagated for ENG5 correlation
            model_override: Optional model name override
            temperature_override: Optional temperature override (0.0-2.0)
            max_tokens_override: Optional max tokens override
            system_prompt_override: Optional system prompt override per batch
            provider_override: Optional provider name override forwarded to LPS
            metadata_context: Optional metadata fields merged into CJLLMComparisonMetadata

        Returns:
            List of comparison results corresponding to the input tasks.
        """
        if not tasks:
            logger.warning("No comparison tasks provided")
            return []

        logger.info(f"Processing {len(tasks)} comparison tasks")
        logger.info(
            f"DEBUG: perform_comparisons called with tracking_map: {tracking_map is not None}, "
            f"tracking_map size: {len(tracking_map) if tracking_map else 0}",
            extra={"correlation_id": str(correlation_id)},
        )

        # Get the provider for the current model configuration
        provider = self._get_provider_for_model()

        # Get business metrics for recording LLM operations
        business_metrics = get_business_metrics()
        llm_api_calls_metric = business_metrics.get("llm_api_calls")

        # Create semaphore for concurrency control
        max_concurrent_requests = getattr(self.settings, "max_concurrent_llm_requests", 3)
        semaphore = asyncio.Semaphore(max_concurrent_requests)

        async def process_task(task: ComparisonTask) -> ComparisonResult | None:
            """Process a single comparison task with direct LLM call."""
            async with semaphore:
                logger.info(
                    f"Processing comparison for essays {task.essay_a.id} vs {task.essay_b.id}",
                )

                # Get the unique correlation ID for this specific comparison
                # If tracking_map is provided, use the unique ID,
                # otherwise use the batch correlation_id
                task_correlation_id = correlation_id
                if tracking_map:
                    task_key = (task.essay_a.id, task.essay_b.id)
                    task_correlation_id = tracking_map.get(task_key, correlation_id)
                    logger.info(
                        f"DEBUG: Using tracking_map correlation ID {task_correlation_id} "
                        f"for task {task_key}",
                        extra={"batch_correlation_id": str(correlation_id)},
                    )
                else:
                    logger.warning(
                        f"DEBUG: No tracking_map provided, "
                        f"using batch correlation ID {correlation_id}",
                        extra={"essay_a": task.essay_a.id, "essay_b": task.essay_b.id},
                    )

                # Make direct LLM API request - no caching
                try:
                    metadata_adapter = CJLLMComparisonMetadata.from_comparison_task(
                        task,
                        bos_batch_id=bos_batch_id,
                    )
                    if metadata_context:
                        metadata_adapter = metadata_adapter.with_additional_context(
                            **metadata_context
                        )
                    request_metadata = metadata_adapter.to_request_metadata()
                    response_data = await provider.generate_comparison(
                        user_prompt=task.prompt,
                        correlation_id=task_correlation_id,  # Use unique correlation ID
                        system_prompt_override=system_prompt_override,
                        model_override=model_override,
                        temperature_override=temperature_override,
                        max_tokens_override=max_tokens_override,
                        provider_override=provider_override,
                        request_metadata=request_metadata,
                    )

                    # ALL LLM calls are async - response_data is ALWAYS None
                    # Results arrive via Kafka callbacks from LLM Provider Service
                    assert response_data is None, (
                        "LLM Provider must always return None (async-only architecture)"
                    )

                    logger.info(
                        f"Comparison for essays {task.essay_a.id} vs {task.essay_b.id} "
                        "queued for async processing - results will arrive via Kafka callback",
                        extra={"correlation_id": str(correlation_id)},
                    )

                    # Record queued LLM API call metric
                    if llm_api_calls_metric:
                        llm_api_calls_metric.labels(
                            provider=self.settings.DEFAULT_LLM_PROVIDER.value,
                            model=model_override or self.settings.DEFAULT_LLM_MODEL,
                            status="queued",
                        ).inc()

                    # Always return None - ALL processing is async
                    return None

                except Exception as e:
                    # Record failed LLM API call metric
                    if llm_api_calls_metric:
                        llm_api_calls_metric.labels(
                            provider=self.settings.DEFAULT_LLM_PROVIDER.value,
                            model=model_override or self.settings.DEFAULT_LLM_MODEL,
                            status="error",
                        ).inc()

                    # Note: exc_info omitted to avoid Rich+Mock interaction in tests
                    logger.error(
                        f"Unexpected error processing task {task.essay_a.id}-{task.essay_b.id}: "
                        f"{e}",
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

            # Handle any exceptions and async results from gather
            final_results: list[ComparisonResult] = []
            async_count = 0
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Note: exc_info omitted here as exceptions should have been logged with full
                    # traceback in the inner except block of process_task(). Logging here with
                    # exc_info=result can trigger Rich's introspection of Mock objects in test
                    # environments, causing TypeError when Rich tries to render local variables.
                    logger.error(
                        f"Task with essays {tasks[i].essay_a.id}-{tasks[i].essay_b.id} "
                        f"raised an exception: {result}",
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
                elif result is None:
                    # Async processing - will be handled via callback
                    async_count += 1
                    # Skip adding to results - callback will handle it
                else:
                    # Type guard: result is ComparisonResult at this point
                    comparison_result = cast(ComparisonResult, result)
                    final_results.append(comparison_result)

            # Log summary
            successful_tasks = sum(1 for r in final_results if r.llm_assessment is not None)
            failed_tasks = len(final_results) - successful_tasks
            logger.info(
                f"Processed {len(tasks)} comparison tasks. "
                f"Immediate: {successful_tasks}, Failed: {failed_tasks}, "
                f"Async (queued): {async_count}",
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
