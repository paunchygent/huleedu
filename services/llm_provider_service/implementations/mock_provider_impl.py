"""Mock LLM provider implementation for testing."""

import random
from typing import Tuple
from uuid import uuid4

from huleedu_service_libs.logging_utils import create_service_logger

from common_core import EssayComparisonWinner, LLMProviderType
from common_core.error_enums import ErrorCode
from services.llm_provider_service.config import Settings
from services.llm_provider_service.internal_models import LLMProviderError, LLMProviderResponse
from services.llm_provider_service.protocols import LLMProviderProtocol

logger = create_service_logger("llm_provider_service.mock_provider")


class MockProviderImpl(LLMProviderProtocol):
    """Mock LLM provider for testing without API calls."""

    def __init__(self, settings: Settings, seed: int | None = None, performance_mode: bool = False):
        """Initialize mock provider.

        Args:
            settings: Service settings
            seed: Optional random seed for reproducible tests
            performance_mode: If True, disables error simulation for performance testing
        """
        self.settings = settings
        self.performance_mode = performance_mode
        if seed is not None:
            random.seed(seed)

    async def generate_comparison(
        self,
        user_prompt: str,
        essay_a: str,
        essay_b: str,
        system_prompt_override: str | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> Tuple[LLMProviderResponse | None, LLMProviderError | None]:
        """Generate mock comparison result.

        Args:
            user_prompt: The comparison prompt
            essay_a: First essay to compare
            essay_b: Second essay to compare
            system_prompt_override: Optional system prompt override
            model_override: Optional model override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            Tuple of (response_model, error_model)
        """
        # Simulate occasional errors (5% chance) - skip in performance mode
        if not self.performance_mode and random.random() < 0.05:
            logger.warning("Mock provider simulating error")
            return None, LLMProviderError(
                error_type=ErrorCode.EXTERNAL_SERVICE_ERROR,
                error_message="Mock provider simulated error",
                provider=LLMProviderType.MOCK,
                correlation_id=uuid4(),
                is_retryable=True,
            )

        # Randomly select winner with slight bias towards Essay B
        winner = (
            EssayComparisonWinner.ESSAY_A
            if random.random() < 0.45
            else EssayComparisonWinner.ESSAY_B
        )
        confidence = round(random.uniform(0.6, 0.95), 2)

        # Generate realistic justification based on winner
        justification_options = {
            EssayComparisonWinner.ESSAY_A: [
                "Essay A demonstrates stronger argumentation and clearer structure.",
                "Essay A provides more compelling evidence and better analysis.",
                "Essay A has superior organization and more persuasive language.",
                "Essay A shows better understanding of the topic with more detailed examples.",
                "Essay A maintains better coherence and has stronger conclusions.",
            ],
            EssayComparisonWinner.ESSAY_B: [
                "Essay B presents a more convincing argument with better supporting evidence.",
                "Essay B demonstrates superior writing quality and clearer expression.",
                "Essay B shows more sophisticated analysis and deeper understanding.",
                "Essay B has better paragraph structure and more effective transitions.",
                "Essay B provides more relevant examples and stronger justification.",
            ],
        }

        justification = random.choice(justification_options[winner])

        # Calculate mock token usage
        prompt_tokens = len(user_prompt.split()) + len(essay_a.split()) + len(essay_b.split())
        completion_tokens = len(justification.split()) + 10  # Add some for structure
        total_tokens = prompt_tokens + completion_tokens

        response = LLMProviderResponse(
            winner=winner,
            justification=justification,
            confidence=confidence,
            provider=LLMProviderType.MOCK,
            model=model_override or "mock-model-v1",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            raw_response={
                "mock_metadata": {
                    "temperature": temperature_override or 0.7,
                    "seed": random.getstate()[1][0] if hasattr(random, "getstate") else None,
                }
            },
        )

        logger.debug(
            f"Mock provider generated response: winner={winner.value}, confidence={confidence}"
        )
        return response, None
