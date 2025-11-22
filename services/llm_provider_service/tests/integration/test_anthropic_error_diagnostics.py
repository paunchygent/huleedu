"""Integration tests for Anthropic API error diagnostics."""

import json
from typing import Any
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

import pytest
from aiohttp import ClientError, ClientResponseError, RequestInfo
from huleedu_service_libs.logging_utils import create_service_logger
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.anthropic_provider_impl import (
    AnthropicProviderImpl,
)
from services.llm_provider_service.metrics import get_llm_metrics
from services.llm_provider_service.protocols import LLMRetryManagerProtocol

logger = create_service_logger("test_anthropic_error_diagnostics")


class MockResponse:
    """Mock aiohttp response."""

    def __init__(self, status: int, text: str = "", headers: dict | None = None) -> None:
        self.status = status
        self._text = text
        self.headers = headers or {}
        # Minimal request info used when constructing ClientResponseError
        self.request_info = RequestInfo(
            url=URL("http://example.com"),
            method="POST",
            headers=CIMultiDictProxy(CIMultiDict()),
        )

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> "MockResponse":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise ClientResponseError(
                request_info=RequestInfo(
                    url=URL("http://example.com"),
                    method="POST",
                    headers=CIMultiDictProxy(CIMultiDict()),
                ),
                history=(),
                status=self.status,
                message=self._text,
            )


@pytest.mark.asyncio
async def test_anthropic_api_error_metrics_and_logging() -> None:
    """Verify that API errors are recorded in metrics and logged with details."""

    # Setup
    settings = Settings(ANTHROPIC_API_KEY="test-key")
    mock_session = Mock()  # session.post is not async, it returns an async context manager
    mock_retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

    # Configure retry manager to execute the operation directly (no retry logic for this test).
    #
    # The real with_retry implementation accepts an "operation" callable plus
    # an "operation_name" and forwards only the operation-specific arguments
    # to the callable. This shim mirrors that behaviour enough for this test
    # and ensures our Anthropic HTTP path (and metrics) are actually exercised.
    async def execute_operation(*args: Any, **kwargs: Any) -> Any:
        # Support both positional and keyword invocation styles.
        operation = kwargs.pop("operation", None)
        if operation is None and args:
            operation = args[0]
            args = args[1:]

        # Drop helper-only kwargs that the underlying operation does not accept.
        kwargs.pop("operation_name", None)

        assert operation is not None  # safety in case of signature drift
        return await operation(*args, **kwargs)

    mock_retry_manager.with_retry.side_effect = execute_operation

    # Reset metrics singleton to ensure fresh initialization with new metrics
    from services.llm_provider_service import metrics as metrics_module

    metrics_module._metrics = None

    provider = AnthropicProviderImpl(
        session=mock_session,
        settings=settings,
        retry_manager=mock_retry_manager,
    )

    # Ensure metrics are initialized and patch the same counter instances
    get_llm_metrics()
    error_counter = provider.metrics["llm_provider_api_errors_total"]
    error_counter.labels = Mock(return_value=Mock(inc=Mock()))
    provider_error_counter = provider.metrics["llm_provider_errors_total"]
    provider_error_counter.labels = Mock(return_value=Mock(inc=Mock()))

    # Test Case 1: 429 Rate Limit
    mock_session.post.return_value = MockResponse(
        status=429,
        text="Rate limit exceeded",
        headers={
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "1234567890",
            "retry-after": "60",
        },
    )

    with pytest.raises(HuleEduError) as exc_info:
        await provider.generate_comparison(
            user_prompt="test prompt",
            correlation_id=uuid4(),
        )

    assert exc_info.value.error_detail.error_code.name == "EXTERNAL_SERVICE_ERROR"

    # Verify metric recording
    error_counter.labels.assert_any_call(
        provider="anthropic", error_type="rate_limit", http_status_code="429"
    )
    provider_error_counter.labels.assert_any_call(
        provider="anthropic", model=ANY, error_type="rate_limit"
    )

    # Verify enriched error details
    details_429 = exc_info.value.error_detail.details
    assert details_429.get("provider") == "anthropic"
    assert details_429.get("http_status") == 429
    assert details_429.get("error_type") == "rate_limit"
    assert details_429.get("retryable") is True
    assert details_429.get("provider_error_code") == "unknown"

    # Test Case 2: 500 Server Error
    mock_session.post.return_value = MockResponse(status=500, text="Internal Server Error")

    with pytest.raises(HuleEduError) as exc_info:
        await provider.generate_comparison(
            user_prompt="test prompt",
            correlation_id=uuid4(),
        )

    assert exc_info.value.error_detail.error_code.name == "EXTERNAL_SERVICE_ERROR"

    # Verify metric recording
    error_counter.labels.assert_any_call(
        provider="anthropic", error_type="server_error", http_status_code="500"
    )
    provider_error_counter.labels.assert_any_call(
        provider="anthropic", model=ANY, error_type="server_error"
    )

    # Verify enriched error details
    details_500 = exc_info.value.error_detail.details
    assert details_500.get("provider") == "anthropic"
    assert details_500.get("http_status") == 500
    assert details_500.get("error_type") == "server_error"
    assert details_500.get("retryable") is True
    assert details_500.get("provider_error_code") == "unknown"

    # Test Case 3: Connection Error
    mock_session.post.side_effect = ClientError("Connection failed")

    with pytest.raises(HuleEduError) as exc_info:
        await provider.generate_comparison(
            user_prompt="test prompt",
            correlation_id=uuid4(),
        )

    assert exc_info.value.error_detail.error_code.name == "EXTERNAL_SERVICE_ERROR"

    # Verify metric recording
    error_counter.labels.assert_any_call(
        provider="anthropic", error_type="connection_error", http_status_code="0"
    )
    provider_error_counter.labels.assert_any_call(
        provider="anthropic", model=ANY, error_type="connection_error"
    )

    # Verify enriched error details
    details_conn = exc_info.value.error_detail.details
    assert details_conn.get("provider") == "anthropic"
    assert details_conn.get("http_status") == 0
    assert details_conn.get("error_type") == "connection_error"
    assert details_conn.get("retryable") is True
    assert details_conn.get("provider_error_code") == "unknown"


@pytest.mark.asyncio
async def test_anthropic_overloaded_error_is_retryable_and_recorded() -> None:
    """Ensure 529/overloaded responses are treated as retryable with structured diagnostics."""

    settings = Settings(ANTHROPIC_API_KEY="test-key")
    mock_session = Mock()
    mock_retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

    async def execute_operation(*args: Any, **kwargs: Any) -> Any:
        operation = kwargs.pop("operation", None)
        if operation is None and args:
            operation = args[0]
            args = args[1:]
        kwargs.pop("operation_name", None)
        assert operation is not None
        return await operation(*args, **kwargs)

    mock_retry_manager.with_retry.side_effect = execute_operation

    from services.llm_provider_service import metrics as metrics_module

    metrics_module._metrics = None

    provider = AnthropicProviderImpl(
        session=mock_session,
        settings=settings,
        retry_manager=mock_retry_manager,
    )

    get_llm_metrics()
    error_counter = provider.metrics["llm_provider_api_errors_total"]
    error_counter.labels = Mock(return_value=Mock(inc=Mock()))
    provider_error_counter = provider.metrics["llm_provider_errors_total"]
    provider_error_counter.labels = Mock(return_value=Mock(inc=Mock()))

    overloaded_body = json.dumps(
        {
            "error": {
                "type": "overloaded_error",
                "code": "overloaded_error",
                "message": "Provider overloaded",
            }
        }
    )
    mock_session.post.return_value = MockResponse(status=529, text=overloaded_body)

    with pytest.raises(HuleEduError) as exc_info:
        await provider.generate_comparison(
            user_prompt="test prompt",
            correlation_id=uuid4(),
        )

    assert exc_info.value.error_detail.error_code.name == "EXTERNAL_SERVICE_ERROR"
    details = exc_info.value.error_detail.details
    assert details.get("http_status") == 529
    assert details.get("error_type") == "overloaded"
    assert details.get("retryable") is True
    assert details.get("provider_error_code") == "overloaded_error"
    assert details.get("provider_error_type") == "overloaded_error"

    error_counter.labels.assert_any_call(
        provider="anthropic", error_type="overloaded", http_status_code="529"
    )
    provider_error_counter.labels.assert_any_call(
        provider="anthropic", model=ANY, error_type="overloaded"
    )


@pytest.mark.asyncio
async def test_anthropic_stop_reason_max_tokens_surfaces_structured_error() -> None:
    """stop_reason=max_tokens should raise a structured EXTERNAL_SERVICE_ERROR with context."""

    settings = Settings(ANTHROPIC_API_KEY="test-key")
    mock_session = Mock()
    mock_retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

    async def execute_operation(*args: Any, **kwargs: Any) -> Any:
        operation = kwargs.pop("operation", None)
        if operation is None and args:
            operation = args[0]
            args = args[1:]
        kwargs.pop("operation_name", None)
        assert operation is not None
        return await operation(*args, **kwargs)

    mock_retry_manager.with_retry.side_effect = execute_operation

    from services.llm_provider_service import metrics as metrics_module

    metrics_module._metrics = None

    provider = AnthropicProviderImpl(
        session=mock_session,
        settings=settings,
        retry_manager=mock_retry_manager,
    )

    response_payload = {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [],
        "stop_reason": "max_tokens",
        "usage": {"input_tokens": 1024, "output_tokens": 1024},
    }

    mock_session.post.return_value = MockResponse(
        status=200,
        text=json.dumps(response_payload),
    )

    with pytest.raises(HuleEduError) as exc_info:
        await provider.generate_comparison(
            user_prompt="long prompt",
            correlation_id=uuid4(),
        )

    assert exc_info.value.error_detail.error_code.name == "EXTERNAL_SERVICE_ERROR"
    details = exc_info.value.error_detail.details
    payload = details.get("details", details)
    assert payload.get("provider") == "anthropic"
    assert payload.get("stop_reason") == "max_tokens"
    assert payload.get("max_tokens") == settings.LLM_DEFAULT_MAX_TOKENS


@pytest.mark.asyncio
async def test_prompt_cache_metrics_record_hits_and_misses() -> None:
    """Prompt cache metrics should track hit/miss outcomes and tokens saved/written."""

    settings = Settings(ANTHROPIC_API_KEY="test-key", ENABLE_PROMPT_CACHING=True)
    mock_session = Mock()
    mock_retry_manager = AsyncMock(spec=LLMRetryManagerProtocol)

    async def execute_operation(*args: Any, **kwargs: Any) -> Any:
        operation = kwargs.pop("operation", None)
        if operation is None and args:
            operation = args[0]
            args = args[1:]
        kwargs.pop("operation_name", None)
        assert operation is not None
        return await operation(*args, **kwargs)

    mock_retry_manager.with_retry.side_effect = execute_operation

    from services.llm_provider_service import metrics as metrics_module

    metrics_module._metrics = None

    provider = AnthropicProviderImpl(
        session=mock_session,
        settings=settings,
        retry_manager=mock_retry_manager,
    )

    get_llm_metrics()
    cache_events = provider.metrics["llm_provider_prompt_cache_events_total"]
    cache_tokens = provider.metrics["llm_provider_prompt_cache_tokens_total"]

    tool_input = {"winner": "Essay A", "justification": "A", "confidence": 3}

    # Cache hit scenario
    cache_events.labels = Mock(return_value=Mock(inc=Mock()))
    cache_tokens.labels = Mock(return_value=Mock(inc=Mock()))
    response_payload_hit = {
        "content": [
            {"type": "tool_use", "name": "comparison_result", "input": tool_input},
        ],
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": 120,
            "output_tokens": 8,
            "cache_read_input_tokens": 80,
            "cache_creation_input_tokens": 0,
        },
    }
    mock_session.post.return_value = MockResponse(
        status=200,
        text=json.dumps(response_payload_hit),
    )

    await provider.generate_comparison(
        user_prompt="cached prompt",
        correlation_id=uuid4(),
    )

    cache_events.labels.assert_called_with(
        provider="anthropic",
        model=settings.ANTHROPIC_DEFAULT_MODEL,
        result="hit",
    )
    cache_events.labels.return_value.inc.assert_called_once_with()
    cache_tokens.labels.assert_called_with(
        provider="anthropic", model=settings.ANTHROPIC_DEFAULT_MODEL, direction="read"
    )
    cache_tokens.labels.return_value.inc.assert_called_once_with(80)

    # Cache miss / creation scenario
    cache_events.labels = Mock(return_value=Mock(inc=Mock()))
    cache_tokens.labels = Mock(return_value=Mock(inc=Mock()))
    response_payload_miss = {
        "content": [
            {"type": "tool_use", "name": "comparison_result", "input": tool_input},
        ],
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": 90,
            "output_tokens": 6,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 60,
        },
    }
    mock_session.post.return_value = MockResponse(
        status=200,
        text=json.dumps(response_payload_miss),
    )

    await provider.generate_comparison(
        user_prompt="cache miss prompt",
        correlation_id=uuid4(),
    )

    cache_events.labels.assert_called_with(
        provider="anthropic",
        model=settings.ANTHROPIC_DEFAULT_MODEL,
        result="miss",
    )
    cache_events.labels.return_value.inc.assert_called_once_with()
    cache_tokens.labels.assert_called_with(
        provider="anthropic", model=settings.ANTHROPIC_DEFAULT_MODEL, direction="write"
    )
    cache_tokens.labels.return_value.inc.assert_called_once_with(60)
