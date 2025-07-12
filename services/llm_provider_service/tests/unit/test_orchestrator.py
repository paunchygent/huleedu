"""Unit tests for LLM orchestrator."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.llm_orchestrator_impl import LLMOrchestratorImpl
from services.llm_provider_service.internal_models import LLMProviderResponse


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.DEFAULT_LLM_PROVIDER = "mock"
    settings.CACHE_TTL = 3600
    settings.QUEUE_REQUEST_TTL_HOURS = 4
    settings.QUEUE_MAX_SIZE = 1000
    settings.QUEUE_MAX_MEMORY_MB = 100
    return settings


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock event publisher."""
    event_publisher = AsyncMock()
    event_publisher.publish_llm_request_started = AsyncMock()
    event_publisher.publish_llm_request_completed = AsyncMock()
    event_publisher.publish_llm_provider_failure = AsyncMock()
    return event_publisher


@pytest.fixture
def mock_queue_manager() -> AsyncMock:
    """Mock queue manager."""
    queue_manager = AsyncMock()
    queue_manager.enqueue = AsyncMock(return_value=True)
    queue_manager.dequeue = AsyncMock(return_value=None)
    queue_manager.get_status = AsyncMock(return_value=None)
    queue_manager.update_status = AsyncMock(return_value=True)
    queue_manager.get_queue_stats = AsyncMock()
    queue_manager.cleanup_expired = AsyncMock(return_value=0)
    return queue_manager


@pytest.fixture
def mock_provider() -> AsyncMock:
    """Mock LLM provider."""
    provider = AsyncMock()
    return provider


@pytest.fixture
def mock_trace_context_manager() -> MagicMock:
    """Mock trace context manager."""
    trace_manager = MagicMock()
    trace_manager.capture_trace_context_for_queue.return_value = {
        "traceparent": "00-trace123-span456-01",
        "_huledu_trace_id": "trace123",
    }
    trace_manager.start_api_request_span.return_value.__enter__.return_value = MagicMock()
    trace_manager.start_provider_call_span.return_value.__enter__.return_value = MagicMock()
    return trace_manager


@pytest.fixture
def orchestrator(
    mock_settings: MagicMock,
    mock_event_publisher: AsyncMock,
    mock_queue_manager: AsyncMock,
    mock_provider: AsyncMock,
    mock_trace_context_manager: MagicMock,
) -> LLMOrchestratorImpl:
    """Create orchestrator with mocked dependencies."""
    from typing import Dict

    from services.llm_provider_service.protocols import LLMProviderProtocol

    providers: Dict[LLMProviderType, LLMProviderProtocol] = {
        LLMProviderType.MOCK: mock_provider,
        LLMProviderType.OPENAI: mock_provider,
    }
    return LLMOrchestratorImpl(
        providers=providers,
        event_publisher=mock_event_publisher,
        queue_manager=mock_queue_manager,
        settings=mock_settings,
        trace_context_manager=mock_trace_context_manager,
    )


@pytest.mark.asyncio
async def test_orchestrator_successful_comparison(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock, mock_event_publisher: AsyncMock
) -> None:
    """Test orchestrator handles successful comparison."""
    # Arrange
    correlation_id = uuid4()
    mock_response = LLMProviderResponse(
        winner=EssayComparisonWinner.ESSAY_B,
        justification="Essay B is better structured",
        confidence=0.85,
        provider=LLMProviderType.MOCK,
        model="mock-model-v1",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )
    mock_provider.generate_comparison.return_value = mock_response

    # Act
    result = await orchestrator.perform_comparison(
        provider=LLMProviderType.MOCK,
        user_prompt="Compare these essays",
        essay_a="Essay A content",
        essay_b="Essay B content",
        correlation_id=correlation_id,
    )

    # Assert
    assert result is not None
    # Result should be an LLMOrchestratorResponse for successful case
    from services.llm_provider_service.internal_models import LLMOrchestratorResponse

    assert isinstance(result, LLMOrchestratorResponse)
    assert result.winner == "Essay B"
    assert result.justification == "Essay B is better structured"
    assert result.confidence == 0.85
    assert result.provider == LLMProviderType.MOCK
    assert result.model == "mock-model-v1"
    assert result.correlation_id == correlation_id

    # Verify events were published
    mock_event_publisher.publish_llm_request_started.assert_called_once()
    mock_event_publisher.publish_llm_request_completed.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_provider_not_found(orchestrator: LLMOrchestratorImpl) -> None:
    """Test orchestrator handles missing provider."""
    # Arrange
    correlation_id = uuid4()

    # Act & Assert
    with pytest.raises(HuleEduError) as exc_info:
        await orchestrator.perform_comparison(
            provider=LLMProviderType.GOOGLE,  # Valid provider type but not configured in test setup
            user_prompt="Compare",
            essay_a="A",
            essay_b="B",
            correlation_id=correlation_id,
        )

    # Verify error details
    assert exc_info.value.error_detail.error_code == ErrorCode.CONFIGURATION_ERROR
    assert "not found" in str(exc_info.value)
    assert "google" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_orchestrator_queues_when_provider_unavailable(
    orchestrator: LLMOrchestratorImpl,
    mock_queue_manager: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test orchestrator queues requests when provider unavailable."""
    # Arrange
    correlation_id = uuid4()

    # Mock provider as unavailable (circuit breaker open)
    mock_provider = orchestrator.providers[LLMProviderType.MOCK]

    # Create a proper circuit breaker mock
    mock_circuit_breaker = MagicMock()
    mock_circuit_breaker.state = "open"

    # Set up the wrapped provider structure to simulate make_resilient wrapper
    # The resilient wrapper sets __wrapped__ attribute and _circuit_breaker on the wrapper itself
    setattr(mock_provider, "__wrapped__", MagicMock())
    setattr(mock_provider, "_circuit_breaker", mock_circuit_breaker)

    # Mock queue stats
    from services.llm_provider_service.queue_models import QueueStats

    mock_queue_stats = QueueStats(
        current_size=10,
        max_size=1000,
        memory_usage_mb=5.0,
        max_memory_mb=100.0,
        usage_percent=1.0,
        estimated_wait_minutes=5,
        is_accepting_requests=True,
    )
    mock_queue_manager.get_queue_stats.return_value = mock_queue_stats

    # Act
    result = await orchestrator.perform_comparison(
        provider=LLMProviderType.MOCK,
        user_prompt="Compare",
        essay_a="A",
        essay_b="B",
        correlation_id=correlation_id,
    )

    # Assert
    assert result is not None
    # Result should be an LLMQueuedResult for queued case
    from services.llm_provider_service.internal_models import LLMQueuedResult

    assert isinstance(result, LLMQueuedResult)
    assert result.provider == LLMProviderType.MOCK
    assert result.status == "queued"
    assert result.correlation_id == correlation_id
    assert result.estimated_wait_minutes == 5

    # Verify queue was called
    mock_queue_manager.enqueue.assert_called_once()

    # Verify events were published
    mock_event_publisher.publish_llm_request_started.assert_called_once()
    mock_event_publisher.publish_llm_request_completed.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_provider_error(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock, mock_event_publisher: AsyncMock
) -> None:
    """Test orchestrator handles provider errors."""
    # Arrange
    correlation_id = uuid4()
    from services.llm_provider_service.exceptions import raise_rate_limit_error

    # Mock provider to raise rate limit error
    def mock_rate_limit_error(*args, **kwargs) -> None:
        raise_rate_limit_error(
            service="llm_provider_service",
            operation="generate_comparison",
            external_service="mock_provider",
            message="Rate limit exceeded",
            correlation_id=correlation_id,
            details={"retry_after": 60, "provider": "mock"},
            limit=1000,
            window_seconds=60
        )

    mock_provider.generate_comparison.side_effect = mock_rate_limit_error

    # Act & Assert
    with pytest.raises(HuleEduError) as exc_info:
        await orchestrator.perform_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="Compare",
            essay_a="A",
            essay_b="B",
            correlation_id=correlation_id,
        )

    # Verify error details
    assert exc_info.value.error_detail.error_code == ErrorCode.RATE_LIMIT
    assert "Rate limit exceeded" in str(exc_info.value)

    # Verify failure events were published
    mock_event_publisher.publish_llm_provider_failure.assert_called_once()
    mock_event_publisher.publish_llm_request_completed.assert_called_once_with(
        provider="mock",  # Event publisher uses string value
        correlation_id=correlation_id,
        success=False,
        response_time_ms=pytest.approx(0, abs=100),  # Allow some variance in timing
        metadata={
            "request_type": "comparison",
            "error_message": "Provider error occurred",
            "failure_type": "unknown",
        },
    )


@pytest.mark.asyncio
async def test_orchestrator_test_provider_success(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock
) -> None:
    """Test provider connectivity check success."""
    # Arrange
    mock_response = LLMProviderResponse(
        winner=EssayComparisonWinner.ESSAY_A,
        justification="Test response",
        confidence=0.5,
        provider=LLMProviderType.MOCK,
        model="mock-model",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )
    mock_provider.generate_comparison.return_value = mock_response

    # Act
    correlation_id = uuid4()
    success = await orchestrator.test_provider(LLMProviderType.MOCK, correlation_id)

    # Assert
    assert success is True


@pytest.mark.asyncio
async def test_orchestrator_test_provider_failure(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock
) -> None:
    """Test provider connectivity check failure."""
    # Arrange
    mock_provider.generate_comparison.side_effect = Exception("Connection failed")

    # Act & Assert
    correlation_id = uuid4()
    with pytest.raises(HuleEduError):
        await orchestrator.test_provider(LLMProviderType.MOCK, correlation_id)


@pytest.mark.asyncio
async def test_orchestrator_with_overrides(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock
) -> None:
    """Test orchestrator passes overrides to provider."""
    # Arrange
    correlation_id = uuid4()
    mock_response = LLMProviderResponse(
        winner=EssayComparisonWinner.ESSAY_A,
        justification="Response",
        confidence=0.7,
        provider=LLMProviderType.MOCK,
        model="overridden-model",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    mock_provider.generate_comparison.return_value = mock_response

    # Act
    result = await orchestrator.perform_comparison(
        provider=LLMProviderType.MOCK,
        user_prompt="Compare",
        essay_a="A",
        essay_b="B",
        correlation_id=correlation_id,
        model_override="overridden-model",
        temperature_override=0.5,
        system_prompt_override="Custom prompt",
    )

    # Assert
    assert result is not None
    mock_provider.generate_comparison.assert_called_once_with(
        user_prompt="Compare",
        essay_a="A",
        essay_b="B",
        correlation_id=correlation_id,
        system_prompt_override="Custom prompt",
        model_override="overridden-model",
        temperature_override=0.5,
        max_tokens_override=None,
    )
