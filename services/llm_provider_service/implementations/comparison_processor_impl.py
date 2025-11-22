"""Comparison processor implementation - handles domain logic for LLM comparisons."""

import time
from typing import Any, Dict
from uuid import UUID

from common_core import LLMProviderType
from huleedu_service_libs.error_handling import (
    raise_external_service_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.internal_models import (
    BatchComparisonItem,
    LLMOrchestratorResponse,
)
from services.llm_provider_service.protocols import (
    ComparisonProcessorProtocol,
    LLMEventPublisherProtocol,
    LLMProviderProtocol,
)

logger = create_service_logger(__name__)


class ComparisonProcessorImpl(ComparisonProcessorProtocol):
    """Processes LLM comparisons - domain logic only."""

    def __init__(
        self,
        providers: Dict[LLMProviderType, LLMProviderProtocol],
        event_publisher: LLMEventPublisherProtocol,
        settings: Settings,
    ):
        """Initialize processor with domain dependencies."""
        self.providers = providers
        self.event_publisher = event_publisher
        self.settings = settings

    async def process_comparison(
        self,
        provider: LLMProviderType,
        user_prompt: str,
        correlation_id: UUID,
        prompt_blocks: list[dict[str, Any]] | None = None,
        **overrides: Any,
    ) -> LLMOrchestratorResponse:
        """Process LLM comparison without infrastructure concerns.

        This is pure domain logic - no queuing, no callbacks.
        Used by QueueProcessor for actual LLM invocation.
        """
        start_time = time.time()

        try:
            provider_impl = self.providers[provider]

            # Call the provider with parameters
            result = await provider_impl.generate_comparison(
                user_prompt=user_prompt,
                prompt_blocks=prompt_blocks,
                correlation_id=correlation_id,
                system_prompt_override=overrides.get("system_prompt_override"),
                model_override=overrides.get("model_override"),
                temperature_override=overrides.get("temperature_override"),
                max_tokens_override=overrides.get("max_tokens_override"),
            )

            response_time_ms = int((time.time() - start_time) * 1000)

            # Build token usage and cost estimate
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
                    "processing_context": "domain_processor",
                },
            )

            logger.info(
                f"Comparison processing successful for provider {provider.value}, "
                f"correlation_id: {correlation_id}, "
                f"response_time: {response_time_ms}ms"
            )

            # Return orchestrator response
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
                trace_id=None,  # Will be set by trace manager in integration layer
                metadata=result.metadata,
            )

        except HuleEduError:
            # Provider error - already logged, re-raise for queue processor
            response_time_ms = int((time.time() - start_time) * 1000)
            await self._handle_provider_failure(
                provider=provider,
                correlation_id=correlation_id,
                error="Provider error occurred during processing",
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
                operation="comparison_processor_process",
                external_service=f"{provider.value}_provider",
                message=error_msg,
                correlation_id=correlation_id,
                details={"provider": provider.value, "processing_context": "domain_processor"},
            )

    async def process_comparison_batch(
        self,
        items: list[BatchComparisonItem],
    ) -> list[LLMOrchestratorResponse]:
        """Process a batch of comparisons sequentially to preserve behaviour."""
        results: list[LLMOrchestratorResponse] = []
        for item in items:
            overrides = item.overrides or {}
            result = await self.process_comparison(
                provider=item.provider,
                user_prompt=item.user_prompt,
                prompt_blocks=item.prompt_blocks,
                correlation_id=item.correlation_id,
                **overrides,
            )
            results.append(result)
        return results

    def _estimate_cost(self, provider: str, token_usage: Dict[str, int]) -> float:
        """Estimate cost based on provider and token usage."""
        # Cost estimation logic per provider
        cost_per_1k_tokens = {
            "anthropic": 0.01,
            "openai": 0.015,
            "google": 0.005,
            "openrouter": 0.02,
            "mock": 0.0,
        }

        rate = cost_per_1k_tokens.get(provider, 0.01)
        total_tokens = token_usage.get("total_tokens", 0)
        return (total_tokens / 1000.0) * rate

    async def _handle_provider_failure(
        self,
        provider: LLMProviderType,
        correlation_id: UUID,
        error: str,
        response_time_ms: int,
    ) -> None:
        """Handle provider failures by publishing failure events."""
        await self.event_publisher.publish_llm_provider_failure(
            provider=provider.value,
            failure_type="provider_error",
            correlation_id=correlation_id,
            error_details=error,
            circuit_breaker_opened=False,  # Circuit breaker handled at infrastructure layer
        )

        await self.event_publisher.publish_llm_request_completed(
            provider=provider.value,
            correlation_id=correlation_id,
            success=False,
            response_time_ms=response_time_ms,
            metadata={
                "request_type": "comparison",
                "error_message": error,
                "failure_type": "provider_error",
                "processing_context": "domain_processor",
            },
        )
