"""Shared fixtures for LLM payload construction integration tests."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Awaitable, Callable
from unittest.mock import AsyncMock

import aiohttp
import pytest
from aioresponses import aioresponses
from common_core import LLMProviderType

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.llm_interaction_impl import (
    LLMInteractionImpl,
)
from services.cj_assessment_service.implementations.llm_provider_service_client import (
    LLMProviderServiceClient,
)
from services.cj_assessment_service.protocols import (
    LLMInteractionProtocol,
    LLMProviderProtocol,
    RetryManagerProtocol,
)

CapturedRequestExtractor = Callable[[aioresponses], list[dict[str, Any]]]


@pytest.fixture
def capture_requests_from_mocker(test_settings: Settings) -> CapturedRequestExtractor:
    """Extract JSON request bodies captured by aioresponses."""

    def _extract_requests(mocker: aioresponses) -> list[dict[str, Any]]:
        from yarl import URL

        captured: list[dict[str, Any]] = []
        llm_provider_url = test_settings.LLM_PROVIDER_SERVICE_URL
        request_key = ("POST", URL(f"{llm_provider_url}/comparison"))

        if request_key in mocker.requests:
            for request_call in mocker.requests[request_key]:
                if "json" in request_call.kwargs:
                    captured.append(request_call.kwargs["json"])

        return captured

    return _extract_requests


@pytest.fixture
async def mock_llm_http_session(
    test_settings: Settings,
) -> AsyncGenerator[tuple[aiohttp.ClientSession, aioresponses], None]:
    """Provide an aiohttp session with /comparison POST mocked via aioresponses."""

    session = aiohttp.ClientSession()

    with aioresponses() as mocker:
        llm_provider_url = test_settings.LLM_PROVIDER_SERVICE_URL
        mocker.post(
            f"{llm_provider_url}/comparison",
            payload={
                "status": "queued",
                "queue_id": "test-queue-id",
                "message": "Comparison queued for async processing",
            },
            status=202,
            repeat=True,
        )

        yield session, mocker

    await session.close()


@pytest.fixture
async def real_llm_interaction(
    mock_llm_http_session: tuple[aiohttp.ClientSession, aioresponses],
    test_settings: Settings,
) -> tuple[LLMInteractionProtocol, aioresponses]:
    """Create a real LLMInteractionImpl backed by LLMProviderServiceClient with mocked HTTP."""

    session, mocker = mock_llm_http_session

    mock_retry_manager = AsyncMock(spec=RetryManagerProtocol)

    async def no_retry(
        operation: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await operation(*args, **kwargs)

    mock_retry_manager.with_retry = AsyncMock(side_effect=no_retry)

    llm_client = LLMProviderServiceClient(
        session=session,
        settings=test_settings,
        retry_manager=mock_retry_manager,
    )

    providers: dict[LLMProviderType, LLMProviderProtocol] = {
        LLMProviderType.OPENAI: llm_client,  # type: ignore[assignment]
        LLMProviderType.ANTHROPIC: llm_client,  # type: ignore[assignment]
    }

    llm_interaction = LLMInteractionImpl(
        providers=providers,
        settings=test_settings,
    )

    return llm_interaction, mocker
