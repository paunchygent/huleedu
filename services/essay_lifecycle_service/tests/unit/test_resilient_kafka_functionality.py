"""
Unit tests for Essay Lifecycle Service resilient Kafka functionality.

These tests verify the circuit breaker behavior specifically for the 
Essay Lifecycle Service use cases and publishing patterns.
"""

import asyncio
import pytest
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, Mock
from datetime import datetime, timezone, timedelta

from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerError
from huleedu_service_libs.kafka.fallback_handler import QueuedMessage
from common_core.events.envelope import EventEnvelope
from pydantic import BaseModel
from uuid import uuid4
from aiokafka.errors import KafkaError


class EssayStateChangeData(BaseModel):
    """Test data model for essay state change events."""
    essay_id: str
    previous_state: str
    new_state: str
    batch_id: str
    timestamp: datetime


@pytest.fixture
def mock_kafka_bus() -> AsyncMock:
    """Mock KafkaBus for testing."""
    mock_bus = AsyncMock(spec=KafkaBus)
    mock_bus.client_id = "essay-lifecycle-test-producer"
    mock_bus.bootstrap_servers = "localhost:9092"
    return mock_bus


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Circuit breaker configured for Essay Lifecycle Service."""
    return CircuitBreaker(
        name="essay-lifecycle-service.kafka_producer",
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=1),  # Short for testing
        success_threshold=2,
        expected_exception=KafkaError,
    )


@pytest.fixture
def test_event() -> EventEnvelope[EssayStateChangeData]:
    """Test event envelope for essay lifecycle events."""
    return EventEnvelope[EssayStateChangeData](
        event_id=uuid4(),
        event_type="huleedu.essay.state.changed.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="essay-lifecycle-service",
        correlation_id=uuid4(),
        data=EssayStateChangeData(
            essay_id="essay_123",
            previous_state="draft",
            new_state="spellcheck_pending",
            batch_id="batch_456",
            timestamp=datetime.now(timezone.utc)
        )
    )


@pytest.mark.asyncio
async def test_normal_publishing_flow(mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker, test_event: EventEnvelope[EssayStateChangeData]) -> None:
    """Test normal Kafka publishing through circuit breaker."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )
    
    try:
        # Test successful publishing
        await resilient_publisher.publish("huleedu.essay.state.changed", test_event, "essay_123")
        
        # Verify delegate was called
        mock_kafka_bus.publish.assert_called_once_with(
            "huleedu.essay.state.changed", test_event, "essay_123"
        )
    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures(mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker, test_event: EventEnvelope[EssayStateChangeData]) -> None:
    """Test that circuit breaker opens after repeated failures."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )
    
    # Clear any existing queue state
    await resilient_publisher.fallback_handler.clear_queue()
    
    try:
        mock_kafka_bus.publish.side_effect = KafkaError("Connection failed")
        
        # Trigger failures to open circuit
        for i in range(circuit_breaker.failure_threshold):
            try:
                await resilient_publisher.publish("test.topic", test_event)
            except KafkaError:
                pass  # Expected
        
        # Circuit should be open now
        assert circuit_breaker.state.value == "open"
        
        # Clear the queue to get a clean starting point
        await resilient_publisher.fallback_handler.clear_queue()
        initial_queue_size = resilient_publisher.get_fallback_queue_size()
        assert initial_queue_size == 0
        
        # Next publish should queue the message instead of calling delegate
        await resilient_publisher.publish("test.topic", test_event)
        
        # Message should be queued
        assert resilient_publisher.get_fallback_queue_size() == initial_queue_size + 1
    
    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_fallback_queue_essay_events(mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker, test_event: EventEnvelope[EssayStateChangeData]) -> None:
    """Test fallback queue specifically for essay lifecycle events."""
    # Create fresh publisher with empty queue
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )
    
    # Clear any existing queue state
    await resilient_publisher.fallback_handler.clear_queue()
    assert resilient_publisher.get_fallback_queue_size() == 0
    
    try:
        mock_kafka_bus.publish.side_effect = KafkaError("Kafka unavailable")
        
        # Open circuit by causing failures
        for _ in range(circuit_breaker.failure_threshold):
            try:
                await resilient_publisher.publish("test.topic", test_event)
            except KafkaError:
                pass
        
        # Ensure circuit is open
        assert circuit_breaker.state.value == "open"
        
        # Clear queue before testing essay events to ensure clean state
        await resilient_publisher.fallback_handler.clear_queue()
        
        # Test different essay lifecycle events are queued
        essay_events = [
            ("huleedu.essay.state.changed", "essay_123"),
            ("huleedu.essay.spellcheck.completed", "essay_456"),
            ("huleedu.essay.cj_assessment.completed", "essay_789"),
        ]
        
        for topic, key in essay_events:
            await resilient_publisher.publish(topic, test_event, key)
        
        # All events should be queued
        assert resilient_publisher.get_fallback_queue_size() == len(essay_events)
    
    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_recovery_after_kafka_returns(mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker, test_event: EventEnvelope[EssayStateChangeData]) -> None:
    """Test recovery when Kafka becomes available again."""
    # Create fresh publisher with empty queue
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )
    
    # Clear any existing queue state
    await resilient_publisher.fallback_handler.clear_queue()
    assert resilient_publisher.get_fallback_queue_size() == 0
    
    try:
        # Initially fail
        mock_kafka_bus.publish.side_effect = KafkaError("Connection failed")
        
        # Open circuit
        for _ in range(circuit_breaker.failure_threshold):
            try:
                await resilient_publisher.publish("test.topic", test_event)
            except KafkaError:
                pass
        
        assert circuit_breaker.state.value == "open"
        
        # Clear queue to ensure clean state, then queue exactly one message
        await resilient_publisher.fallback_handler.clear_queue()
        await resilient_publisher.publish("test.topic", test_event)
        assert resilient_publisher.get_fallback_queue_size() == 1
        
        # Simulate Kafka recovery
        mock_kafka_bus.publish.side_effect = None  # Remove the exception
        
        # Wait for circuit to transition to half-open (short timeout for testing)
        await asyncio.sleep(1.1)  # Slightly longer than recovery timeout
        
        # Manually process queued messages to simulate recovery loop
        await resilient_publisher._process_queued_messages()
        
        # Queue should be empty after successful processing
        assert resilient_publisher.get_fallback_queue_size() == 0
    
    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_without_circuit_breaker(mock_kafka_bus: AsyncMock, test_event: EventEnvelope[EssayStateChangeData]) -> None:
    """Test resilient publisher without circuit breaker (passthrough mode)."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=None,  # No circuit breaker
    )
    
    try:
        # Should delegate directly
        await resilient_publisher.publish("test.topic", test_event, "test_key")
        
        mock_kafka_bus.publish.assert_called_once_with("test.topic", test_event, "test_key")
        
        # Circuit breaker state should show disabled
        state = resilient_publisher.get_circuit_breaker_state()
        assert state["enabled"] is False
    finally:
        # Cleanup fallback handler even when no circuit breaker
        await resilient_publisher.fallback_handler.clear_queue()


@pytest.mark.asyncio
async def test_essay_lifecycle_specific_topics() -> None:
    """Test that common Essay Lifecycle Service topics work correctly."""
    mock_kafka_bus = AsyncMock(spec=KafkaBus)
    mock_kafka_bus.client_id = "essay-lifecycle-producer"
    
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=None,  # Test without circuit breaker first
    )
    
    try:
        # Common Essay Lifecycle Service topics
        topics = [
            "huleedu.essay.state.changed.v1",
            "huleedu.essay.spellcheck.initiated.v1", 
            "huleedu.essay.cj_assessment.initiated.v1",
            "huleedu.essay.batch.phase.completed.v1",
            "huleedu.essay.processing.error.v1",
        ]
        
        test_event = EventEnvelope[EssayStateChangeData](
            event_id=uuid4(),
            event_type="test.event.v1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="essay-lifecycle-service",
            data=EssayStateChangeData(
                essay_id="essay_test",
                previous_state="init",
                new_state="processing",
                batch_id="batch_test",
                timestamp=datetime.now(timezone.utc)
            )
        )
        
        # Test publishing to all common topics
        for topic in topics:
            await resilient_publisher.publish(topic, test_event, "test_key")
        
        # All topics should have been published
        assert mock_kafka_bus.publish.call_count == len(topics)
    
    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()


@pytest.mark.asyncio
async def test_lifecycle_management(mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker) -> None:
    """Test proper startup and shutdown lifecycle."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )
    
    try:
        # Test start
        await resilient_publisher.start()
        mock_kafka_bus.start.assert_called_once()
        
        # Test stop
        await resilient_publisher.stop()
        mock_kafka_bus.stop.assert_called_once()
    
    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


def test_client_id_and_servers_properties(mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker) -> None:
    """Test that client_id and bootstrap_servers are properly exposed."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )
    
    assert resilient_publisher.client_id == "essay-lifecycle-test-producer"
    assert resilient_publisher.bootstrap_servers == "localhost:9092"