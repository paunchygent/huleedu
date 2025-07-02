"""
Integration tests for Kafka circuit breaker implementation.

These tests verify that the ResilientKafkaPublisher correctly handles
circuit breaker protection and fallback queuing for Kafka publishing.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka.errors import KafkaError
from huleedu_service_libs.kafka.fallback_handler import QueuedMessage
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from pydantic import BaseModel

from common_core.events.envelope import EventEnvelope


class _TestEventData(BaseModel):
    """Test event data model for testing purposes."""

    message: str
    timestamp: datetime


@pytest.fixture
def circuit_breaker():
    """Circuit breaker for testing."""
    return CircuitBreaker(
        name="test_kafka",
        failure_threshold=2,
        recovery_timeout=timedelta(seconds=1),
        success_threshold=1,
        expected_exception=KafkaError,
    )


@pytest.fixture
def test_envelope():
    """Test event envelope."""
    return EventEnvelope[_TestEventData](
        event_id=uuid4(),
        event_type="test.event.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="test-service",
        correlation_id=uuid4(),
        data=_TestEventData(message="test message", timestamp=datetime.now(timezone.utc)),
    )


@pytest.mark.asyncio
async def test_resilient_kafka_publisher_normal_operation(circuit_breaker, test_envelope):
    """Test normal operation with circuit breaker closed."""
    # Create mock KafkaBus delegate
    mock_kafka_bus = AsyncMock(spec=KafkaBus)
    mock_kafka_bus.client_id = "test-client"
    mock_kafka_bus.bootstrap_servers = "localhost:9092"

    # Create resilient publisher with mock delegate
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
        retry_interval=1,
    )

    # Test start
    await resilient_publisher.start()
    mock_kafka_bus.start.assert_called_once()

    # Test normal publishing
    await resilient_publisher.publish("test-topic", test_envelope, "test-key")

    # Verify delegate was called through circuit breaker
    mock_kafka_bus.publish.assert_called_once_with("test-topic", test_envelope, "test-key")

    # Test stop
    await resilient_publisher.stop()
    mock_kafka_bus.stop.assert_called_once()


@pytest.mark.asyncio
async def test_resilient_kafka_publisher_without_circuit_breaker(test_envelope):
    """Test operation without circuit breaker."""
    # Create mock KafkaBus delegate
    mock_kafka_bus = AsyncMock(spec=KafkaBus)
    mock_kafka_bus.client_id = "test-client"
    mock_kafka_bus.bootstrap_servers = "localhost:9092"

    # Create resilient publisher without circuit breaker
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=None,  # No circuit breaker
        retry_interval=1,
    )

    await resilient_publisher.start()

    # Test publishing without circuit breaker
    await resilient_publisher.publish("test-topic", test_envelope, "test-key")

    # Should call delegate publish directly
    mock_kafka_bus.publish.assert_called_once_with("test-topic", test_envelope, "test-key")

    await resilient_publisher.stop()


@pytest.mark.asyncio
async def test_circuit_breaker_open_queues_messages(circuit_breaker, test_envelope):
    """Test that messages are queued when circuit breaker is open."""
    # Create mock KafkaBus that always fails (to open circuit)
    mock_kafka_bus = AsyncMock(spec=KafkaBus)
    mock_kafka_bus.client_id = "test-client"
    mock_kafka_bus.bootstrap_servers = "localhost:9092"
    mock_kafka_bus.publish.side_effect = KafkaError("Connection failed")

    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
        retry_interval=1,
    )

    await resilient_publisher.start()

    # Trigger circuit breaker to open by causing failures
    for _ in range(circuit_breaker.failure_threshold):
        try:
            await resilient_publisher.publish("test-topic", test_envelope, "test-key")
        except KafkaError:
            pass  # Expected failures

    # Circuit should now be open
    assert circuit_breaker.state.value == "open"

    # Next publish should queue the message instead of throwing error
    initial_queue_size = resilient_publisher.get_fallback_queue_size()
    await resilient_publisher.publish("test-topic", test_envelope, "test-key")

    # Verify message was queued
    assert resilient_publisher.get_fallback_queue_size() == initial_queue_size + 1

    await resilient_publisher.stop()


def test_circuit_breaker_state_reporting(circuit_breaker):
    """Test circuit breaker state reporting."""
    mock_kafka_bus = AsyncMock(spec=KafkaBus)
    mock_kafka_bus.client_id = "test-client"
    mock_kafka_bus.bootstrap_servers = "localhost:9092"

    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    state = resilient_publisher.get_circuit_breaker_state()

    assert state["enabled"] is True
    assert state["name"] == "test_kafka"
    assert state["state"] == "closed"
    assert "fallback_queue_size" in state


def test_circuit_breaker_state_without_breaker():
    """Test state reporting without circuit breaker."""
    mock_kafka_bus = AsyncMock(spec=KafkaBus)
    mock_kafka_bus.client_id = "test-client"
    mock_kafka_bus.bootstrap_servers = "localhost:9092"

    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=None,
    )

    state = resilient_publisher.get_circuit_breaker_state()
    assert state["enabled"] is False


@pytest.mark.asyncio
async def test_fallback_queue_operations():
    """Test fallback queue basic operations."""
    from huleedu_service_libs.kafka.fallback_handler import FallbackMessageHandler

    handler = FallbackMessageHandler(max_queue_size=3)

    # Test empty queue
    assert handler.queue_size() == 0
    assert not handler.has_queued_messages()
    assert await handler.get_next_message() is None

    # Create test message
    test_envelope = EventEnvelope[_TestEventData](
        event_id=uuid4(),
        event_type="test.event.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="test-service",
        data=_TestEventData(message="test", timestamp=datetime.now(timezone.utc)),
    )

    queued_message = QueuedMessage(
        topic="test-topic",
        envelope=test_envelope,
        key="test-key",
        queued_at=datetime.now(timezone.utc),
        retry_count=0,
    )

    # Test queuing
    await handler.queue_message(queued_message)
    assert handler.queue_size() == 1
    assert handler.has_queued_messages()

    # Test getting message
    retrieved = await handler.get_next_message()
    assert retrieved is not None
    assert retrieved.topic == "test-topic"
    assert retrieved.key == "test-key"
    assert handler.queue_size() == 0

    # Test queue full
    for _ in range(3):
        await handler.queue_message(queued_message)

    # Next one should raise exception
    with pytest.raises(Exception, match="Fallback queue is full"):
        await handler.queue_message(queued_message)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
