"""Unit coverage for Anthropic prompt block handling and cache_control payloads."""

import json
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.llm_provider_service.protocols import LLMRetryManagerProtocol


async def _execute_operation(*args: Any, **kwargs: Any) -> Any:
    """Replay the retry manager operation immediately (mimics with_retry shim)."""
    operation = kwargs.pop("operation", None)
    if operation is None and args:
        operation = args[0]
        args = args[1:]

    kwargs.pop("operation_name", None)
    assert operation is not None
    return await operation(*args, **kwargs)


@pytest.mark.asyncio
async def test_anthropic_prefers_prompt_blocks_and_sets_cache_control() -> None:
    """Prompt blocks are preferred, cache_control added, and cache metrics surfaced."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    mock_session = Mock()
    mock_retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)
    mock_retry_manager.with_retry.side_effect = _execute_operation

    # Reset metrics singleton for deterministic counters
    from services.llm_provider_service import metrics as metrics_module

    metrics_module._metrics = None

    provider = AnthropicProviderImpl(
        session=mock_session,
        settings=settings,
        retry_manager=mock_retry_manager,
    )

    prompt_blocks = [
        {"target": "user_content", "content": "static context", "cacheable": True, "ttl": "1h"},
        {"target": "user_content", "content": "essay A", "cacheable": False},
        {"target": "user_content", "content": "essay B", "cacheable": False},
        {
            "target": "user_content",
            "content": "response instructions",
            "cacheable": True,
            "ttl": "5m",
        },
    ]

    fake_response = {
        "content": [
            {
                "type": "tool_use",
                "name": "comparison_result",
                "input": {"winner": "Essay A", "justification": "A", "confidence": 3},
            }
        ],
        "usage": {
            "input_tokens": 120,
            "output_tokens": 18,
            "cache_creation_input_tokens": 90,
            "cache_read_input_tokens": 0,
        },
    }

    captured_payload: dict[str, Any] = {}

    async def fake_http_request(**kwargs: Any) -> str:
        captured_payload["payload"] = kwargs["payload"]
        return json.dumps(fake_response)

    provider._perform_http_request_with_metrics = fake_http_request  # type: ignore[method-assign]

    response = await provider.generate_comparison(
        user_prompt="legacy prompt should be ignored",
        prompt_blocks=prompt_blocks,
        correlation_id=uuid4(),
    )

    payload = captured_payload["payload"]
    assert isinstance(payload["system"], list)
    assert payload["system"][0]["cache_control"]["ttl"] == "1h"
    assert payload["messages"][0]["content"][0]["cache_control"]["ttl"] == "1h"
    assert "cache_control" not in payload["messages"][0]["content"][1]  # non-cacheable essay A
    assert payload["messages"][0]["content"][-1]["cache_control"]["ttl"] == "5m"
    assert payload["tools"][0]["cache_control"]["ttl"] == "1h"

    assert response.metadata.get("cache_creation_input_tokens") == 90
    assert response.metadata.get("cache_read_input_tokens") == 0
    usage = response.metadata.get("usage") or {}
    assert usage.get("input_tokens") == 120


@pytest.mark.asyncio
async def test_anthropic_rejects_ttl_ordering_violation() -> None:
    """A 1h block after 5m should raise a validation error."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    mock_session = Mock()
    mock_retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)
    mock_retry_manager.with_retry.side_effect = _execute_operation

    provider = AnthropicProviderImpl(
        session=mock_session,
        settings=settings,
        retry_manager=mock_retry_manager,
    )

    prompt_blocks = [
        {"target": "user_content", "content": "5m block", "cacheable": True, "ttl": "5m"},
        {"target": "user_content", "content": "1h block", "cacheable": True, "ttl": "1h"},
    ]

    provider._perform_http_request_with_metrics = AsyncMock(return_value=json.dumps({}))  # type: ignore[method-assign]

    with pytest.raises(HuleEduError) as exc_info:
        await provider.generate_comparison(
            user_prompt="legacy prompt",
            prompt_blocks=prompt_blocks,
            correlation_id=uuid4(),
        )

    assert "1h TTL block must precede 5m TTL blocks" in str(exc_info.value)
