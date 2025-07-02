"""
Unit tests for File Service resilient Kafka functionality.

These tests verify the circuit breaker behavior specifically for the
File Service use cases and publishing patterns.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka.errors import KafkaError
from huleedu_service_libs.kafka.fallback_handler import QueuedMessage
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker, CircuitState
from pydantic import BaseModel

from common_core.events.envelope import EventEnvelope


class FileValidationData(BaseModel):
    """Test data model for file validation events."""

    file_id: str
    batch_id: str
    status: str
    content_length: int
    timestamp: datetime


class SimpleTestData(BaseModel):
    """Simple test data model for basic events."""

    test: str


class BatchFileData(BaseModel):
    """Test data model for batch file events."""

    batch_id: str
    file_id: str
    added_by: str
    timestamp: str


@pytest.fixture
def mock_kafka_bus() -> AsyncMock:
    """Mock KafkaBus for testing."""
    mock_bus = AsyncMock(spec=KafkaBus)
    mock_bus.client_id = "file-service-test-producer"
    mock_bus.bootstrap_servers = "localhost:9092"
    return mock_bus


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Circuit breaker configured for File Service."""
    return CircuitBreaker(
        name="file-service.kafka_producer",
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=1),  # Short for testing
        success_threshold=2,
        expected_exception=KafkaError,
    )


@pytest.fixture
def resilient_publisher(mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker) -> ResilientKafkaPublisher:
    """ResilientKafkaPublisher for testing."""
    return ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
        retry_interval=1,  # Short for testing
    )


@pytest.fixture
def sample_file_event() -> EventEnvelope[FileValidationData]:
    """Sample file validation event for testing."""
    return EventEnvelope[FileValidationData](
        event_type="huleedu.file.essay.validation.success.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="file-service",
        correlation_id=uuid4(),
        data=FileValidationData(
            file_id="test-file-123",
            batch_id="test-batch-456",
            status="validated",
            content_length=5000,
            timestamp=datetime.now(timezone.utc),
        ),
    )


@pytest.mark.asyncio
async def test_successful_publish(resilient_publisher: ResilientKafkaPublisher, sample_file_event: EventEnvelope[FileValidationData]) -> None:
    """Test successful event publishing through circuit breaker."""
    topic = "huleedu.file.essay.validation.success.v1"

    # Mock successful publish
    resilient_publisher.delegate.publish.return_value = None

    # Should publish successfully
    await resilient_publisher.publish(topic, sample_file_event)

    # Verify delegate was called (note: includes key parameter)
    resilient_publisher.delegate.publish.assert_called_once_with(topic, sample_file_event, None)

    # Circuit breaker should remain closed
    assert resilient_publisher.circuit_breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures(resilient_publisher: ResilientKafkaPublisher, sample_file_event: EventEnvelope[FileValidationData]) -> None:
    """Test that circuit breaker opens after repeated failures."""
    topic = "huleedu.file.essay.validation.success.v1"

    # Mock failing publish calls
    resilient_publisher.delegate.publish.side_effect = KafkaError("Connection failed")

    # First few failures should be stored in fallback queue (catch exceptions)
    for _ in range(3):
        try:
            await resilient_publisher.publish(topic, sample_file_event)
        except KafkaError:
            pass  # Expected during circuit breaker testing

    # Circuit breaker should now be open
    assert resilient_publisher.circuit_breaker.state == CircuitState.OPEN

    # Verify events were queued
    assert resilient_publisher.get_fallback_queue_size() == 3

    # Verify delegate was called 3 times before circuit opened
    assert resilient_publisher.delegate.publish.call_count == 3


@pytest.mark.asyncio
async def test_fallback_queue_behavior(resilient_publisher: ResilientKafkaPublisher, sample_file_event: EventEnvelope[FileValidationData]) -> None:
    """Test fallback queue stores failed messages correctly."""
    topic = "huleedu.file.essay.validation.success.v1"

    # Force circuit breaker open
    resilient_publisher.circuit_breaker.state = CircuitState.OPEN
    resilient_publisher.circuit_breaker.last_failure_time = datetime.now()

    # Publish should queue message without calling delegate
    await resilient_publisher.publish(topic, sample_file_event)

    # Verify message was queued
    assert resilient_publisher.get_fallback_queue_size() == 1

    # Verify delegate was NOT called (circuit is open)
    resilient_publisher.delegate.publish.assert_not_called()


@pytest.mark.asyncio
async def test_circuit_breaker_recovery(resilient_publisher: ResilientKafkaPublisher, sample_file_event: EventEnvelope[FileValidationData]) -> None:
    """Test circuit breaker recovery after successful publishes."""
    topic = "huleedu.file.essay.validation.success.v1"

    # Force circuit breaker to half-open state
    resilient_publisher.circuit_breaker.state = CircuitState.HALF_OPEN

    # Mock successful publishes
    resilient_publisher.delegate.publish.return_value = None

    # Need 2 successful calls to close circuit (success_threshold=2)
    await resilient_publisher.publish(topic, sample_file_event)
    await resilient_publisher.publish(topic, sample_file_event)

    # Circuit should now be closed
    assert resilient_publisher.circuit_breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_fallback_queue_retry_mechanism(resilient_publisher: ResilientKafkaPublisher) -> None:
    """Test that fallback queue messages can be queued and retrieved."""
    topic = "huleedu.file.essay.validation.success.v1"

    # Create test event
    file_event = EventEnvelope[FileValidationData](
        event_type="huleedu.file.essay.validation.success.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="file-service",
        correlation_id=uuid4(),
        data=FileValidationData(
            file_id="queued-file-123",
            batch_id="queued-batch-456",
            status="validated",
            content_length=3000,
            timestamp=datetime.now(timezone.utc),
        ),
    )

    # Manually add to fallback queue
    queued_message = QueuedMessage(
        topic=topic,
        envelope=file_event,
        key=None,
        queued_at=datetime.now(timezone.utc),
        retry_count=0,
    )
    await resilient_publisher.fallback_handler.queue_message(queued_message)

    # Verify queue has the message
    assert resilient_publisher.get_fallback_queue_size() == 1

    # Test that we can retrieve the message
    retrieved_message = await resilient_publisher.fallback_handler.get_next_message()
    assert retrieved_message is not None
    assert retrieved_message.topic == topic
    assert retrieved_message.envelope.event_id == file_event.event_id

    # Queue should be empty after retrieval
    assert resilient_publisher.get_fallback_queue_size() == 0


@pytest.mark.asyncio
async def test_file_specific_error_scenarios(resilient_publisher: ResilientKafkaPublisher) -> None:
    """Test File Service specific error scenarios."""
    # Test large file validation event
    large_file_event = EventEnvelope[FileValidationData](
        event_type="huleedu.file.essay.validation.failed.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="file-service",
        correlation_id=uuid4(),
        data=FileValidationData(
            file_id="large-file-123",
            batch_id="batch-456",
            status="failed",
            content_length=55000,  # Over limit
            timestamp=datetime.now(timezone.utc),
        ),
    )

    topic = "huleedu.file.essay.validation.failed.v1"

    # Mock Kafka timeout (common with large messages)
    resilient_publisher.delegate.publish.side_effect = KafkaError("Message too large")

    # Should handle error gracefully
    try:
        await resilient_publisher.publish(topic, large_file_event)
    except KafkaError:
        pass  # Expected during circuit breaker testing

    # Verify event was queued for retry
    assert resilient_publisher.get_fallback_queue_size() == 1


@pytest.mark.asyncio
async def test_circuit_breaker_state_reporting(resilient_publisher: ResilientKafkaPublisher) -> None:
    """Test circuit breaker state reporting functionality."""
    # Initially closed
    state = resilient_publisher.get_circuit_breaker_state()
    assert state["enabled"] is True
    assert state["state"] == "closed"
    assert state["name"] == "file-service.kafka_producer"
    assert state["failure_count"] == 0

    # Force some failures
    resilient_publisher.delegate.publish.side_effect = KafkaError("Test failure")

    test_data = SimpleTestData(test="data")
    sample_event = EventEnvelope[SimpleTestData](
        event_type="test.event",
        event_timestamp=datetime.now(timezone.utc),
        source_service="file-service",
        correlation_id=uuid4(),
        data=test_data,
    )

    # Cause failures
    for _ in range(3):
        try:
            await resilient_publisher.publish("test.topic", sample_event)
        except KafkaError:
            pass  # Expected during circuit breaker testing

    # Check updated state
    state = resilient_publisher.get_circuit_breaker_state()
    assert state["state"] == "open"
    assert state["failure_count"] >= 3


@pytest.mark.asyncio
async def test_resource_cleanup(resilient_publisher: ResilientKafkaPublisher) -> None:
    """Test proper resource cleanup."""
    # Verify start/stop delegation
    await resilient_publisher.start()
    resilient_publisher.delegate.start.assert_called_once()

    await resilient_publisher.stop()
    resilient_publisher.delegate.stop.assert_called_once()


@pytest.mark.asyncio
async def test_file_batch_management_events(resilient_publisher: ResilientKafkaPublisher) -> None:
    """Test File Service specific batch management events."""
    # Test batch file added event
    batch_data = BatchFileData(
        batch_id="batch-789",
        file_id="file-456",
        added_by="user-123",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    batch_file_event = EventEnvelope[BatchFileData](
        event_type="huleedu.file.batch.file.added.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="file-service",
        correlation_id=uuid4(),
        data=batch_data,
    )

    topic = "huleedu.file.batch.file.added.v1"

    # Mock successful publish
    resilient_publisher.delegate.publish.return_value = None

    # Should publish successfully
    await resilient_publisher.publish(topic, batch_file_event)

    # Verify correct topic and event (with key parameter)
    resilient_publisher.delegate.publish.assert_called_once_with(topic, batch_file_event, None)
