"""Unit tests for LLM orchestrator."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from common_core import LLMProviderType
from common_core.error_enums import ErrorCode
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.llm_orchestrator_impl import LLMOrchestratorImpl
from services.llm_provider_service.internal_models import LLMProviderError, LLMProviderResponse


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.DEFAULT_LLM_PROVIDER = "mock"
    settings.CACHE_TTL = 3600
    return settings


@pytest.fixture
def mock_cache_manager() -> AsyncMock:
    """Mock cache manager."""
    cache_manager = AsyncMock()
    cache_manager.generate_cache_key = MagicMock(return_value="test_cache_key")
    cache_manager.get_cached_response = AsyncMock(return_value=None)
    cache_manager.cache_response = AsyncMock()
    return cache_manager


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock event publisher."""
    event_publisher = AsyncMock()
    event_publisher.publish_llm_request_started = AsyncMock()
    event_publisher.publish_llm_request_completed = AsyncMock()
    event_publisher.publish_llm_provider_failure = AsyncMock()
    return event_publisher


@pytest.fixture
def mock_provider() -> AsyncMock:
    """Mock LLM provider."""
    provider = AsyncMock()
    return provider


@pytest.fixture
def orchestrator(
    mock_settings: MagicMock,
    mock_cache_manager: AsyncMock,
    mock_event_publisher: AsyncMock,
    mock_provider: AsyncMock,
) -> LLMOrchestratorImpl:
    """Create orchestrator with mocked dependencies."""
    from typing import Dict

    from services.llm_provider_service.protocols import LLMProviderProtocol

    providers: Dict[LLMProviderType, LLMProviderProtocol] = {
        LLMProviderType.MOCK: mock_provider,
        LLMProviderType.OPENAI: mock_provider,
    }  # type: ignore
    return LLMOrchestratorImpl(
        providers=providers,
        cache_manager=mock_cache_manager,
        event_publisher=mock_event_publisher,
        settings=mock_settings,
    )


@pytest.mark.asyncio
async def test_orchestrator_successful_comparison(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock, mock_event_publisher: AsyncMock
) -> None:
    """Test orchestrator handles successful comparison."""
    # Arrange
    correlation_id = uuid4()
    mock_response = LLMProviderResponse(
        choice="B",
        reasoning="Essay B is better structured",
        confidence=0.85,
        provider=LLMProviderType.MOCK,
        model="mock-model-v1",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )
    mock_provider.generate_comparison.return_value = (mock_response, None)

    # Act
    result, error = await orchestrator.perform_comparison(
        provider=LLMProviderType.MOCK,
        user_prompt="Compare these essays",
        essay_a="Essay A content",
        essay_b="Essay B content",
        correlation_id=correlation_id,
    )

    # Assert
    assert error is None
    assert result is not None
    assert result.choice == "B"
    assert result.reasoning == "Essay B is better structured"
    assert result.confidence == 0.85
    assert result.provider == "mock"
    assert result.model == "mock-model-v1"
    assert result.cached is False
    assert result.correlation_id == correlation_id

    # Verify events were published
    mock_event_publisher.publish_llm_request_started.assert_called_once()
    mock_event_publisher.publish_llm_request_completed.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_provider_not_found(orchestrator: LLMOrchestratorImpl) -> None:
    """Test orchestrator handles missing provider."""
    # Arrange
    correlation_id = uuid4()

    # Act
    result, error = await orchestrator.perform_comparison(
        provider=LLMProviderType.GOOGLE,  # Valid provider type but not configured in test setup
        user_prompt="Compare",
        essay_a="A",
        essay_b="B",
        correlation_id=correlation_id,
    )

    # Assert
    assert result is None
    assert error is not None
    assert error.error_type == ErrorCode.CONFIGURATION_ERROR
    assert "not found" in error.error_message
    assert error.provider == LLMProviderType.GOOGLE
    assert error.is_retryable is False


@pytest.mark.asyncio
async def test_orchestrator_cache_hit(
    orchestrator: LLMOrchestratorImpl,
    mock_cache_manager: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test orchestrator returns cached response."""
    # Arrange
    correlation_id = uuid4()
    cached_data = {
        "choice": "A",
        "reasoning": "Cached reasoning",
        "confidence": 0.9,
        "model": "cached-model",
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "cost_estimate": 0.001,
    }
    mock_cache_manager.get_cached_response.return_value = cached_data

    # Act
    result, error = await orchestrator.perform_comparison(
        provider=LLMProviderType.MOCK,
        user_prompt="Compare",
        essay_a="A",
        essay_b="B",
        correlation_id=correlation_id,
    )

    # Assert
    assert error is None
    assert result is not None
    assert result.choice == "A"
    assert result.reasoning == "Cached reasoning"
    assert result.cached is True
    assert result.provider == "mock"

    # Verify only cache hit event was published
    mock_event_publisher.publish_llm_request_started.assert_called_once()
    mock_event_publisher.publish_llm_request_completed.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrator_provider_error(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock, mock_event_publisher: AsyncMock
) -> None:
    """Test orchestrator handles provider errors."""
    # Arrange
    correlation_id = uuid4()
    provider_error = LLMProviderError(
        error_type=ErrorCode.RATE_LIMIT,
        error_message="Rate limit exceeded",
        provider=LLMProviderType.MOCK,
        correlation_id=correlation_id,
        retry_after=60,
        is_retryable=True,
    )
    mock_provider.generate_comparison.return_value = (None, provider_error)

    # Act
    result, error = await orchestrator.perform_comparison(
        provider=LLMProviderType.MOCK,
        user_prompt="Compare",
        essay_a="A",
        essay_b="B",
        correlation_id=correlation_id,
    )

    # Assert
    assert result is None
    assert error == provider_error

    # Verify failure events were published
    mock_event_publisher.publish_llm_provider_failure.assert_called_once()
    mock_event_publisher.publish_llm_request_completed.assert_called_once_with(
        provider=LLMProviderType.MOCK,
        correlation_id=correlation_id,
        success=False,
        response_time_ms=pytest.approx(0, abs=100),  # Allow some variance in timing
        metadata={
            "request_type": "comparison",
            "error_message": "Rate limit exceeded",
            "failure_type": "rate_limit",
        },
    )


@pytest.mark.asyncio
async def test_orchestrator_test_provider_success(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock
) -> None:
    """Test provider connectivity check success."""
    # Arrange
    mock_response = LLMProviderResponse(
        choice="A",
        reasoning="Test response",
        confidence=0.5,
        provider=LLMProviderType.MOCK,
        model="mock-model",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )
    mock_provider.generate_comparison.return_value = (mock_response, None)

    # Act
    success, message = await orchestrator.test_provider(LLMProviderType.MOCK)

    # Assert
    assert success is True
    assert "operational" in message


@pytest.mark.asyncio
async def test_orchestrator_test_provider_failure(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock
) -> None:
    """Test provider connectivity check failure."""
    # Arrange
    mock_provider.generate_comparison.side_effect = Exception("Connection failed")

    # Act
    success, message = await orchestrator.test_provider(LLMProviderType.MOCK)

    # Assert
    assert success is False
    assert "exception" in message
    assert "Connection failed" in message


@pytest.mark.asyncio
async def test_orchestrator_with_overrides(
    orchestrator: LLMOrchestratorImpl, mock_provider: AsyncMock
) -> None:
    """Test orchestrator passes overrides to provider."""
    # Arrange
    correlation_id = uuid4()
    mock_response = LLMProviderResponse(
        choice="A",
        reasoning="Response",
        confidence=0.7,
        provider=LLMProviderType.MOCK,
        model="overridden-model",
        prompt_tokens=20,
        completion_tokens=10,
        total_tokens=30,
    )
    mock_provider.generate_comparison.return_value = (mock_response, None)

    # Act
    result, error = await orchestrator.perform_comparison(
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
    assert error is None
    assert result is not None
    mock_provider.generate_comparison.assert_called_once_with(
        user_prompt="Compare",
        essay_a="A",
        essay_b="B",
        system_prompt_override="Custom prompt",
        model_override="overridden-model",
        temperature_override=0.5,
        max_tokens_override=None,
    )
