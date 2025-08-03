"""
Unit tests for Spell Checker Service resilient Kafka functionality.

These tests verify the circuit breaker behavior specifically for the
Spell Checker Service use cases and publishing patterns.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka.errors import KafkaError
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from pydantic import BaseModel


class SpellCheckResultData(BaseModel):
    """Test data model for spellcheck result events."""

    essay_id: str
    batch_id: str
    corrected_text: str
    original_errors: int
    corrected_errors: int
    timestamp: datetime


class SimpleTestData(BaseModel):
    """Simple test data model for basic events."""

    test: str


@pytest.fixture
def mock_kafka_bus() -> AsyncMock:
    """Mock KafkaBus for testing."""
    mock_bus = AsyncMock(spec=KafkaBus)
    mock_bus.client_id = "spellchecker-service-test-producer"
    mock_bus.bootstrap_servers = "localhost:9092"
    return mock_bus


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Circuit breaker configured for Spell Checker Service."""
    return CircuitBreaker(
        name="spell-checker-service.kafka_producer",
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=1),  # Short for testing
        success_threshold=2,
        expected_exception=KafkaError,
    )


@pytest.fixture
def test_event() -> EventEnvelope[SpellCheckResultData]:
    """Test event envelope for spellcheck completion events."""
    return EventEnvelope[SpellCheckResultData](
        event_id=uuid4(),
        event_type=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        event_timestamp=datetime.now(timezone.utc),
        source_service="spell-checker-service",
        correlation_id=uuid4(),
        data=SpellCheckResultData(
            essay_id="essay_123",
            batch_id="batch_456",
            corrected_text="This is a corrected essay.",
            original_errors=5,
            corrected_errors=5,
            timestamp=datetime.now(timezone.utc),
        ),
    )


@pytest.mark.asyncio
async def test_normal_publishing_flow(
    mock_kafka_bus: AsyncMock,
    circuit_breaker: CircuitBreaker,
    test_event: EventEnvelope[SpellCheckResultData],
) -> None:
    """Test normal Kafka publishing through circuit breaker."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    try:
        # Test successful publishing
        await resilient_publisher.publish(
            "huleedu.essay.spellcheck.completed", test_event, "essay_123"
        )

        # Verify delegate was called
        mock_kafka_bus.publish.assert_called_once_with(
            "huleedu.essay.spellcheck.completed", test_event, "essay_123"
        )
    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures(
    mock_kafka_bus: AsyncMock,
    circuit_breaker: CircuitBreaker,
    test_event: EventEnvelope[SpellCheckResultData],
) -> None:
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
        for _ in range(circuit_breaker.failure_threshold):
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
async def test_fallback_queue_spellcheck_events(
    mock_kafka_bus: AsyncMock,
    circuit_breaker: CircuitBreaker,
    test_event: EventEnvelope[SpellCheckResultData],
) -> None:
    """Test fallback queue specifically for spellcheck events."""
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

        # Clear queue before testing spellcheck events to ensure clean state
        await resilient_publisher.fallback_handler.clear_queue()

        # Test different spellcheck events are queued
        spellcheck_events = [
            ("huleedu.essay.spellcheck.completed", "essay_123"),
            ("huleedu.essay.spellcheck.initiated", "essay_456"),
            ("huleedu.batch.spellcheck.phase.completed", "batch_789"),
        ]

        for topic, key in spellcheck_events:
            await resilient_publisher.publish(topic, test_event, key)

        # All events should be queued
        assert resilient_publisher.get_fallback_queue_size() == len(spellcheck_events)

    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_recovery_after_kafka_returns(
    mock_kafka_bus: AsyncMock,
    circuit_breaker: CircuitBreaker,
    test_event: EventEnvelope[SpellCheckResultData],
) -> None:
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
async def test_without_circuit_breaker(
    mock_kafka_bus: AsyncMock, test_event: EventEnvelope[SpellCheckResultData]
) -> None:
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
async def test_spellcheck_specific_topics() -> None:
    """Test that common Spell Checker Service topics work correctly."""
    mock_kafka_bus = AsyncMock(spec=KafkaBus)
    mock_kafka_bus.client_id = "spellchecker-producer"

    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=None,  # Test without circuit breaker first
    )

    try:
        # Common Spell Checker Service topics
        topics = [
            topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            "huleedu.essay.spellcheck.initiated.v1",
            "huleedu.batch.spellcheck.phase.completed.v1",
            "huleedu.spellcheck.processing.error.v1",
            "huleedu.spellcheck.result.stored.v1",
        ]

        test_event = EventEnvelope[SpellCheckResultData](
            event_id=uuid4(),
            event_type="test.event.v1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="spell-checker-service",
            data=SpellCheckResultData(
                essay_id="essay_test",
                batch_id="batch_test",
                corrected_text="Test corrected text",
                original_errors=3,
                corrected_errors=3,
                timestamp=datetime.now(timezone.utc),
            ),
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
async def test_lifecycle_management(
    mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker
) -> None:
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


def test_client_id_and_servers_properties(
    mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker
) -> None:
    """Test that client_id and bootstrap_servers are properly exposed."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    assert resilient_publisher.client_id == "spellchecker-service-test-producer"
    assert resilient_publisher.bootstrap_servers == "localhost:9092"


@pytest.mark.asyncio
async def test_spellcheck_specific_error_scenarios(
    mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker
) -> None:
    """Test Spell Checker Service specific error scenarios."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    try:
        # Test large spellcheck result event
        large_spellcheck_data = SpellCheckResultData(
            essay_id="large-essay-123",
            batch_id="batch-456",
            corrected_text="A" * 50000,  # Large corrected text
            original_errors=1000,
            corrected_errors=950,
            timestamp=datetime.now(timezone.utc),
        )

        large_spellcheck_event = EventEnvelope[SpellCheckResultData](
            event_type=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
            event_timestamp=datetime.now(timezone.utc),
            source_service="spell-checker-service",
            correlation_id=uuid4(),
            data=large_spellcheck_data,
        )

        topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED)

        # Mock Kafka timeout (common with large messages)
        mock_kafka_bus.publish.side_effect = KafkaError("Message too large")

        # Should handle error gracefully
        try:
            await resilient_publisher.publish(topic, large_spellcheck_event)
        except KafkaError:
            pass  # Expected during circuit breaker testing

        # Verify event was queued for retry
        assert resilient_publisher.get_fallback_queue_size() == 1

    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_circuit_breaker_state_reporting(
    mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker
) -> None:
    """Test circuit breaker state reporting functionality."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    try:
        # Initially closed
        state = resilient_publisher.get_circuit_breaker_state()
        assert state["enabled"] is True
        assert state["state"] == "closed"
        assert state["name"] == "spell-checker-service.kafka_producer"
        assert state["failure_count"] == 0

        # Force some failures
        mock_kafka_bus.publish.side_effect = KafkaError("Test failure")

        test_data = SimpleTestData(test="data")
        sample_event = EventEnvelope[SimpleTestData](
            event_type="test.event",
            event_timestamp=datetime.now(timezone.utc),
            source_service="spell-checker-service",
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

    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_resource_cleanup(mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker) -> None:
    """Test proper resource cleanup."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    try:
        # Verify start/stop delegation
        await resilient_publisher.start()
        mock_kafka_bus.start.assert_called_once()

        await resilient_publisher.stop()
        mock_kafka_bus.stop.assert_called_once()

    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()
