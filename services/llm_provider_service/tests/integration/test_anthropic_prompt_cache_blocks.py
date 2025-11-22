"""Integration coverage for Anthropic prompt block caching and callback metadata."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core import EssayComparisonWinner, LLMComparisonRequest, LLMProviderType

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.implementations.trace_context_manager_impl import (
    TraceContextManagerImpl,
)
from services.llm_provider_service.internal_models import LLMOrchestratorResponse
from services.llm_provider_service.protocols import LLMRetryManagerProtocol, QueueManagerProtocol
from services.llm_provider_service.queue_models import QueuedRequest
from services.llm_provider_service.tests.fixtures.fake_event_publisher import FakeEventPublisher


async def _execute_operation(*args: Any, **kwargs: Any) -> Any:
    """Replay the retry manager operation immediately (mirrors with_retry shim)."""
    operation = kwargs.pop("operation", None)
    if operation is None and args:
        operation = args[0]
        args = args[1:]

    kwargs.pop("operation_name", None)
    assert operation is not None
    return await operation(*args, **kwargs)


def _fake_tool_response(
    *, cache_read_tokens: int = 0, cache_write_tokens: int = 0
) -> dict[str, Any]:
    """Minimal Anthropic response payload with tool_use and usage."""

    return {
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
            "cache_read_input_tokens": cache_read_tokens,
            "cache_creation_input_tokens": cache_write_tokens,
        },
    }


def _capture_http_response(captured: Dict[str, Any], response_payload: dict[str, Any]) -> Any:
    """Build a fake HTTP request function that records the payload."""

    async def _fake_http_request(**kwargs: Any) -> str:
        captured["payload"] = kwargs["payload"]
        return json.dumps(response_payload)

    return _fake_http_request


def _build_provider(settings: Settings) -> tuple[AnthropicProviderImpl, dict[str, Any]]:
    """Create an Anthropic provider with a captured payload buffer."""

    mock_session = Mock()
    mock_retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)
    mock_retry_manager.with_retry.side_effect = _execute_operation

    from services.llm_provider_service import metrics as metrics_module

    metrics_module._metrics = None

    provider = AnthropicProviderImpl(
        session=mock_session,
        settings=settings,
        retry_manager=mock_retry_manager,
    )
    captured_payload: dict[str, Any] = {}
    return provider, captured_payload


@pytest.mark.asyncio
async def test_prompt_blocks_preferred_over_user_prompt() -> None:
    """Prompt blocks should drive the payload when provided."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    provider, captured = _build_provider(settings)

    response_payload = _fake_tool_response(cache_write_tokens=64)
    provider._perform_http_request_with_metrics = _capture_http_response(  # type: ignore[assignment]
        captured, response_payload
    )

    prompt_blocks = [
        {"target": "user_content", "content": "static context", "cacheable": True, "ttl": "1h"},
        {"target": "user_content", "content": "essay A block", "cacheable": False},
        {"target": "user_content", "content": "essay B block", "cacheable": False},
    ]
    await provider.generate_comparison(
        user_prompt="legacy prompt should be ignored",
        prompt_blocks=prompt_blocks,
        correlation_id=uuid4(),
    )

    payload = captured["payload"]
    assert payload["messages"][0]["content"][0]["text"] == "static context"
    assert payload["messages"][0]["content"][1]["text"] == "essay A block"
    assert payload["messages"][0]["content"][2]["text"] == "essay B block"
    assert payload["tools"][0]["cache_control"]["ttl"] == "1h"


@pytest.mark.asyncio
async def test_legacy_prompt_fallback_uses_five_minute_ttl_by_default() -> None:
    """Legacy prompts without blocks should default to 5m cache TTL."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    provider, captured = _build_provider(settings)

    provider._perform_http_request_with_metrics = _capture_http_response(  # type: ignore[assignment]
        captured, _fake_tool_response()
    )

    user_prompt = "legacy comparison prompt content"
    await provider.generate_comparison(
        user_prompt=user_prompt,
        prompt_blocks=None,
        correlation_id=uuid4(),
    )

    payload = captured["payload"]
    assert payload["system"][0]["cache_control"]["ttl"] == "5m"
    assert payload["tools"][0]["cache_control"]["ttl"] == "5m"
    assert payload["messages"][0]["content"][0]["text"] == user_prompt


@pytest.mark.asyncio
async def test_extended_ttl_flag_enables_one_hour_service_constants() -> None:
    """Config flag should allow 1h TTL when prompt blocks are absent."""

    settings = Settings(
        ANTHROPIC_API_KEY="test-key",
        ENABLE_PROMPT_CACHING=True,
        USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS=True,
    )
    provider, captured = _build_provider(settings)

    provider._perform_http_request_with_metrics = _capture_http_response(  # type: ignore[assignment]
        captured, _fake_tool_response(cache_write_tokens=90)
    )

    await provider.generate_comparison(
        user_prompt="legacy prompt",
        prompt_blocks=None,
        correlation_id=uuid4(),
    )

    payload = captured["payload"]
    assert payload["system"][0]["cache_control"]["ttl"] == "1h"
    assert payload["tools"][0]["cache_control"]["ttl"] == "1h"


@pytest.mark.asyncio
async def test_system_blocks_and_tools_include_cache_control() -> None:
    """System content array and tools should carry cache_control metadata."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    provider, captured = _build_provider(settings)

    provider._perform_http_request_with_metrics = _capture_http_response(  # type: ignore[assignment]
        captured, _fake_tool_response(cache_write_tokens=45)
    )

    prompt_blocks = [
        {"target": "system", "content": "system guidance", "cacheable": True, "ttl": "1h"},
        {
            "target": "user_content",
            "content": "static instructions",
            "cacheable": True,
            "ttl": "1h",
        },
        {"target": "user_content", "content": "essay payload", "cacheable": False},
        {"target": "user_content", "content": "response format", "cacheable": True, "ttl": "5m"},
    ]

    await provider.generate_comparison(
        user_prompt="should be overridden",
        prompt_blocks=prompt_blocks,
        correlation_id=uuid4(),
    )

    payload = captured["payload"]
    system_blocks = payload["system"]
    assert system_blocks[0]["cache_control"]["ttl"] == "1h"
    assert system_blocks[1]["cache_control"]["ttl"] == "1h"
    user_blocks = payload["messages"][0]["content"]
    assert user_blocks[0]["cache_control"]["ttl"] == "1h"
    assert "cache_control" not in user_blocks[1]
    assert user_blocks[-1]["cache_control"]["ttl"] == "5m"
    assert payload["tools"][0]["cache_control"]["ttl"] == "1h"


@pytest.mark.asyncio
async def test_ttl_ordering_passes_when_one_hour_blocks_precede_five_minutes() -> None:
    """A 1h block before 5m should be accepted."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    provider, captured = _build_provider(settings)

    provider._perform_http_request_with_metrics = _capture_http_response(  # type: ignore[assignment]
        captured, _fake_tool_response(cache_write_tokens=50)
    )

    prompt_blocks = [
        {
            "target": "user_content",
            "content": "cacheable long-lived",
            "cacheable": True,
            "ttl": "1h",
        },
        {
            "target": "user_content",
            "content": "short lived details",
            "cacheable": True,
            "ttl": "5m",
        },
    ]

    await provider.generate_comparison(
        user_prompt="legacy prompt",
        prompt_blocks=prompt_blocks,
        correlation_id=uuid4(),
    )

    payload = captured["payload"]
    user_blocks = payload["messages"][0]["content"]
    assert user_blocks[0]["cache_control"]["ttl"] == "1h"
    assert user_blocks[1]["cache_control"]["ttl"] == "5m"


@pytest.mark.asyncio
async def test_ttl_ordering_violation_raises_validation_error() -> None:
    """A 1h block after a 5m block should raise a validation error."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    provider, _ = _build_provider(settings)

    ttl_metric = provider.metrics["llm_provider_prompt_ttl_violations_total"]
    ttl_metric.labels = Mock(return_value=Mock(inc=Mock()))

    provider._perform_http_request_with_metrics = AsyncMock(  # type: ignore[assignment]
        return_value=json.dumps(_fake_tool_response())
    )

    prompt_blocks = [
        {
            "target": "user_content",
            "content": "short lived details",
            "cacheable": True,
            "ttl": "5m",
        },
        {"target": "user_content", "content": "long lived", "cacheable": True, "ttl": "1h"},
    ]

    with pytest.raises(HuleEduError) as exc_info:
        await provider.generate_comparison(
            user_prompt="legacy prompt",
            prompt_blocks=prompt_blocks,
            correlation_id=uuid4(),
        )

    assert "1h TTL block must precede 5m TTL blocks" in str(exc_info.value)
    ttl_metric.labels.assert_called_once_with(
        provider="anthropic", model=settings.ANTHROPIC_DEFAULT_MODEL, stage="incoming_blocks"
    )


@pytest.mark.asyncio
async def test_callback_metadata_includes_prompt_cache_usage() -> None:
    """Provider metadata should be echoed into callback request_metadata."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    comparison_processor = AsyncMock()
    queue_manager = AsyncMock(spec=QueueManagerProtocol)
    event_publisher = FakeEventPublisher()
    trace_manager = AsyncMock(spec=TraceContextManagerImpl)

    queue_processor = QueueProcessorImpl(
        comparison_processor=comparison_processor,
        queue_manager=queue_manager,
        event_publisher=event_publisher,
        trace_context_manager=trace_manager,
        settings=settings,
    )

    request = QueuedRequest(
        request_data=LLMComparisonRequest(
            user_prompt="prompt",
            prompt_blocks=None,
            callback_topic="test.callback",
            correlation_id=uuid4(),
            metadata={"essay_a_id": "a1", "essay_b_id": "b1"},
        ),
        priority=0,
        ttl=timedelta(hours=settings.QUEUE_REQUEST_TTL_HOURS),
        callback_topic="test.callback",
        size_bytes=0,
    )

    cache_usage = {
        "input_tokens": 120,
        "output_tokens": 18,
        "cache_read_input_tokens": 80,
        "cache_creation_input_tokens": 0,
    }
    result = LLMOrchestratorResponse(
        winner=EssayComparisonWinner.ESSAY_A,
        justification="A",
        confidence=0.5,
        provider=LLMProviderType.ANTHROPIC,
        model="claude-test",
        response_time_ms=25,
        token_usage={
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "total_tokens": 120,
        },
        cost_estimate=0.01,
        correlation_id=uuid4(),
        trace_id=None,
        metadata={
            "prompt_sha256": "hash123",
            "usage": cache_usage,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 0,
        },
    )

    await queue_processor._publish_callback_event(request, result)

    published = event_publisher.get_last_event_of_type("topic_publish")
    assert published is not None
    envelope = published["envelope"]
    callback_metadata = envelope.data.request_metadata
    assert callback_metadata["essay_a_id"] == "a1"
    assert callback_metadata["prompt_sha256"] == "hash123"
    assert callback_metadata["cache_read_input_tokens"] == 80
    assert callback_metadata["cache_creation_input_tokens"] == 0
    assert callback_metadata["usage"] == cache_usage


@pytest.mark.asyncio
async def test_prompt_cache_metrics_record_bypass_when_no_tokens() -> None:
    """Cache metrics should mark bypass when no read/write tokens are present."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    provider, _ = _build_provider(settings)

    cache_events = provider.metrics["llm_provider_prompt_cache_events_total"]
    cache_tokens = provider.metrics["llm_provider_prompt_cache_tokens_total"]
    cache_events.labels = Mock(return_value=Mock(inc=Mock()))
    cache_tokens.labels = Mock(return_value=Mock(inc=Mock()))

    provider._perform_http_request_with_metrics = AsyncMock(  # type: ignore[assignment]
        return_value=json.dumps(_fake_tool_response(cache_read_tokens=0, cache_write_tokens=0))
    )

    await provider.generate_comparison(
        user_prompt="short prompt",
        prompt_blocks=None,
        correlation_id=uuid4(),
    )

    cache_events.labels.assert_called_with(
        provider="anthropic",
        model=settings.ANTHROPIC_DEFAULT_MODEL,
        result="bypass",
    )
