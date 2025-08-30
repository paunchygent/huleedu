"""Service-specific circuit breaker LLM provider wrapper.

This module provides a typed wrapper for LLM providers that adds circuit breaker
protection while maintaining full protocol compatibility. This wrapper lives
within the LLM Provider Service to respect architectural boundaries.
"""

from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

from services.llm_provider_service.internal_models import LLMProviderResponse
from services.llm_provider_service.protocols import LLMProviderProtocol

logger = create_service_logger("circuit_breaker_llm_provider")


class CircuitBreakerLLMProvider(LLMProviderProtocol):
    """LLM provider with circuit breaker protection.

    This wrapper implements LLMProviderProtocol and adds circuit breaker
    protection to all LLM operations. It delegates all actual LLM work
    to the underlying provider while providing resilience through the
    circuit breaker pattern.

    This is a SERVICE-SPECIFIC wrapper that lives within the LLM Provider Service
    to respect architectural boundaries. It imports the service's own protocols
    while using the shared CircuitBreaker mechanism.

    Circuit Breaker Behavior:
    - CLOSED: All requests pass through normally
    - OPEN: Requests are blocked and CircuitBreakerError is raised
    - HALF_OPEN: Limited requests allowed to test recovery
    """

    def __init__(self, delegate: LLMProviderProtocol, circuit_breaker: CircuitBreaker) -> None:
        """Initialize circuit breaker LLM provider.

        Args:
            delegate: The actual LLM provider implementation
            circuit_breaker: Circuit breaker for resilience protection
        """
        self._delegate = delegate
        self._circuit_breaker = circuit_breaker

    async def generate_comparison(
        self,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        correlation_id: UUID,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> LLMProviderResponse:
        """Generate LLM comparison with circuit breaker protection.

        Args:
            user_prompt: The comparison prompt
            essay_a: First essay to compare
            essay_b: Second essay to compare
            correlation_id: Request correlation ID for tracing
            system_prompt_override: Optional system prompt override
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            The LLM provider response containing comparison result

        Raises:
            CircuitBreakerError: If circuit is open
            HuleEduError: On any failure to generate comparison
        """
        logger.debug(
            "Generating LLM comparison through circuit breaker",
            extra={
                "correlation_id": str(correlation_id),
                "user_prompt_length": len(user_prompt),
                "essay_a_length": len(essay_a),
                "essay_b_length": len(essay_b),
                "model_override": model_override,
                "provider": self._delegate.__class__.__name__,
            },
        )
        return await self._circuit_breaker.call(
            self._delegate.generate_comparison,
            user_prompt,
            essay_a,
            essay_b,
            correlation_id,
            system_prompt_override,
            model_override,
            temperature_override,
            max_tokens_override,
        )
