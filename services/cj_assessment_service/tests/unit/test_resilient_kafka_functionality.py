"""
Unit tests for CJ Assessment Service resilient Kafka functionality.

These tests verify the circuit breaker behavior specifically for the
CJ Assessment Service use cases and publishing patterns.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka.errors import KafkaError
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker
from pydantic import BaseModel

from common_core import CircuitBreakerState
from common_core.events.envelope import EventEnvelope


class CJAssessmentResultData(BaseModel):
    """Test data model for CJ assessment result events."""

    batch_id: str
    essay_ids: list[str]
    assessments_completed: int
    assessment_type: str
    provider: str
    processing_time_ms: int
    timestamp: datetime
    model: str | None = None
    llm_cost_usd: float | None = None


class SimpleTestData(BaseModel):
    """Simple test data for basic circuit breaker tests."""

    test: str


@pytest.fixture
def mock_kafka_bus() -> AsyncMock:
    """Mock KafkaBus for testing."""
    mock_bus = AsyncMock(spec=KafkaBus)
    mock_bus.client_id = "cj_assessment_producer-test"
    mock_bus.bootstrap_servers = "localhost:9092"
    return mock_bus


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Circuit breaker configured for CJ Assessment Service."""
    return CircuitBreaker(
        name="cj_assessment_service.kafka_producer",
        failure_threshold=3,
        recovery_timeout=timedelta(seconds=1),  # Short for testing
        success_threshold=2,
        expected_exception=KafkaError,
    )


@pytest.fixture
def test_event() -> EventEnvelope[CJAssessmentResultData]:
    """Test event envelope for CJ assessment completion events."""
    return EventEnvelope[CJAssessmentResultData](
        event_id=uuid4(),
        event_type="huleedu.cj_assessment.completed.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="cj_assessment_service",
        correlation_id=uuid4(),
        data=CJAssessmentResultData(
            batch_id="batch_123",
            essay_ids=["essay_456", "essay_789"],
            assessments_completed=2,
            assessment_type="comparative_judgment",
            provider="openai",
            processing_time_ms=1500,
            timestamp=datetime.now(timezone.utc),
        ),
    )


@pytest.mark.asyncio
async def test_normal_publishing_flow(
    mock_kafka_bus: AsyncMock,
    circuit_breaker: CircuitBreaker,
    test_event: EventEnvelope[CJAssessmentResultData],
) -> None:
    """Test normal Kafka publishing through circuit breaker."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    try:
        # Test successful publishing
        await resilient_publisher.publish(
            "huleedu.cj_assessment.completed", test_event, "batch_123"
        )

        # Verify delegate was called
        mock_kafka_bus.publish.assert_called_once_with(
            "huleedu.cj_assessment.completed", test_event, "batch_123"
        )
    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_circuit_breaker_opens_on_failures(
    mock_kafka_bus: AsyncMock,
    circuit_breaker: CircuitBreaker,
    test_event: EventEnvelope[CJAssessmentResultData],
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
        assert circuit_breaker.state.value == CircuitBreakerState.OPEN.value

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
async def test_fallback_queue_cj_assessment_events(
    mock_kafka_bus: AsyncMock,
    circuit_breaker: CircuitBreaker,
    test_event: EventEnvelope[CJAssessmentResultData],
) -> None:
    """Test fallback queue specifically for CJ assessment events."""
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
        assert circuit_breaker.state.value == CircuitBreakerState.OPEN.value

        # Clear queue before testing CJ assessment events to ensure clean state
        await resilient_publisher.fallback_handler.clear_queue()

        # Test different CJ assessment events are queued
        cj_events = [
            ("huleedu.cj_assessment.completed", "batch_123"),
            ("huleedu.cj_assessment.failed", "batch_456"),
            ("huleedu.cj_assessment.requested", "batch_789"),
            ("huleedu.cj_assessment.progress", "batch_101"),
        ]

        for topic, key in cj_events:
            await resilient_publisher.publish(topic, test_event, key)

        # All events should be queued
        assert resilient_publisher.get_fallback_queue_size() == len(cj_events)

    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()


@pytest.mark.asyncio
async def test_recovery_after_kafka_returns(
    mock_kafka_bus: AsyncMock,
    circuit_breaker: CircuitBreaker,
    test_event: EventEnvelope[CJAssessmentResultData],
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

        assert circuit_breaker.state.value == CircuitBreakerState.OPEN.value

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
    mock_kafka_bus: AsyncMock, test_event: EventEnvelope[CJAssessmentResultData]
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
async def test_cj_assessment_specific_topics() -> None:
    """Test that common CJ Assessment Service topics work correctly."""
    mock_kafka_bus = AsyncMock(spec=KafkaBus)
    mock_kafka_bus.client_id = "cj_assessment_producer"

    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=None,  # Test without circuit breaker first
    )

    try:
        # Common CJ Assessment Service topics
        topics = [
            "huleedu.cj_assessment.completed.v1",
            "huleedu.cj_assessment.failed.v1",
            "huleedu.cj_assessment.requested.v1",
            "huleedu.cj_assessment.progress.v1",
            "huleedu.batch.cj_assessment.phase.completed.v1",
        ]

        test_event = EventEnvelope[CJAssessmentResultData](
            event_id=uuid4(),
            event_type="test.event.v1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="cj_assessment_service",
            data=CJAssessmentResultData(
                batch_id="batch_test",
                essay_ids=["essay_test1", "essay_test2"],
                assessments_completed=2,
                assessment_type="comparative_judgment",
                provider="anthropic",
                processing_time_ms=2000,
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

    assert resilient_publisher.client_id == "cj_assessment_producer-test"
    assert resilient_publisher.bootstrap_servers == "localhost:9092"


@pytest.mark.asyncio
async def test_expensive_llm_result_protection(
    mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker
) -> None:
    """Test protection of expensive LLM assessment results during outages."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    try:
        # Simulate expensive assessment result (took 5 seconds to compute)
        expensive_assessment = EventEnvelope[CJAssessmentResultData](
            event_type="huleedu.cj_assessment.completed.v1",
            event_timestamp=datetime.now(timezone.utc),
            source_service="cj_assessment_service",
            correlation_id=uuid4(),
            data=CJAssessmentResultData(
                batch_id="expensive-batch-123",
                essay_ids=["essay_a", "essay_b", "essay_c", "essay_d"],
                assessments_completed=6,  # 4 choose 2 comparisons
                assessment_type="comparative_judgment",
                provider="openai",
                model="gpt-4",
                processing_time_ms=5000,  # Expensive!
                llm_cost_usd=0.12,  # Cost money
                timestamp=datetime.now(timezone.utc),
            ),
        )

        topic = "huleedu.cj_assessment.completed.v1"

        # Mock Kafka outage during result publishing
        mock_kafka_bus.publish.side_effect = KafkaError("Kafka cluster unreachable")

        # Should handle error gracefully and not lose expensive result
        try:
            await resilient_publisher.publish(topic, expensive_assessment, "expensive-batch-123")
        except KafkaError:
            pass  # Expected during circuit breaker testing

        # Verify expensive result was queued for retry (not lost!)
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
        assert state["state"] == CircuitBreakerState.CLOSED.value
        assert state["name"] == "cj_assessment_service.kafka_producer"
        assert state["failure_count"] == 0

        # Force some failures
        mock_kafka_bus.publish.side_effect = KafkaError("Test failure")

        sample_event = EventEnvelope[SimpleTestData](
            event_type="test.event",
            event_timestamp=datetime.now(timezone.utc),
            source_service="cj_assessment_service",
            correlation_id=uuid4(),
            data=SimpleTestData(test="data"),
        )

        # Cause failures
        for _ in range(3):
            try:
                await resilient_publisher.publish("test.topic", sample_event)
            except KafkaError:
                pass  # Expected during circuit breaker testing

        # Check updated state
        state = resilient_publisher.get_circuit_breaker_state()
        assert state["state"] == CircuitBreakerState.OPEN.value
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


@pytest.mark.asyncio
async def test_multi_provider_assessment_scenarios(
    mock_kafka_bus: AsyncMock, circuit_breaker: CircuitBreaker
) -> None:
    """Test CJ Assessment Service specific scenarios with multiple LLM providers."""
    resilient_publisher = ResilientKafkaPublisher(
        delegate=mock_kafka_bus,
        circuit_breaker=circuit_breaker,
    )

    try:
        # Test different provider results during Kafka issues
        provider_results = [
            ("openai", "gpt-4o-mini", 750),
            ("anthropic", "claude-3-haiku", 1200),
            ("google", "gemini-1.5-flash", 600),
            ("openrouter", "anthropic/claude-3-haiku", 850),
        ]

        mock_kafka_bus.publish.side_effect = KafkaError("Intermittent network issues")

        for provider, model, time_ms in provider_results:
            assessment_event = EventEnvelope[CJAssessmentResultData](
                event_type="huleedu.cj_assessment.completed.v1",
                event_timestamp=datetime.now(timezone.utc),
                source_service="cj_assessment_service",
                correlation_id=uuid4(),
                data=CJAssessmentResultData(
                    batch_id=f"batch_{provider}",
                    provider=provider,
                    model=model,
                    processing_time_ms=time_ms,
                    assessments_completed=3,
                    essay_ids=["essay1", "essay2", "essay3"],
                    assessment_type="comparative_judgment",
                    timestamp=datetime.now(timezone.utc),
                ),
            )

            try:
                await resilient_publisher.publish(
                    "huleedu.cj_assessment.completed.v1", assessment_event, f"batch_{provider}"
                )
            except KafkaError:
                pass  # Expected during circuit breaker testing

        # All provider results should be safely queued
        assert resilient_publisher.get_fallback_queue_size() == len(provider_results)

    finally:
        # Cleanup
        await resilient_publisher.fallback_handler.clear_queue()
        circuit_breaker.reset()
