"""Unit tests for MockProviderImpl realism toggles."""

from typing import Any
from uuid import uuid4

import pytest

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.mock_provider_impl import MockProviderImpl
from services.llm_provider_service.internal_models import LLMProviderResponse


def _base_settings(**overrides: Any) -> Settings:
    """Create Settings with mock provider defaults for testing."""
    return Settings(
        ALLOW_MOCK_PROVIDER=overrides.get("ALLOW_MOCK_PROVIDER", True),
        USE_MOCK_LLM=overrides.get("USE_MOCK_LLM", False),
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
