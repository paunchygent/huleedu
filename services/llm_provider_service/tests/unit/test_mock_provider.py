"""Unit tests for mock LLM provider."""

from __future__ import annotations

import pytest

from common_core.error_enums import ErrorCode
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.mock_provider_impl import MockProviderImpl


@pytest.mark.asyncio
async def test_mock_provider_successful_comparison() -> None:
    """Test mock provider returns valid comparison response."""
    # Arrange
    settings = Settings()
    provider = MockProviderImpl(settings, seed=42)  # Fixed seed for deterministic tests

    # Act
    result, error = await provider.generate_comparison(
        user_prompt="Compare these essays",
        essay_a="This is essay A about climate change.",
        essay_b="This is essay B about global warming.",
    )

    # Assert
    assert error is None
    assert result is not None
    assert result.choice in ["A", "B"]
    assert len(result.reasoning) > 0
    assert 0.0 <= result.confidence <= 1.0
    assert result.provider == "mock"
    assert result.model == "mock-model-v1"
    assert result.prompt_tokens > 0
    assert result.completion_tokens > 0
    assert result.total_tokens == result.prompt_tokens + result.completion_tokens


@pytest.mark.asyncio
async def test_mock_provider_with_overrides() -> None:
    """Test mock provider respects model override."""
    # Arrange
    settings = Settings()
    provider = MockProviderImpl(settings, seed=42)

    # Act
    result, error = await provider.generate_comparison(
        user_prompt="Compare these essays",
        essay_a="Essay A content",
        essay_b="Essay B content",
        model_override="custom-model-v2",
    )

    # Assert
    assert error is None
    assert result is not None
    assert result.model == "custom-model-v2"


@pytest.mark.asyncio
async def test_mock_provider_token_calculation() -> None:
    """Test mock provider calculates tokens based on input."""
    # Arrange
    settings = Settings()
    provider = MockProviderImpl(settings, seed=42)

    short_essay = "Short essay."
    long_essay = " ".join(["This is a much longer essay with many words."] * 10)

    # Act
    result_short, _ = await provider.generate_comparison(
        user_prompt="Compare",
        essay_a=short_essay,
        essay_b=short_essay,
    )

    result_long, _ = await provider.generate_comparison(
        user_prompt="Compare",
        essay_a=long_essay,
        essay_b=long_essay,
    )

    # Assert
    assert result_short is not None and result_long is not None
    assert result_short.prompt_tokens < result_long.prompt_tokens
    assert result_short.total_tokens < result_long.total_tokens


@pytest.mark.asyncio
async def test_mock_provider_error_simulation() -> None:
    """Test mock provider error simulation."""
    # Arrange
    settings = Settings()
    # We need to test multiple times since error has 5% chance
    error_occurred = False

    for seed in range(100):  # Try different seeds
        provider = MockProviderImpl(settings, seed=seed)
        result, error = await provider.generate_comparison(
            user_prompt="Compare",
            essay_a="Essay A",
            essay_b="Essay B",
        )

        if error is not None:
            error_occurred = True
            # Verify error structure
            assert error.error_type == ErrorCode.EXTERNAL_SERVICE_ERROR
            assert error.error_message == "Mock provider simulated error"
            assert error.provider == "mock"
            assert error.is_retryable is True
            assert result is None
            break

    # Assert that we found at least one error in our attempts
    assert error_occurred, "No error occurred in 100 attempts (5% chance each)"
