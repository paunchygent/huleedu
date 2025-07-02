"""Unit tests for LLM event publisher."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.event_publisher_impl import LLMEventPublisherImpl


@pytest.fixture
def mock_kafka_bus() -> AsyncMock:
    """Mock Kafka bus for testing."""
    kafka_bus = AsyncMock()
    kafka_bus.publish = AsyncMock()
    return kafka_bus


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.SERVICE_NAME = "llm-provider-service"
    settings.PUBLISH_LLM_USAGE_EVENTS = True
    return settings


@pytest.fixture
def event_publisher(mock_kafka_bus: AsyncMock, mock_settings: MagicMock) -> LLMEventPublisherImpl:
    """Create event publisher with mocked dependencies."""
    return LLMEventPublisherImpl(kafka_bus=mock_kafka_bus, settings=mock_settings)


@pytest.mark.asyncio
async def test_publish_llm_request_started(
    event_publisher: LLMEventPublisherImpl, mock_kafka_bus: AsyncMock
) -> None:
    """Test publishing LLM request started event."""
    # Arrange
    provider = "openai"
    correlation_id = uuid4()
    metadata = {"model": "gpt-4", "temperature": 0.7}

    # Act
    with patch(
        "services.llm_provider_service.implementations.event_publisher_impl.datetime"
    ) as mock_datetime:
        mock_datetime.utcnow.return_value = datetime(2024, 1, 1, 12, 0, 0)
        await event_publisher.publish_llm_request_started(provider, correlation_id, metadata)

    # Assert
    mock_kafka_bus.publish.assert_called_once()
    call_args = mock_kafka_bus.publish.call_args

    # Check topic - it's the string topic name, not the enum
    assert call_args[0][0] == "huleedu.llm_provider.request_started.v1"

    # Check envelope
    envelope = call_args[0][1]
    assert envelope.event_type == "llm_provider.request_started.v1"
    assert envelope.source_service == "llm-provider-service"
    assert envelope.correlation_id == correlation_id

    # Check event data
    event_data = envelope.data
    assert event_data.provider == "openai"
    assert event_data.request_type == "comparison"
    assert event_data.correlation_id == correlation_id
    assert event_data.metadata == metadata


@pytest.mark.asyncio
async def test_publish_llm_request_completed_success(
    event_publisher: LLMEventPublisherImpl, mock_kafka_bus: AsyncMock
) -> None:
    """Test publishing successful LLM request completed event."""
    # Arrange
    provider = "anthropic"
    correlation_id = uuid4()
    success = True
    response_time_ms = 250
    metadata = {
        "model_used": "claude-3",
        "cached": False,
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "cost_estimate": 0.002,
    }

    # Act
    await event_publisher.publish_llm_request_completed(
        provider, correlation_id, success, response_time_ms, metadata
    )

    # Assert
    mock_kafka_bus.publish.assert_called_once()
    call_args = mock_kafka_bus.publish.call_args

    # Check event data
    envelope = call_args[0][1]
    event_data = envelope.data
    assert event_data.provider == "anthropic"
    assert event_data.request_type == "comparison"
    assert event_data.correlation_id == correlation_id
    assert event_data.success is True
    assert event_data.response_time_ms == 250
    assert event_data.error_message is None
    assert event_data.token_usage == metadata["token_usage"]
    assert event_data.cost_estimate == 0.002
    assert event_data.cached is False


@pytest.mark.asyncio
async def test_publish_llm_request_completed_failure(
    event_publisher: LLMEventPublisherImpl, mock_kafka_bus: AsyncMock
) -> None:
    """Test publishing failed LLM request completed event."""
    # Arrange
    provider = "openai"
    correlation_id = uuid4()
    success = False
    response_time_ms = 50
    metadata = {
        "error_message": "Rate limit exceeded",
        "failure_type": "rate_limit",
    }

    # Act
    await event_publisher.publish_llm_request_completed(
        provider, correlation_id, success, response_time_ms, metadata
    )

    # Assert
    mock_kafka_bus.publish.assert_called_once()
    call_args = mock_kafka_bus.publish.call_args

    # Check event data
    envelope = call_args[0][1]
    event_data = envelope.data
    assert event_data.provider == "openai"
    assert event_data.success is False
    assert event_data.response_time_ms == 50
    assert event_data.error_message == "Rate limit exceeded"
    assert event_data.metadata["failure_type"] == "rate_limit"


@pytest.mark.asyncio
async def test_publish_llm_provider_failure(
    event_publisher: LLMEventPublisherImpl, mock_kafka_bus: AsyncMock
) -> None:
    """Test publishing LLM provider failure event."""
    # Arrange
    provider = "google"
    failure_type = "service_unavailable"
    correlation_id = uuid4()
    error_details = "503 Service Unavailable"
    circuit_breaker_opened = True

    # Act
    await event_publisher.publish_llm_provider_failure(
        provider, failure_type, correlation_id, error_details, circuit_breaker_opened
    )

    # Assert
    mock_kafka_bus.publish.assert_called_once()
    call_args = mock_kafka_bus.publish.call_args

    # Check topic - it's the string topic name, not the enum
    assert call_args[0][0] == "huleedu.llm_provider.failure.v1"

    # Check event data
    envelope = call_args[0][1]
    event_data = envelope.data
    assert event_data.provider == "google"
    assert event_data.failure_type == "service_unavailable"
    assert event_data.correlation_id == correlation_id
    assert event_data.error_details == "503 Service Unavailable"
    assert event_data.circuit_breaker_opened is True


@pytest.mark.asyncio
async def test_event_publisher_error_handling(
    event_publisher: LLMEventPublisherImpl, mock_kafka_bus: AsyncMock
) -> None:
    """Test event publisher handles Kafka errors gracefully."""
    # Arrange
    mock_kafka_bus.publish.side_effect = Exception("Kafka connection failed")
    provider = "mock"
    correlation_id = uuid4()
    metadata: dict[str, str] = {}

    # Act - Should not raise exception
    await event_publisher.publish_llm_request_started(provider, correlation_id, metadata)

    # Assert - Error was logged but not propagated
    mock_kafka_bus.publish.assert_called_once()
