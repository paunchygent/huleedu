"""LLM orchestrator implementation for provider selection and request handling."""

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability.tracing import get_current_trace_id

from common_core import CircuitBreakerState, LLMProviderType
from services.llm_provider_service.api_models import LLMComparisonRequest
from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import (
    HuleEduError,
    raise_configuration_error,
    raise_external_service_error,
    raise_llm_queue_full_error,
)
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import (
    LLMOrchestratorResponse,
    LLMQueuedResult,
)
from services.llm_provider_service.protocols import (
    LLMEventPublisherProtocol,
    LLMOrchestratorProtocol,
    LLMProviderProtocol,
    QueueManagerProtocol,
)
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.orchestrator")


class LLMOrchestratorImpl(LLMOrchestratorProtocol):
    """Orchestrates LLM requests across providers with queuing for resilience."""

    def __init__(
        self,
        providers: Dict[LLMProviderType, LLMProviderProtocol],
        event_publisher: LLMEventPublisherProtocol,
        queue_manager: QueueManagerProtocol,
        trace_context_manager: TraceContextManagerImpl,
        settings: Settings,
    ):
        """Initialize LLM orchestrator.

        Args:
            providers: Dictionary of available LLM providers
            event_publisher: Event publisher for usage tracking
            queue_manager: Queue manager for resilient request handling
            trace_context_manager: Trace context manager for distributed tracing
            settings: Service settings
        """
        self.providers = providers
        self.event_publisher = event_publisher
        self.queue_manager = queue_manager
        self.trace_context_manager = trace_context_manager
        self.settings = settings

    async def perform_comparison(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        **overrides: Any,
    ) -> LLMOrchestratorResponse | LLMQueuedResult:
        """Perform LLM comparison with provider-first logic and queuing fallback.

        Args:
            provider: LLM provider to use
            user_prompt: The comparison prompt
            essay_a: First essay to compare
            essay_b: Second essay to compare
            correlation_id: Request correlation ID
            **overrides: Additional parameter overrides

        Returns:
            LLMOrchestratorResponse for immediate results or LLMQueuedResult for queued processing

        Raises:
            HuleEduError: On any failure to perform comparison
        """
        start_time = time.time()

        # Validate provider exists
        if provider not in self.providers:
            available = [p.value for p in self.providers.keys()]
            error_msg = f"Provider '{provider.value}' not found. Available: {available}"
            logger.error(error_msg)
            raise_configuration_error(
                service="llm_provider_service",
                operation="orchestrator_perform_comparison",
                config_key="provider",
                message=error_msg,
                correlation_id=correlation_id,
                details={"requested_provider": provider.value, "available_providers": available},
            )

        # Publish request started event
        await self.event_publisher.publish_llm_request_started(
            provider=provider.value,
            correlation_id=correlation_id,
            metadata={
                "request_type": "comparison",
                **overrides,
            },
        )

        # Check provider availability FIRST
        is_available = await self._is_provider_available(provider)

        if not is_available:
            # Provider unavailable - queue the request
            return await self._queue_request(
                provider=provider,
                user_prompt=user_prompt,
                essay_a=essay_a,
                essay_b=essay_b,
                correlation_id=correlation_id,
                overrides=overrides,
                start_time=start_time,
            )

        # Provider is available - make direct LLM request
        return await self._make_llm_request(
            provider=provider,
            user_prompt=user_prompt,
            essay_a=essay_a,
            essay_b=essay_b,
            correlation_id=correlation_id,
            overrides=overrides,
            start_time=start_time,
        )

    async def _queue_request(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        overrides: Dict[str, Any],
        start_time: float,
    ) -> LLMQueuedResult:
        """Queue a request when provider is unavailable."""
        logger.warning(
            f"Provider {provider.value} is unavailable, queuing request. "
            f"correlation_id: {correlation_id}"
        )

        # Create queued request
        request_data = LLMComparisonRequest(
            user_prompt=user_prompt,
            essay_a=essay_a,
            essay_b=essay_b,
            correlation_id=correlation_id,
            metadata=overrides,
        )

        # Capture current trace context for queue processing
        trace_context = self.trace_context_manager.capture_trace_context_for_queue()

        queued_request = QueuedRequest(
            request_data=request_data,
            priority=self._get_request_priority(overrides),
            ttl=timedelta(hours=self.settings.QUEUE_REQUEST_TTL_HOURS),
            correlation_id=correlation_id,
            trace_context=trace_context,
            size_bytes=0,  # Will be calculated
        )
        queued_request.size_bytes = queued_request.calculate_size()

        # Try to enqueue
        success = await self.queue_manager.enqueue(queued_request)

        if success:
            # Get queue stats for estimated wait time
            queue_stats = await self.queue_manager.get_queue_stats()

            # Publish queued event
            await self.event_publisher.publish_llm_request_completed(
                provider=provider.value,
                correlation_id=correlation_id,
                success=True,
                response_time_ms=int((time.time() - start_time) * 1000),
                metadata={
                    "request_type": "comparison",
                    "queued": True,
                    "queue_id": str(queued_request.queue_id),
                    "priority": queued_request.priority,
                },
            )

            # Return queued result
            return LLMQueuedResult(
                queue_id=queued_request.queue_id,
                correlation_id=correlation_id,
                provider=provider,
                status="queued",
                estimated_wait_minutes=queue_stats.estimated_wait_minutes,
                priority=queued_request.priority,
                queued_at=datetime.now(timezone.utc).isoformat(),
            )
        else:
            # Queue is full
            queue_stats = await self.queue_manager.get_queue_stats()

            await self.event_publisher.publish_llm_provider_failure(
                provider=provider.value,
                failure_type="queue_full",
                correlation_id=correlation_id,
                error_details=f"Queue at capacity: {queue_stats.usage_percent:.1f}%",
                circuit_breaker_opened=True,
            )

            raise_llm_queue_full_error(
                service="llm_provider_service",
                operation="orchestrator_queue_request",
                queue_size=queue_stats.current_size,
                message="Service temporarily at capacity. Please try again later.",
                correlation_id=correlation_id,
                details={
                    "provider": provider.value,
                    "queue_usage_percent": queue_stats.usage_percent,
                    "retry_after_seconds": 300,
                },
            )

    async def _make_llm_request(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        overrides: Dict[str, Any],
        start_time: float,
    ) -> LLMOrchestratorResponse:
        """Make direct LLM request when provider is available."""
        try:
            provider_impl = self.providers[provider]

            # Create provider call span for distributed tracing
            with self.trace_context_manager.start_provider_call_span(
                provider=provider.value,
                model=overrides.get("model_override") or "default",
                correlation_id=correlation_id,
            ):
                # Call the provider with tracing context
                result = await provider_impl.generate_comparison(
                    user_prompt=user_prompt,
                    essay_a=essay_a,
                    essay_b=essay_b,
                    correlation_id=correlation_id,
                    system_prompt_override=overrides.get("system_prompt_override"),
                    model_override=overrides.get("model_override"),
                    temperature_override=overrides.get("temperature_override"),
                    max_tokens_override=overrides.get("max_tokens_override"),
                )

            response_time_ms = int((time.time() - start_time) * 1000)

            # Success - fresh LLM response
            token_usage_dict: Dict[str, int] = {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
            }
            cost_estimate_value: float = (
                self._estimate_cost(provider.value, token_usage_dict) or 0.0
            )

            # Publish completion event
            await self.event_publisher.publish_llm_request_completed(
                provider=provider.value,
                correlation_id=correlation_id,
                success=True,
                response_time_ms=response_time_ms,
                metadata={
                    "request_type": "comparison",
                    "token_usage": token_usage_dict,
                    "cost_estimate": cost_estimate_value,
                    "model_used": result.model,
                },
            )

            logger.info(
                f"LLM request successful for provider {provider.value}, "
                f"correlation_id: {correlation_id}, "
                f"response_time: {response_time_ms}ms"
            )

            # Capture current trace ID from active span
            current_trace_id = get_current_trace_id()

            # Return fresh orchestrator response
            return LLMOrchestratorResponse(
                winner=result.winner,
                justification=result.justification,
                confidence=result.confidence,
                provider=provider,
                model=result.model,
                response_time_ms=response_time_ms,
                token_usage=token_usage_dict,
                cost_estimate=cost_estimate_value,
                correlation_id=correlation_id,
                trace_id=current_trace_id,
            )

        except HuleEduError:
            # Provider error - already logged and traced
            response_time_ms = int((time.time() - start_time) * 1000)
            await self._handle_provider_failure(
                provider=provider,
                correlation_id=correlation_id,
                error="Provider error occurred",
                response_time_ms=response_time_ms,
            )
            raise
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

            raise_external_service_error(
                service="llm_provider_service",
                operation="orchestrator_llm_request",
                external_service=f"{provider.value}_provider",
                message=error_msg,
                correlation_id=correlation_id,
                details={"provider": provider.value},
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

    async def test_provider(self, provider: LLMProviderType, correlation_id: UUID) -> bool:
        """Test provider connectivity and availability.

        Args:
            provider: Provider to test
            correlation_id: Request correlation ID for tracing

        Returns:
            True if provider is available and functional

        Raises:
            HuleEduError: On provider test failure with details
        """
        if provider not in self.providers:
            raise_configuration_error(
                service="llm_provider_service",
                operation="orchestrator_test_provider",
                config_key="provider",
                message=f"Provider '{provider.value}' not found",
                correlation_id=correlation_id,
                details={"requested_provider": provider.value},
            )

        try:
            # Simple test prompt
            test_prompt = "Complete this sentence in exactly 5 words: The weather today is"

            await self.providers[provider].generate_comparison(
                user_prompt=test_prompt,
                essay_a="Test essay A",
                essay_b="Test essay B",
                correlation_id=correlation_id,
            )

            return True

        except HuleEduError:
            # Provider error - already logged and traced
            raise
        except Exception as e:
            raise_external_service_error(
                service="llm_provider_service",
                operation="orchestrator_test_provider",
                external_service=f"{provider.value}_provider",
                message=f"Provider test failed with exception: {str(e)}",
                correlation_id=correlation_id,
                details={"provider": provider.value},
            )

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

    async def _is_provider_available(self, provider: LLMProviderType) -> bool:
        """Check if a provider is available for requests.

        Args:
            provider: The provider to check

        Returns:
            True if provider is available, False otherwise
        """
        # Check if provider exists
        if provider not in self.providers:
            return False

        # Check circuit breaker state if available
        provider_impl = self.providers[provider]
        if hasattr(provider_impl, "__wrapped__"):
            # Provider is wrapped with circuit breaker
            original = provider_impl
            if hasattr(original, "_circuit_breaker"):
                circuit_breaker = original._circuit_breaker
                return bool(circuit_breaker.state != CircuitBreakerState.OPEN)

        # No circuit breaker or not wrapped - assume available
        return True

    def _get_request_priority(self, overrides: Dict[str, Any]) -> int:
        """Determine request priority based on metadata.

        Args:
            overrides: Request metadata

        Returns:
            Priority level (0-10, higher = more urgent)
        """
        # CJ Assessment requests get higher priority
        if overrides.get("service_type") == "cj_assessment":
            return 8

        # User-specified priority
        if "priority" in overrides:
            return max(0, min(10, int(overrides["priority"])))

        # Default priority
        return 5
