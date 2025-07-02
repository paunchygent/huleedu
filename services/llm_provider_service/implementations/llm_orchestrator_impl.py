"""LLM orchestrator implementation for provider selection and request handling."""

import time
from typing import Any, Dict, Tuple
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from common_core import LLMProviderType
from common_core.error_enums import ErrorCode
from services.llm_provider_service.config import Settings
from services.llm_provider_service.internal_models import (
    LLMOrchestratorResponse,
    LLMProviderError,
)
from services.llm_provider_service.protocols import (
    LLMCacheManagerProtocol,
    LLMEventPublisherProtocol,
    LLMOrchestratorProtocol,
    LLMProviderProtocol,
)

logger = create_service_logger("llm_provider_service.orchestrator")


class LLMOrchestratorImpl(LLMOrchestratorProtocol):
    """Orchestrates LLM requests across providers with caching and events."""

    def __init__(
        self,
        providers: Dict[LLMProviderType, LLMProviderProtocol],
        cache_manager: LLMCacheManagerProtocol,
        event_publisher: LLMEventPublisherProtocol,
        settings: Settings,
    ):
        """Initialize LLM orchestrator.

        Args:
            providers: Dictionary of available LLM providers
            cache_manager: Cache manager for responses
            event_publisher: Event publisher for usage tracking
            settings: Service settings
        """
        self.providers = providers
        self.cache_manager = cache_manager
        self.event_publisher = event_publisher

        self.settings = settings

    async def perform_comparison(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        **overrides: Any,
    ) -> Tuple[LLMOrchestratorResponse | None, LLMProviderError | None]:
        """Perform LLM comparison with provider selection.

        Args:
            provider: LLM provider to use
            user_prompt: The comparison prompt
            essay_a: First essay to compare
            essay_b: Second essay to compare
            correlation_id: Request correlation ID
            **overrides: Additional parameter overrides

        Returns:
            Tuple of (response_dict, error_message)
        """
        start_time = time.time()

        # Validate provider
        if provider not in self.providers:
            available = [p.value for p in self.providers.keys()]
            error_msg = f"Provider '{provider.value}' not found. Available: {available}"
            logger.error(error_msg)
            return None, LLMProviderError(
                error_type=ErrorCode.CONFIGURATION_ERROR,
                error_message=error_msg,
                provider=provider,
                correlation_id=correlation_id,
                is_retryable=False,
            )

        # Generate cache key
        cache_key = self.cache_manager.generate_cache_key(
            provider=provider.value,
            user_prompt=user_prompt,
            essay_a=essay_a,
            essay_b=essay_b,
            **overrides,
        )

        # Publish request started event
        await self.event_publisher.publish_llm_request_started(
            provider=provider.value,
            correlation_id=correlation_id,
            metadata={
                "request_type": "comparison",
                "cache_key": cache_key,
                **overrides,
            },
        )

        # Check cache first
        cached_response = await self.cache_manager.get_cached_response(cache_key)
        if cached_response:
            response_time_ms = int((time.time() - start_time) * 1000)

            # Publish completion event for cache hit
            await self.event_publisher.publish_llm_request_completed(
                provider=provider.value,
                correlation_id=correlation_id,
                success=True,
                response_time_ms=response_time_ms,
                metadata={
                    "request_type": "comparison",
                    "cached": True,
                    "cache_key": cache_key,
                },
            )

            logger.info(
                f"Cache hit for provider {provider.value}, correlation_id: {correlation_id}"
            )

            # Construct response from cached data
            return LLMOrchestratorResponse(
                choice=cached_response.get("choice", "A"),
                reasoning=cached_response.get("reasoning", ""),
                confidence=cached_response.get("confidence", 0.5),
                provider=provider,
                model=cached_response.get("model", "unknown"),
                response_time_ms=response_time_ms,
                cached=True,
                token_usage=cached_response.get(
                    "token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                ),
                cost_estimate=cached_response.get("cost_estimate", 0.0),
                correlation_id=correlation_id,
                trace_id=cached_response.get("trace_id"),
            ), None

        # Make actual LLM request
        try:
            provider_impl = self.providers[provider]

            # Call the provider
            result, error = await provider_impl.generate_comparison(
                user_prompt=user_prompt,
                essay_a=essay_a,
                essay_b=essay_b,
                system_prompt_override=overrides.get("system_prompt_override"),
                model_override=overrides.get("model_override"),
                temperature_override=overrides.get("temperature_override"),
                max_tokens_override=overrides.get("max_tokens_override"),
            )

            response_time_ms = int((time.time() - start_time) * 1000)

            if result:
                # Success - cache the provider response
                token_usage_dict: Dict[str, int] = {
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "total_tokens": result.total_tokens,
                }
                cost_estimate_value: float = (
                    self._estimate_cost(provider.value, token_usage_dict) or 0.0
                )

                cache_data = {
                    "choice": result.choice,
                    "reasoning": result.reasoning,
                    "confidence": result.confidence,
                    "model": result.model,
                    "token_usage": token_usage_dict,
                    "cost_estimate": cost_estimate_value,
                }
                await self.cache_manager.cache_response(cache_key, cache_data)

                # Publish completion event
                await self.event_publisher.publish_llm_request_completed(
                    provider=provider.value,
                    correlation_id=correlation_id,
                    success=True,
                    response_time_ms=response_time_ms,
                    metadata={
                        "request_type": "comparison",
                        "cached": False,
                        "cache_key": cache_key,
                        "token_usage": cache_data["token_usage"],
                        "cost_estimate": cache_data["cost_estimate"],
                        "model_used": result.model,
                    },
                )

                logger.info(
                    f"LLM request successful for provider {provider.value}, "
                    f"correlation_id: {correlation_id}, "
                    f"response_time: {response_time_ms}ms"
                )

                # Return orchestrator response
                return LLMOrchestratorResponse(
                    choice=result.choice,
                    reasoning=result.reasoning,
                    confidence=result.confidence,
                    provider=provider,
                    model=result.model,
                    response_time_ms=response_time_ms,
                    cached=False,
                    token_usage=token_usage_dict,
                    cost_estimate=cost_estimate_value,
                    correlation_id=correlation_id,
                    trace_id=None,  # TODO: Add OpenTelemetry trace ID
                ), None

            else:
                # Request failed
                error_message = error.error_message if error else "Unknown error"
                await self._handle_provider_failure(
                    provider=provider,
                    correlation_id=correlation_id,
                    error=error_message,
                    response_time_ms=response_time_ms,
                )

                return None, error  # error is already LLMProviderError

        except Exception as e:
            # Unexpected error
            response_time_ms = int((time.time() - start_time) * 1000)
            error_msg = f"Unexpected error calling provider {provider.value}: {str(e)}"
            logger.error(error_msg, exc_info=True)

            await self._handle_provider_failure(
                provider=provider,
                correlation_id=correlation_id,
                error=error_msg,
                response_time_ms=response_time_ms,
            )

            return None, LLMProviderError(
                error_type=ErrorCode.EXTERNAL_SERVICE_ERROR,
                error_message=error_msg,
                provider=provider,
                correlation_id=correlation_id,
                is_retryable=True,
            )

    async def _handle_provider_failure(
        self,
        provider: LLMProviderType,
        correlation_id: UUID,
        error: str,
        response_time_ms: int,
    ) -> None:
        """Handle provider failure by publishing appropriate events.

        Args:
            provider: Provider that failed
            correlation_id: Request correlation ID
            error: Error message
            response_time_ms: Response time before failure
        """
        # Determine failure type
        failure_type = "unknown"
        if "timeout" in error.lower():
            failure_type = "timeout"
        elif "rate limit" in error.lower() or "429" in error:
            failure_type = "rate_limit"
        elif "authentication" in error.lower() or "401" in error:
            failure_type = "authentication"
        elif "service unavailable" in error.lower() or "503" in error:
            failure_type = "service_unavailable"

        # Publish failure event
        await self.event_publisher.publish_llm_provider_failure(
            provider=provider.value,
            failure_type=failure_type,
            correlation_id=correlation_id,
            error_details=error,
            circuit_breaker_opened=False,  # Would be set by circuit breaker
        )

        # Publish completion event with failure
        await self.event_publisher.publish_llm_request_completed(
            provider=provider.value,
            correlation_id=correlation_id,
            success=False,
            response_time_ms=response_time_ms,
            metadata={
                "request_type": "comparison",
                "error_message": error,
                "failure_type": failure_type,
            },
        )

    async def test_provider(self, provider: LLMProviderType) -> Tuple[bool, str]:
        """Test provider connectivity and availability.

        Args:
            provider: Provider to test

        Returns:
            Tuple of (success, message)
        """
        if provider not in self.providers:
            return False, f"Provider '{provider.value}' not found"

        try:
            # Simple test prompt
            test_prompt = "Complete this sentence in exactly 5 words: The weather today is"

            result, error = await self.providers[provider].generate_comparison(
                user_prompt=test_prompt,
                essay_a="Test essay A",
                essay_b="Test essay B",
            )

            if error:
                return False, f"Provider test failed: {error.error_message}"

            return True, f"Provider '{provider.value}' is operational"

        except Exception as e:
            return False, f"Provider test failed with exception: {str(e)}"

    def _estimate_cost(self, provider: str, token_usage: Dict[str, int] | None) -> float | None:
        """Estimate cost based on provider and token usage.

        Args:
            provider: Provider name
            token_usage: Token usage dict with prompt_tokens and completion_tokens

        Returns:
            Estimated cost in USD or None
        """
        if not token_usage:
            return None

        # Simple cost estimation - would be expanded with actual pricing
        # These are example rates per 1K tokens
        cost_per_1k_tokens = {
            "anthropic": {"prompt": 0.015, "completion": 0.075},  # Claude 3 Opus
            "openai": {"prompt": 0.03, "completion": 0.06},  # GPT-4
            "google": {"prompt": 0.001, "completion": 0.002},  # Gemini Pro
            "openrouter": {"prompt": 0.002, "completion": 0.004},  # Variable
        }

        provider_costs = cost_per_1k_tokens.get(provider)
        if not provider_costs:
            return None

        prompt_tokens = token_usage.get("prompt_tokens", 0)
        completion_tokens = token_usage.get("completion_tokens", 0)

        cost = (prompt_tokens / 1000) * provider_costs["prompt"] + (
            completion_tokens / 1000
        ) * provider_costs["completion"]

        return round(cost, 6)  # 6 decimal places for USD
