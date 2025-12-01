"""Tests for orchestrator wiring of reasoning/output verbosity overrides."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.llm_orchestrator_impl import LLMOrchestratorImpl
from services.llm_provider_service.internal_models import (
    LLMOrchestratorResponse,
    LLMProviderResponse,
)
from services.llm_provider_service.protocols import (
    LLMEventPublisherProtocol,
    LLMProviderProtocol,
    QueueManagerProtocol,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock(spec=Settings)
    settings.QUEUE_REQUEST_TTL_HOURS = 4
    settings.QUEUE_MAX_SIZE = 1000
    settings.QUEUE_MAX_MEMORY_MB = 100
    return settings


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    publisher = AsyncMock(spec=LLMEventPublisherProtocol)
    publisher.publish_llm_request_started = AsyncMock()
    publisher.publish_llm_request_completed = AsyncMock()
    publisher.publish_llm_provider_failure = AsyncMock()
    return publisher


@pytest.fixture
def mock_queue_manager() -> AsyncMock:
    manager = AsyncMock(spec=QueueManagerProtocol)
    manager.enqueue = AsyncMock(return_value=True)
    manager.get_queue_stats = AsyncMock()
    manager.dequeue = AsyncMock()
    manager.get_status = AsyncMock()
    manager.update_status = AsyncMock()
    manager.remove = AsyncMock()
    return manager


@pytest.fixture
def mock_trace_context_manager() -> MagicMock:
    trace = MagicMock()
    trace.capture_trace_context_for_queue.return_value = {}
    trace.start_provider_call_span.return_value.__enter__.return_value = MagicMock()
    trace.get_current_trace_id.return_value = "trace-id"
    return trace


@pytest.fixture
def mock_provider() -> AsyncMock:
    provider = AsyncMock(spec=LLMProviderProtocol)
    provider.generate_comparison.return_value = LLMProviderResponse(
        winner=EssayComparisonWinner.ESSAY_A,
        justification="A",
        confidence=0.5,
        provider=LLMProviderType.OPENAI,
        model="gpt-5.1",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )
    return provider


@pytest.fixture
def orchestrator(
    mock_settings: MagicMock,
    mock_event_publisher: AsyncMock,
    mock_queue_manager: AsyncMock,
    mock_provider: AsyncMock,
    mock_trace_context_manager: MagicMock,
) -> LLMOrchestratorImpl:
    providers: Dict[LLMProviderType, LLMProviderProtocol] = {
        LLMProviderType.OPENAI: mock_provider,
    }
    return LLMOrchestratorImpl(
        providers=providers,
        event_publisher=mock_event_publisher,
        queue_manager=mock_queue_manager,
        trace_context_manager=mock_trace_context_manager,
        settings=mock_settings,
    )


@pytest.mark.asyncio
async def test_process_queued_request_wires_reasoning_overrides(
    orchestrator: LLMOrchestratorImpl,
    mock_provider: AsyncMock,
) -> None:
    """reasoning_effort and output_verbosity should flow unchanged into provider call."""
    correlation_id = uuid4()
    overrides: Dict[str, Any] = {
        "model_override": "gpt-5.1",
        "reasoning_effort": "medium",
        "output_verbosity": "high",
    }

    result = await orchestrator.process_queued_request(
        provider=LLMProviderType.OPENAI,
        user_prompt="Compare essays",
        correlation_id=correlation_id,
        prompt_blocks=None,
        **overrides,
    )

    assert isinstance(result, LLMOrchestratorResponse)
    mock_provider.generate_comparison.assert_awaited_once()
    _, kwargs = mock_provider.generate_comparison.call_args
    assert kwargs.get("reasoning_effort") == "medium"
    assert kwargs.get("output_verbosity") == "high"
