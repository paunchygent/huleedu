"""LLM interaction orchestration implementation.

Extracted and adapted from llm_caller.py process_comparison_tasks_async function
to follow clean architecture with protocol-based dependency injection.
"""

from __future__ import annotations

import asyncio

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import (
    ComparisonResult,
    ComparisonTask,
    LLMAssessmentResponseSchema,
)
from services.cj_assessment_service.protocols import (
    CacheProtocol,
    LLMInteractionProtocol,
    LLMProviderProtocol,
)

logger = create_service_logger("cj_assessment_service.llm_interaction_impl")


class LLMInteractionImpl(LLMInteractionProtocol):
    """Implementation of LLMInteractionProtocol for orchestrating LLM comparisons."""

    def __init__(
        self,
        cache_manager: CacheProtocol,
        providers: dict[str, LLMProviderProtocol],
        settings: Settings,
    ) -> None:
        """Initialize LLM interaction orchestrator.

        Args:
            cache_manager: Cache implementation for response caching.
            providers: Dictionary of available LLM providers.
            settings: Application settings.
        """
        self.cache_manager = cache_manager
        self.providers = providers
        self.settings = settings

    def _get_provider_for_model(self) -> LLMProviderProtocol:
        """Get the appropriate provider for the configured model."""
        # Use the default provider from structured configuration
        provider_key = self.settings.DEFAULT_LLM_PROVIDER.lower()

        if provider_key not in self.providers:
            available_providers = list(self.providers.keys())
            logger.warning(
                f"Default provider '{provider_key}' not available. Available providers: "
                f"{available_providers}. Using first available provider."
            )
            provider_key = available_providers[0] if available_providers else "openai"

        logger.debug(
            f"Using provider '{provider_key}' with model '{self.settings.DEFAULT_LLM_MODEL}'"
        )
        return self.providers[provider_key]

    async def perform_comparisons(
        self,
        tasks: list[ComparisonTask],
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> list[ComparisonResult]:
        """Perform multiple comparison tasks using configured LLM providers.

        Args:
            tasks: List of comparison tasks to process.
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

        # Create semaphore for concurrency control
        max_concurrent_requests = getattr(self.settings, "max_concurrent_llm_requests", 3)
        semaphore = asyncio.Semaphore(max_concurrent_requests)

        async def process_task(task: ComparisonTask) -> ComparisonResult:
            """Process a single comparison task with caching and error handling."""
            async with semaphore:
                # Generate cache key from the prompt and override parameters for proper caching
                cache_key = self.cache_manager.generate_hash(
                    f"{task.prompt}|model:{model_override}|temp:{temperature_override}|tokens:{max_tokens_override}"
                )

                # Check cache first
                cached_response = self.cache_manager.get_from_cache(cache_key)
                if cached_response:
                    logger.debug(
                        f"Cache hit for task with essays {task.essay_a.id}-{task.essay_b.id}"
                    )
                    try:
                        llm_assessment = LLMAssessmentResponseSchema(**cached_response)
                        return ComparisonResult(
                            task=task,
                            llm_assessment=llm_assessment,
                            from_cache=True,
                            prompt_hash=cache_key,
                            error_message=None,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to create ComparisonResult from cached data for task "
                            f"{task.essay_a.id}-{task.essay_b.id}: {e}"
                        )
                        # Continue to make fresh request if cache data is invalid

                # Make fresh API request
                try:
                    response_data, error_message = await provider.generate_comparison(
                        user_prompt=task.prompt,
                        system_prompt_override=None,
                        model_override=model_override,
                        temperature_override=temperature_override,
                        max_tokens_override=max_tokens_override,
                    )

                    if response_data:
                        # Cache successful response
                        self.cache_manager.add_to_cache(cache_key, response_data)

                        llm_assessment = LLMAssessmentResponseSchema(**response_data)
                        return ComparisonResult(
                            task=task,
                            llm_assessment=llm_assessment,
                            from_cache=False,
                            prompt_hash=cache_key,
                            error_message=None,
                        )
                    else:
                        logger.error(
                            f"Task with essays {task.essay_a.id}-{task.essay_b.id} "
                            f"failed: {error_message}"
                        )
                        return ComparisonResult(
                            task=task,
                            llm_assessment=None,
                            from_cache=False,
                            prompt_hash=cache_key,
                            error_message=error_message,
                        )

                except Exception as e:
                    logger.error(
                        f"Unexpected error processing task {task.essay_a.id}-{task.essay_b.id}: "
                        f"{e}",
                        exc_info=True,
                    )
                    return ComparisonResult(
                        task=task,
                        llm_assessment=None,
                        from_cache=False,
                        prompt_hash=cache_key,
                        error_message=f"Unexpected error: {e!s}",
                    )

        # Process all tasks concurrently
        try:
            results = await asyncio.gather(
                *[process_task(task) for task in tasks],
                return_exceptions=True,
            )

            # Handle any exceptions from gather
            final_results = []
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
                            from_cache=False,
                            error_message=f"Task execution failed: {result!s}",
                        )
                    )
                else:
                    final_results.append(result)

            # Log summary
            successful_tasks = sum(1 for r in final_results if r.llm_assessment is not None)
            logger.info(
                f"Completed {len(tasks)} comparison tasks. "
                f"Successful: {successful_tasks}, Failed: {len(tasks) - successful_tasks}"
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
                    from_cache=False,
                    error_message=f"Critical processing error: {e!s}",
                )
                for task in tasks
            ]
