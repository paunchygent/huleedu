"""Integration tests for Anthropic API error diagnostics."""

from typing import Any
from unittest.mock import AsyncMock, Mock
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

    # Ensure metrics are initialized and patch the same counter instance
    get_llm_metrics()
    error_counter = provider.metrics["llm_provider_api_errors_total"]
    error_counter.labels = Mock(return_value=Mock(inc=Mock()))

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
