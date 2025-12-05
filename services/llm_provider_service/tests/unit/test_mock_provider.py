"""Unit tests for MockProviderImpl realism toggles."""

from typing import Any
from uuid import uuid4

import pytest

from services.llm_provider_service.config import MockMode, Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.mock_provider_impl import MockProviderImpl
from services.llm_provider_service.internal_models import LLMProviderResponse


def _base_settings(**overrides: Any) -> Settings:
    """Create Settings with mock provider defaults for testing."""
    return Settings(
        ALLOW_MOCK_PROVIDER=overrides.get("ALLOW_MOCK_PROVIDER", True),
        USE_MOCK_LLM=overrides.get("USE_MOCK_LLM", False),
        MOCK_MODE=overrides.get("MOCK_MODE", MockMode.DEFAULT.value),
        MOCK_PROVIDER_SEED=overrides.get("MOCK_PROVIDER_SEED", 123),
        MOCK_LATENCY_MS=overrides.get("MOCK_LATENCY_MS", 0),
        MOCK_LATENCY_JITTER_MS=overrides.get("MOCK_LATENCY_JITTER_MS", 0),
        MOCK_ERROR_RATE=overrides.get("MOCK_ERROR_RATE", 0.0),
        MOCK_ERROR_CODES=overrides.get("MOCK_ERROR_CODES", [503]),
        MOCK_CACHE_ENABLED=overrides.get("MOCK_CACHE_ENABLED", True),
        MOCK_CACHE_HIT_RATE=overrides.get("MOCK_CACHE_HIT_RATE", 0.0),
        MOCK_TOKENIZER=overrides.get("MOCK_TOKENIZER", "simple"),
        MOCK_TOKENS_PER_WORD=overrides.get("MOCK_TOKENS_PER_WORD", 0.75),
        MOCK_CONFIDENCE_BASE=overrides.get("MOCK_CONFIDENCE_BASE", 4.5),
        MOCK_CONFIDENCE_JITTER=overrides.get("MOCK_CONFIDENCE_JITTER", 0.0),
        MOCK_STREAMING_METADATA=overrides.get("MOCK_STREAMING_METADATA", False),
    )


@pytest.mark.asyncio
async def test_mock_provider_raises_when_error_rate_one() -> None:
    settings = _base_settings(MOCK_ERROR_RATE=1.0, MOCK_ERROR_CODES=[503])
    provider = MockProviderImpl(settings=settings)

    with pytest.raises(HuleEduError) as excinfo:
        await provider.generate_comparison(user_prompt="test", correlation_id=uuid4())

    detail = excinfo.value.error_detail
    assert detail.details.get("status_code") == 503
    assert detail.correlation_id is not None


@pytest.mark.asyncio
async def test_cj_generic_batch_mode_disables_error_simulation() -> None:
    """cj_generic_batch mode should not simulate provider errors even with error_rate=1.0."""
    settings = _base_settings(
        MOCK_MODE=MockMode.CJ_GENERIC_BATCH.value,
        MOCK_ERROR_RATE=1.0,
        MOCK_ERROR_CODES=[503],
    )
    provider = MockProviderImpl(settings=settings)

    # Should not raise, despite error_rate=1.0, because cj_generic_batch is pinned-success.
    resp: LLMProviderResponse = await provider.generate_comparison(
        user_prompt="test", correlation_id=uuid4()
    )

    assert isinstance(resp, LLMProviderResponse)
    assert resp.winner is not None


@pytest.mark.asyncio
async def test_mock_provider_respects_cache_hit_rate() -> None:
    settings = _base_settings(MOCK_CACHE_HIT_RATE=1.0)
    provider = MockProviderImpl(settings=settings)

    resp: LLMProviderResponse = await provider.generate_comparison(
        user_prompt="test prompt", correlation_id=uuid4()
    )

    assert resp.metadata.get("cache_read_input_tokens", 0) > 0
    assert resp.metadata.get("cache_creation_input_tokens", 0) == 0


@pytest.mark.asyncio
async def test_mock_provider_success_when_error_rate_zero() -> None:
    settings = _base_settings(MOCK_ERROR_RATE=0.0)
    provider = MockProviderImpl(settings=settings)

    resp: LLMProviderResponse = await provider.generate_comparison(
        user_prompt="test prompt", correlation_id=uuid4()
    )

    assert isinstance(resp, LLMProviderResponse)
    assert resp.winner is not None
    assert 0.0 <= resp.confidence <= 1.0
    assert resp.metadata.get("prompt_sha256")


@pytest.mark.asyncio
async def test_eng5_anchor_mode_produces_successful_responses() -> None:
    """ENG5 anchor mock mode should be pinned-success and scaled for large tokens."""
    settings = _base_settings(
        MOCK_MODE=MockMode.ENG5_ANCHOR_GPT51_LOW.value,
        MOCK_ERROR_RATE=1.0,
        MOCK_ERROR_CODES=[503],
    )
    provider = MockProviderImpl(settings=settings)

    resp: LLMProviderResponse = await provider.generate_comparison(
        user_prompt="ENG5 anchor comparison prompt",
        correlation_id=uuid4(),
    )

    # Despite error_rate=1.0, ENG5 anchor mode disables simulated errors.
    assert isinstance(resp, LLMProviderResponse)
    assert resp.winner is not None
    # Token scaling for ENG5 anchor mode should approximate large ENG5 prompts.
    assert resp.prompt_tokens >= 1100
    assert resp.completion_tokens >= 40


@pytest.mark.asyncio
async def test_eng5_lower5_mode_produces_successful_responses_in_lower_token_band() -> None:
    """ENG5 LOWER5 mock mode is pinned-success with slightly smaller tokens than full-anchor."""
    settings = _base_settings(
        MOCK_MODE=MockMode.ENG5_LOWER5_GPT51_LOW.value,
        MOCK_ERROR_RATE=1.0,
        MOCK_ERROR_CODES=[503],
    )
    provider = MockProviderImpl(settings=settings)

    resp: LLMProviderResponse = await provider.generate_comparison(
        user_prompt="ENG5 LOWER5 comparison prompt",
        correlation_id=uuid4(),
    )

    # Despite error_rate=1.0, ENG5 LOWER5 mode disables simulated errors.
    assert isinstance(resp, LLMProviderResponse)
    assert resp.winner is not None
    # LOWER5 token scaling should sit below the ENG5 anchor floor but
    # well above generic mock defaults for short prompts.
    assert 1000 <= resp.prompt_tokens < 1100
    assert 30 <= resp.completion_tokens < 40
