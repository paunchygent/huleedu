"""Unit tests for OpenAIProviderImpl GPT-5 family behaviour."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.openai_provider_impl import OpenAIProviderImpl
from services.llm_provider_service.protocols import LLMRetryManagerProtocol


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock aiohttp session."""
    return AsyncMock(spec=aiohttp.ClientSession)


@pytest.fixture
def retry_manager() -> AsyncMock:
    """Retry manager that simply invokes the operation once."""
    retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

    async def mock_with_retry(operation: Any, operation_name: str, **kwargs: Any) -> Any:
        return await operation(**kwargs)

    retry_manager.with_retry.side_effect = mock_with_retry
    return retry_manager


@pytest.fixture
def base_settings() -> MagicMock:
    """Base Settings mock with required attributes."""
    settings = MagicMock(spec=Settings)
    # SecretStr-like mock for API key
    settings.OPENAI_API_KEY = MagicMock()
    settings.OPENAI_API_KEY.get_secret_value.return_value = "test-key"
    settings.LLM_DEFAULT_TEMPERATURE = 0.2
    settings.LLM_DEFAULT_MAX_TOKENS = 1024
    return settings


def _prepare_openai_provider(
    mock_session: AsyncMock, retry_manager: AsyncMock, settings: MagicMock, default_model: str
) -> OpenAIProviderImpl:
    settings.OPENAI_DEFAULT_MODEL = default_model
    provider = OpenAIProviderImpl(
        session=mock_session, settings=settings, retry_manager=retry_manager
    )
    return provider


def _setup_response(mock_session: AsyncMock) -> None:
    """Configure session.post to return a minimal successful response."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "choices": [
                {
                    "message": {
                        "content": '{"winner": "Essay A", "justification": "A", "confidence": 4}'
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
    )

    mock_context = AsyncMock()
    mock_context.__aenter__.return_value = mock_response
    mock_session.post.return_value = mock_context


@pytest.mark.asyncio
async def test_gpt51_payload_uses_reasoning_controls(
    mock_session: AsyncMock, retry_manager: AsyncMock, base_settings: MagicMock
) -> None:
    """GPT-5.1 should use max_completion_tokens and reasoning/text controls."""
    provider = _prepare_openai_provider(
        mock_session=mock_session,
        retry_manager=retry_manager,
        settings=base_settings,
        default_model="gpt-5.1",
    )
    _setup_response(mock_session)

    correlation_id = uuid4()
    await provider.generate_comparison(
        user_prompt="Compare essays",
        correlation_id=correlation_id,
        reasoning_effort="medium",
        output_verbosity="high",
    )

    assert mock_session.post.called
    _, kwargs = mock_session.post.call_args
    payload = kwargs["json"]

    assert payload["model"] == "gpt-5.1"
    assert "max_completion_tokens" in payload
    assert "max_tokens" not in payload
    assert "temperature" not in payload

    assert payload.get("reasoning") == {"effort": "medium"}
    assert payload.get("text", {}).get("verbosity") == "high"


@pytest.mark.asyncio
async def test_gpt5_mini_payload_uses_reasoning_controls(
    mock_session: AsyncMock, retry_manager: AsyncMock, base_settings: MagicMock
) -> None:
    """GPT-5 Mini should also use reasoning/text controls and max_completion_tokens."""
    provider = _prepare_openai_provider(
        mock_session=mock_session,
        retry_manager=retry_manager,
        settings=base_settings,
        default_model="gpt-5-mini-2025-08-07",
    )
    _setup_response(mock_session)

    correlation_id = uuid4()
    await provider.generate_comparison(
        user_prompt="Compare essays mini",
        correlation_id=correlation_id,
        reasoning_effort="low",
        output_verbosity="medium",
    )

    assert mock_session.post.called
    _, kwargs = mock_session.post.call_args
    payload = kwargs["json"]

    assert payload["model"] == "gpt-5-mini-2025-08-07"
    assert "max_completion_tokens" in payload
    assert "max_tokens" not in payload
    assert "temperature" not in payload

    assert payload.get("reasoning") == {"effort": "low"}
    assert payload.get("text", {}).get("verbosity") == "medium"
