"""
Unit tests for Class Management Service resilient Kafka functionality.

These tests verify the circuit breaker behavior specifically for the
Class Management Service use cases and publishing patterns.
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


class ClassManagementEventData(BaseModel):
    """Test data model for class management events."""
    class_id: str
    action: str
    user_id: str
    timestamp: datetime


@pytest.fixture
def mock_kafka_bus():
    """Mock KafkaBus for testing."""
    mock_bus = AsyncMock(spec=KafkaBus)
    mock_bus.client_id = "class_management_service-test-producer"
    mock_bus.bootstrap_servers = "localhost:9092"
    return mock_bus


@pytest.fixture
def circuit_breaker():
    """Circuit breaker configured for Class Management Service."""
    return CircuitBreaker(
        name="class_management_service.kafka_producer",
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=1),  # Short for testing
        success_threshold=2,
        expected_exception=KafkaError,
    )


@pytest.fixture
def resilient_publisher(mock_kafka_bus, circuit_breaker):
    """ResilientKafkaPublisher for testing."""
    return ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
        retry_interval=1,  # Short for testing
    )


@pytest.fixture
def sample_class_event():
    """Sample class management event for testing."""
    return EventEnvelope(
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
async def test_successful_publish(resilient_publisher, sample_class_event):
    """Test successful event publishing through circuit breaker."""
    topic = "huleedu.class.student.added.v1"

    # Mock successful publish
    resilient_publisher.delegate.publish.return_value = None

    # Should publish successfully
    await resilient_publisher.publish(topic, sample_class_event)

    # Verify delegate was called (note: includes key parameter)
    resilient_publisher.delegate.publish.assert_called_once_with(topic, sample_class_event, None)

    # Circuit breaker should remain closed
    assert resilient_publisher.circuit_breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures(resilient_publisher, sample_class_event):
    """Test that circuit breaker opens after repeated failures."""
    topic = "huleedu.class.student.added.v1"

    # Mock failing publish calls
    resilient_publisher.delegate.publish.side_effect = KafkaError("Connection failed")

    # First few failures should be stored in fallback queue (catch exceptions)
    for _ in range(3):
        try:
            await resilient_publisher.publish(topic, sample_class_event)
        except KafkaError:
            pass  # Expected during circuit breaker testing

    # Circuit breaker should now be open
    assert resilient_publisher.circuit_breaker.state == CircuitState.OPEN

    # Verify events were queued
    assert resilient_publisher.get_fallback_queue_size() == 3

    # Verify delegate was called 3 times before circuit opened
    assert resilient_publisher.delegate.publish.call_count == 3


@pytest.mark.asyncio
async def test_fallback_queue_behavior(resilient_publisher, sample_class_event):
    """Test fallback queue stores failed messages correctly."""
    topic = "huleedu.class.student.added.v1"

    # Force circuit breaker open
    resilient_publisher.circuit_breaker.state = CircuitState.OPEN
    resilient_publisher.circuit_breaker.last_failure_time = datetime.now()

    # Publish should queue message without calling delegate
    await resilient_publisher.publish(topic, sample_class_event)

    # Verify message was queued
    assert resilient_publisher.get_fallback_queue_size() == 1

    # Verify delegate was NOT called (circuit is open)
    resilient_publisher.delegate.publish.assert_not_called()


@pytest.mark.asyncio
async def test_circuit_breaker_recovery(resilient_publisher, sample_class_event):
    """Test circuit breaker recovery after successful publishes."""
    topic = "huleedu.class.student.added.v1"

    # Force circuit breaker to half-open state
    resilient_publisher.circuit_breaker.state = CircuitState.HALF_OPEN

    # Mock successful publishes
    resilient_publisher.delegate.publish.return_value = None

    # Need 2 successful calls to close circuit (success_threshold=2)
    await resilient_publisher.publish(topic, sample_class_event)
    await resilient_publisher.publish(topic, sample_class_event)

    # Circuit should now be closed
    assert resilient_publisher.circuit_breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_fallback_queue_retry_mechanism(resilient_publisher):
    """Test that fallback queue messages can be queued and retrieved."""
    topic = "huleedu.class.student.added.v1"

    # Create test event
    class_event = EventEnvelope(
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
async def test_class_specific_error_scenarios(resilient_publisher):
    """Test Class Management Service specific error scenarios."""
    # Test class creation event with large payload
    large_class_event = EventEnvelope(
        event_type="huleedu.class.created.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="class_management_service",
        correlation_id=uuid4(),
        data={
            "class_id": "large-class-123",
            "class_name": "Very Long Class Name" * 100,  # Large payload
            "student_count": 500,
            "metadata": {"description": "A" * 10000},  # Large metadata
        },
    )

    topic = "huleedu.class.created.v1"

    # Mock Kafka timeout (common with large messages)
    resilient_publisher.delegate.publish.side_effect = KafkaError("Message too large")

    # Should handle error gracefully
    try:
        await resilient_publisher.publish(topic, large_class_event)
    except KafkaError:
        pass  # Expected during circuit breaker testing

    # Verify event was queued for retry
    assert resilient_publisher.get_fallback_queue_size() == 1


@pytest.mark.asyncio
async def test_circuit_breaker_state_reporting(resilient_publisher):
    """Test circuit breaker state reporting functionality."""
    # Initially closed
    state = resilient_publisher.get_circuit_breaker_state()
    assert state["enabled"] is True
    assert state["state"] == "closed"
    assert state["name"] == "class_management_service.kafka_producer"
    assert state["failure_count"] == 0

    # Force some failures
    resilient_publisher.delegate.publish.side_effect = KafkaError("Test failure")

    sample_event = EventEnvelope(
        event_type="test.event",
        event_timestamp=datetime.now(timezone.utc),
        source_service="class_management_service",
        correlation_id=uuid4(),
        data={"test": "data"},
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
async def test_resource_cleanup(resilient_publisher):
    """Test proper resource cleanup."""
    # Verify start/stop delegation
    await resilient_publisher.start()
    resilient_publisher.delegate.start.assert_called_once()

    await resilient_publisher.stop()
    resilient_publisher.delegate.stop.assert_called_once()


@pytest.mark.asyncio
async def test_class_management_specific_events(resilient_publisher):
    """Test Class Management Service specific events."""
    # Test student enrollment event
    enrollment_event = EventEnvelope(
        event_type="huleedu.class.student.enrolled.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="class_management_service",
        correlation_id=uuid4(),
        data={
            "class_id": "class-789",
            "student_id": "student-456",
            "enrolled_by": "teacher-123",
            "enrollment_date": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        },
    )

    topic = "huleedu.class.student.enrolled.v1"

    # Mock successful publish
    resilient_publisher.delegate.publish.return_value = None

    # Should publish successfully
    await resilient_publisher.publish(topic, enrollment_event)

    # Verify correct topic and event (with key parameter)
    resilient_publisher.delegate.publish.assert_called_once_with(topic, enrollment_event, None)
