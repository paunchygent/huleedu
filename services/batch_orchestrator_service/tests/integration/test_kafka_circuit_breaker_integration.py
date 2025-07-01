"""
Integration tests for Kafka circuit breaker implementation.

These tests verify that the ResilientKafkaBus correctly handles
circuit breaker protection and fallback queuing for Kafka publishing.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock
from datetime import timedelta

from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaBus
from huleedu_service_libs.kafka.fallback_handler import QueuedMessage
from common_core.events.envelope import EventEnvelope
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone
from aiokafka.errors import KafkaError


class TestEventData(BaseModel):
    """Test event data model."""
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
    return EventEnvelope[TestEventData](
        event_id=uuid4(),
        event_type="test.event.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="test-service",
        correlation_id=uuid4(),
        data=TestEventData(
            message="test message",
            timestamp=datetime.now(timezone.utc)
        )
    )


@pytest.mark.asyncio
async def test_resilient_kafka_bus_normal_operation(circuit_breaker, test_envelope):
    """Test normal operation with circuit breaker closed."""
    # Mock the parent KafkaBus
    with pytest.MonkeyPatch() as m:
        mock_publish = AsyncMock()
        mock_start = AsyncMock()
        mock_stop = AsyncMock()
        
        # Create resilient bus
        resilient_bus = ResilientKafkaBus(
            client_id="test-client",
            bootstrap_servers="localhost:9092",
            circuit_breaker=circuit_breaker,
            max_queue_size=10,
        )
        
        # Mock parent methods
        m.setattr(resilient_bus, "_KafkaBus__dict__", {})
        resilient_bus._started = False
        resilient_bus.client_id = "test-client"
        
        # Replace parent methods with mocks
        super_publish = mock_publish
        super_start = mock_start
        super_stop = mock_stop
        
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.publish", super_publish)
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.start", super_start)
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.stop", super_stop)
        
        # Test start
        await resilient_bus.start()
        super_start.assert_called_once()
        
        # Test normal publishing
        await resilient_bus.publish("test-topic", test_envelope, "test-key")
        
        # Verify circuit breaker was used to call parent publish
        assert mock_publish.call_count == 1
        call_args = mock_publish.call_args
        assert call_args[0][0] == "test-topic"
        assert call_args[0][1] == test_envelope
        assert call_args[0][2] == "test-key"
        
        # Test stop
        await resilient_bus.stop()
        super_stop.assert_called_once()


@pytest.mark.asyncio
async def test_resilient_kafka_bus_without_circuit_breaker(test_envelope):
    """Test operation without circuit breaker."""
    with pytest.MonkeyPatch() as m:
        mock_publish = AsyncMock()
        mock_start = AsyncMock()
        mock_stop = AsyncMock()
        
        # Create resilient bus without circuit breaker
        resilient_bus = ResilientKafkaBus(
            client_id="test-client",
            bootstrap_servers="localhost:9092",
            circuit_breaker=None,  # No circuit breaker
        )
        
        # Mock parent methods
        m.setattr(resilient_bus, "_KafkaBus__dict__", {})
        resilient_bus._started = False
        resilient_bus.client_id = "test-client"
        
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.publish", mock_publish)
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.start", mock_start)
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.stop", mock_stop)
        
        await resilient_bus.start()
        
        # Test publishing without circuit breaker
        await resilient_bus.publish("test-topic", test_envelope, "test-key")
        
        # Should call parent publish directly
        mock_publish.assert_called_once_with("test-topic", test_envelope, "test-key")
        
        await resilient_bus.stop()


@pytest.mark.asyncio
async def test_circuit_breaker_open_queues_messages(circuit_breaker, test_envelope):
    """Test that messages are queued when circuit breaker is open."""
    with pytest.MonkeyPatch() as m:
        # Mock parent to always fail (to open circuit)
        mock_publish = AsyncMock(side_effect=KafkaError("Connection failed"))
        mock_start = AsyncMock()
        mock_stop = AsyncMock()
        
        resilient_bus = ResilientKafkaBus(
            client_id="test-client",
            bootstrap_servers="localhost:9092",
            circuit_breaker=circuit_breaker,
            max_queue_size=10,
        )
        
        m.setattr(resilient_bus, "_KafkaBus__dict__", {})
        resilient_bus._started = False
        resilient_bus.client_id = "test-client"
        
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.publish", mock_publish)
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.start", mock_start)
        m.setattr("huleedu_service_libs.kafka_client.KafkaBus.stop", mock_stop)
        
        await resilient_bus.start()
        
        # Trigger circuit breaker to open by causing failures
        for _ in range(circuit_breaker.failure_threshold):
            try:
                await resilient_bus.publish("test-topic", test_envelope, "test-key")
            except KafkaError:
                pass  # Expected failures
        
        # Circuit should now be open
        assert circuit_breaker.state.value == "open"
        
        # Next publish should queue the message instead of throwing error
        initial_queue_size = resilient_bus.get_fallback_queue_size()
        await resilient_bus.publish("test-topic", test_envelope, "test-key")
        
        # Verify message was queued
        assert resilient_bus.get_fallback_queue_size() == initial_queue_size + 1
        
        await resilient_bus.stop()


def test_circuit_breaker_state_reporting(circuit_breaker):
    """Test circuit breaker state reporting."""
    resilient_bus = ResilientKafkaBus(
        client_id="test-client",
        bootstrap_servers="localhost:9092",
        circuit_breaker=circuit_breaker,
    )
    
    state = resilient_bus.get_circuit_breaker_state()
    
    assert state["enabled"] is True
    assert state["name"] == "test_kafka"
    assert state["state"] == "closed"
    assert "fallback_queue_size" in state


def test_circuit_breaker_state_without_breaker():
    """Test state reporting without circuit breaker."""
    resilient_bus = ResilientKafkaBus(
        client_id="test-client",
        bootstrap_servers="localhost:9092",
        circuit_breaker=None,
    )
    
    state = resilient_bus.get_circuit_breaker_state()
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
    test_envelope = EventEnvelope[TestEventData](
        event_id=uuid4(),
        event_type="test.event.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="test-service",
        data=TestEventData(message="test", timestamp=datetime.now(timezone.utc))
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
    for i in range(3):
        await handler.queue_message(queued_message)
    
    # Next one should raise exception
    with pytest.raises(Exception, match="Fallback queue is full"):
        await handler.queue_message(queued_message)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])