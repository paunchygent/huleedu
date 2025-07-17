"""
Unit tests for Class Management Service resilient Kafka functionality.

These tests verify the circuit breaker behavior specifically for the
Class Management Service use cases and publishing patterns.
"""

from datetime import datetime, timedelta, timezone
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka.errors import KafkaError
from common_core import CircuitBreakerState
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.kafka.fallback_handler import QueuedMessage
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from pydantic import BaseModel


class ClassManagementEventData(BaseModel):
    """Test data model for class management events."""

    class_id: str
    action: str
    user_id: str
    timestamp: datetime


class LargeClassData(BaseModel):
    """Test data model for large class events."""

    class_id: str
    class_name: str
    student_count: int
    metadata: dict


class SimpleTestData(BaseModel):
    """Simple test data model for basic events."""

    test: str


class EnrollmentData(BaseModel):
    """Test data model for enrollment events."""

    class_id: str
    student_id: str
    enrolled_by: str
    enrollment_date: str
    status: str


@pytest.fixture
def mock_kafka_bus() -> AsyncMock:
    """Mock KafkaBus for testing."""
    mock_bus = AsyncMock(spec=KafkaBus)
    mock_bus.client_id = "class_management_service-test-producer"
    mock_bus.bootstrap_servers = "localhost:9092"
    return mock_bus


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Circuit breaker configured for Class Management Service."""
    return CircuitBreaker(
        name="class_management_service.kafka_producer",
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=1),  # Short for testing
        success_threshold=2,
        expected_exception=KafkaError,
    )


@pytest.fixture
def resilient_publisher(
    mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker
) -> ResilientKafkaPublisher:
    """ResilientKafkaPublisher for testing."""
    return ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
        retry_interval=1,  # Short for testing
    )


@pytest.fixture
def sample_class_event() -> EventEnvelope[ClassManagementEventData]:
    """Sample class management event for testing."""
    return EventEnvelope[ClassManagementEventData](
        event_type="huleedu.class.student.added.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="class_management_service",
        correlation_id=uuid4(),
        data=ClassManagementEventData(
            class_id="class-123",
            action="student_added",
            user_id="user-456",
            timestamp=datetime.now(timezone.utc),
        ),
    )


@pytest.mark.asyncio
async def test_successful_publish(
    resilient_publisher: ResilientKafkaPublisher,
    sample_class_event: EventEnvelope[ClassManagementEventData],
) -> None:
    """Test successful event publishing through circuit breaker."""
    topic = "huleedu.class.student.added.v1"

    # Mock successful publish
    cast(AsyncMock, resilient_publisher.delegate.publish).return_value = None

    # Should publish successfully
    await resilient_publisher.publish(topic, sample_class_event)

    # Verify delegate was called (note: includes key parameter)
    cast(AsyncMock, resilient_publisher.delegate.publish).assert_called_once_with(
        topic, sample_class_event, None
    )

    # Circuit breaker should remain closed
    assert resilient_publisher.circuit_breaker is not None
    assert resilient_publisher.circuit_breaker.state == CircuitBreakerState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures(
    resilient_publisher: ResilientKafkaPublisher,
    sample_class_event: EventEnvelope[ClassManagementEventData],
) -> None:
    """Test that circuit breaker opens after repeated failures."""
    topic = "huleedu.class.student.added.v1"

    # Mock failing publish calls
    cast(AsyncMock, resilient_publisher.delegate.publish).side_effect = KafkaError(
        "Connection failed"
    )

    # First few failures should be stored in fallback queue (catch exceptions)
    for _ in range(3):
        try:
            await resilient_publisher.publish(topic, sample_class_event)
        except KafkaError:
            pass  # Expected during circuit breaker testing

    # Circuit breaker should now be open
    assert resilient_publisher.circuit_breaker is not None
    assert resilient_publisher.circuit_breaker.state == CircuitBreakerState.OPEN

    # Verify events were queued
    assert resilient_publisher.get_fallback_queue_size() == 3

    # Verify delegate was called 3 times before circuit opened
    assert cast(AsyncMock, resilient_publisher.delegate.publish).call_count == 3


@pytest.mark.asyncio
async def test_fallback_queue_behavior(
    resilient_publisher: ResilientKafkaPublisher,
    sample_class_event: EventEnvelope[ClassManagementEventData],
) -> None:
    """Test fallback queue stores failed messages correctly."""
    topic = "huleedu.class.student.added.v1"

    # Force circuit breaker open
    assert resilient_publisher.circuit_breaker is not None
    resilient_publisher.circuit_breaker.state = CircuitBreakerState.OPEN
    resilient_publisher.circuit_breaker.last_failure_time = datetime.now()

    # Publish should queue message without calling delegate
    await resilient_publisher.publish(topic, sample_class_event)

    # Verify message was queued
    assert resilient_publisher.get_fallback_queue_size() == 1

    # Verify delegate was NOT called (circuit is open)
    cast(AsyncMock, resilient_publisher.delegate.publish).assert_not_called()


@pytest.mark.asyncio
async def test_circuit_breaker_recovery(
    resilient_publisher: ResilientKafkaPublisher,
    sample_class_event: EventEnvelope[ClassManagementEventData],
) -> None:
    """Test circuit breaker recovery after successful publishes."""
    topic = "huleedu.class.student.added.v1"

    # Force circuit breaker to half-open state
    assert resilient_publisher.circuit_breaker is not None
    resilient_publisher.circuit_breaker.state = CircuitBreakerState.HALF_OPEN

    # Mock successful publishes
    cast(AsyncMock, resilient_publisher.delegate.publish).return_value = None

    # Need 2 successful calls to close circuit (success_threshold=2)
    await resilient_publisher.publish(topic, sample_class_event)
    await resilient_publisher.publish(topic, sample_class_event)

    # Circuit should now be closed
    assert resilient_publisher.circuit_breaker is not None
    assert resilient_publisher.circuit_breaker.state == CircuitBreakerState.CLOSED


@pytest.mark.asyncio
async def test_fallback_queue_retry_mechanism(resilient_publisher: ResilientKafkaPublisher) -> None:
    """Test that fallback queue messages can be queued and retrieved."""
    topic = "huleedu.class.student.added.v1"

    # Create test event
    class_event = EventEnvelope[ClassManagementEventData](
        event_type="huleedu.class.student.added.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="class_management_service",
        correlation_id=uuid4(),
        data=ClassManagementEventData(
            class_id="queued-class-123",
            action="student_added",
            user_id="queued-user-456",
            timestamp=datetime.now(timezone.utc),
        ),
    )

    # Manually add to fallback queue
    queued_message = QueuedMessage(
        topic=topic,
        envelope=class_event,
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
    assert retrieved_message.envelope.event_id == class_event.event_id

    # Queue should be empty after retrieval
    assert resilient_publisher.get_fallback_queue_size() == 0


@pytest.mark.asyncio
async def test_class_specific_error_scenarios(resilient_publisher: ResilientKafkaPublisher) -> None:
    """Test Class Management Service specific error scenarios."""
    # Test class creation event with large payload
    large_class_data = LargeClassData(
        class_id="large-class-123",
        class_name="Very Long Class Name" * 100,  # Large payload
        student_count=500,
        metadata={"description": "A" * 10000},  # Large metadata
    )
    large_class_event = EventEnvelope[LargeClassData](
        event_type="huleedu.class.created.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="class_management_service",
        correlation_id=uuid4(),
        data=large_class_data,
    )

    topic = "huleedu.class.created.v1"

    # Mock Kafka timeout (common with large messages)
    cast(AsyncMock, resilient_publisher.delegate.publish).side_effect = KafkaError(
        "Message too large"
    )

    # Should handle error gracefully
    try:
        await resilient_publisher.publish(topic, large_class_event)
    except KafkaError:
        pass  # Expected during circuit breaker testing

    # Verify event was queued for retry
    assert resilient_publisher.get_fallback_queue_size() == 1


@pytest.mark.asyncio
async def test_circuit_breaker_state_reporting(
    resilient_publisher: ResilientKafkaPublisher,
) -> None:
    """Test circuit breaker state reporting functionality."""
    # Initially closed
    state = resilient_publisher.get_circuit_breaker_state()
    assert state["enabled"] is True
    assert state["state"] == "closed"
    assert state["name"] == "class_management_service.kafka_producer"
    assert state["failure_count"] == 0

    # Force some failures
    cast(AsyncMock, resilient_publisher.delegate.publish).side_effect = KafkaError("Test failure")

    test_data = SimpleTestData(test="data")
    sample_event = EventEnvelope[SimpleTestData](
        event_type="test.event",
        event_timestamp=datetime.now(timezone.utc),
        source_service="class_management_service",
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
    cast(AsyncMock, resilient_publisher.delegate.start).assert_called_once()

    await resilient_publisher.stop()
    cast(AsyncMock, resilient_publisher.delegate.stop).assert_called_once()


@pytest.mark.asyncio
async def test_class_management_specific_events(
    resilient_publisher: ResilientKafkaPublisher,
) -> None:
    """Test Class Management Service specific events."""
    # Test student enrollment event
    enrollment_data = EnrollmentData(
        class_id="class-789",
        student_id="student-456",
        enrolled_by="teacher-123",
        enrollment_date=datetime.now(timezone.utc).isoformat(),
        status="active",
    )
    enrollment_event = EventEnvelope[EnrollmentData](
        event_type="huleedu.class.student.enrolled.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="class_management_service",
        correlation_id=uuid4(),
        data=enrollment_data,
    )

    topic = "huleedu.class.student.enrolled.v1"

    # Mock successful publish
    cast(AsyncMock, resilient_publisher.delegate.publish).return_value = None

    # Should publish successfully
    await resilient_publisher.publish(topic, enrollment_event)

    # Verify correct topic and event (with key parameter)
    cast(AsyncMock, resilient_publisher.delegate.publish).assert_called_once_with(
        topic, enrollment_event, None
    )
