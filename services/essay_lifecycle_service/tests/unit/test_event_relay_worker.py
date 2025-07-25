"""
Unit tests for EventRelayWorker - Rewritten to test actual behavior.

Tests the event relay worker that polls the outbox and publishes to Kafka:
- Verifies actual data transformations
- Tests real EventEnvelope creation
- Validates topic resolution logic
- Confirms error handling behavior
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from common_core.events.envelope import EventEnvelope

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.event_relay_worker import EventRelayWorker
from services.essay_lifecycle_service.protocols import OutboxEvent

UTC = UTC


@dataclass
class MockOutboxEvent:
    """Test implementation of OutboxEvent protocol."""

    id: UUID
    aggregate_id: str
    aggregate_type: str
    event_type: str
    event_data: dict[str, Any]
    event_key: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None
    retry_count: int = 0
    last_error: str | None = None


class MockKafkaPublisher:
    """Test implementation of KafkaPublisherProtocol that captures published events."""

    def __init__(self) -> None:
        self.published_events: list[tuple[str, EventEnvelope[Any]]] = []
        self.publish_error: Exception | None = None
        self.call_count = 0

    async def publish(self, topic: str, envelope: EventEnvelope[Any]) -> None:
        """Capture published events for verification."""
        self.call_count += 1
        if self.publish_error:
            raise self.publish_error
        self.published_events.append((topic, envelope))


class MockOutboxRepository:
    """Test implementation of OutboxRepositoryProtocol."""

    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []
        self.published_event_ids: set[UUID] = set()
        self.failed_event_ids: dict[UUID, str] = {}
        self.retry_counts: dict[UUID, tuple[int, str]] = {}

    async def get_unpublished_events(self, limit: int = 100) -> list[OutboxEvent]:
        """Return unpublished events."""
        unpublished = [e for e in self.events if e.id not in self.published_event_ids]
        return unpublished[:limit]

    async def mark_event_published(self, event_id: UUID) -> None:
        """Mark event as published."""
        self.published_event_ids.add(event_id)
        # Update the actual event object
        for event in self.events:
            if event.id == event_id:
                event.published_at = datetime.now(UTC)

    async def mark_event_failed(self, event_id: UUID, error: str) -> None:
        """Mark event as permanently failed."""
        self.failed_event_ids[event_id] = error

    async def increment_retry_count(self, event_id: UUID, error: str) -> None:
        """Increment retry count and record error."""
        # Find the event and increment its retry count
        for event in self.events:
            if event.id == event_id:
                event.retry_count += 1
                event.last_error = error
                self.retry_counts[event_id] = (event.retry_count, error)
                break


class TestEventRelayWorker:
    """Unit tests for EventRelayWorker focusing on behavior."""

    @pytest.fixture
    def kafka_publisher(self) -> MockKafkaPublisher:
        """Create test Kafka publisher."""
        return MockKafkaPublisher()

    @pytest.fixture
    def outbox_repository(self) -> MockOutboxRepository:
        """Create test outbox repository."""
        return MockOutboxRepository()

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings with real Settings object."""
        # Create minimal settings for testing
        return Settings(
            DB_URI="postgresql://test",
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            REDIS_URL="redis://localhost",
            # Outbox specific settings
            OUTBOX_POLL_INTERVAL_SECONDS=0.1,
            OUTBOX_BATCH_SIZE=10,
            OUTBOX_MAX_RETRIES=3,
            OUTBOX_ERROR_RETRY_INTERVAL_SECONDS=0.1,
        )

    @pytest.fixture
    def worker(
        self,
        kafka_publisher: MockKafkaPublisher,
        outbox_repository: MockOutboxRepository,
        settings: Settings,
    ) -> EventRelayWorker:
        """Create EventRelayWorker instance with test dependencies."""
        return EventRelayWorker(
            kafka_bus=kafka_publisher,  # type: ignore
            outbox_repository=outbox_repository,  # type: ignore
            settings=settings,
        )

    async def test_process_event_success_with_envelope_creation(
        self,
        worker: EventRelayWorker,
        kafka_publisher: MockKafkaPublisher,
        outbox_repository: MockOutboxRepository,
    ) -> None:
        """Test successful event processing verifies actual EventEnvelope creation."""
        # Arrange
        event_id = uuid4()
        aggregate_id = str(uuid4())
        test_data = {"status": "completed", "score": 95}

        event = MockOutboxEvent(
            id=event_id,
            aggregate_id=aggregate_id,
            aggregate_type="essay",
            event_type="essay.status.updated.v1",
            event_data={
                "correlation_id": str(uuid4()),
                "data": test_data,
                "topic": "essay.status.events",
                "extra_field": "should_remain",
            },
            event_key=aggregate_id,
            retry_count=0,
        )

        # Act
        await worker._process_event(event)

        # Assert - Verify the actual EventEnvelope created
        assert len(kafka_publisher.published_events) == 1
        topic, envelope = kafka_publisher.published_events[0]

        # Verify topic extraction
        assert topic == "essay.status.events"

        # Verify EventEnvelope fields
        assert envelope.event_type == "essay.status.updated.v1"
        assert envelope.source_service == "essay-lifecycle-service"
        # EventEnvelope converts correlation_id to UUID
        assert str(envelope.correlation_id) == event.event_data["correlation_id"]
        assert envelope.data == test_data  # Should extract data field

        # Verify event was marked as published
        assert event_id in outbox_repository.published_event_ids

    async def test_process_event_topic_fallback_mechanism(
        self,
        worker: EventRelayWorker,
        kafka_publisher: MockKafkaPublisher,
        outbox_repository: MockOutboxRepository,
    ) -> None:
        """Test topic resolution falls back to event type mapping when topic not in data."""
        # Arrange
        event_id = uuid4()
        correlation_id = str(uuid4())

        event = MockOutboxEvent(
            id=event_id,
            aggregate_id=str(uuid4()),
            aggregate_type="batch",
            event_type="huleedu.els.batch_phase.progress.v1",
            event_data={
                "correlation_id": correlation_id,
                "data": {"phase": "processing", "progress": 50},
                # No 'topic' field - should trigger fallback
            },
            retry_count=0,
        )

        # Act
        await worker._process_event(event)

        # Assert
        assert len(kafka_publisher.published_events) == 1
        topic, envelope = kafka_publisher.published_events[0]

        # Should use fallback topic from _get_topic_for_event_type
        assert topic == "batch.phase.progress.events"

        # Verify envelope still created correctly
        assert envelope.event_type == "huleedu.els.batch_phase.progress.v1"
        assert str(envelope.correlation_id) == correlation_id
        assert envelope.data == {"phase": "processing", "progress": 50}

    async def test_process_event_correlation_id_fallback(
        self,
        worker: EventRelayWorker,
        kafka_publisher: MockKafkaPublisher,
    ) -> None:
        """Test correlation_id falls back to event.id when not provided."""
        # Arrange
        event_id = uuid4()

        event = MockOutboxEvent(
            id=event_id,
            aggregate_id=str(uuid4()),
            aggregate_type="essay",
            event_type="essay.status.updated.v1",
            event_data={
                # No correlation_id - should use event.id
                "data": {"status": "draft"},
                "topic": "essay.status.events",
            },
            retry_count=0,
        )

        # Act
        await worker._process_event(event)

        # Assert
        assert len(kafka_publisher.published_events) == 1
        _, envelope = kafka_publisher.published_events[0]

        # Should use event.id as correlation_id (both are UUID)
        assert envelope.correlation_id == event_id

    async def test_process_event_kafka_failure_increments_retry(
        self,
        worker: EventRelayWorker,
        kafka_publisher: MockKafkaPublisher,
        outbox_repository: MockOutboxRepository,
    ) -> None:
        """Test that Kafka publish failures properly increment retry count."""
        # Arrange
        event_id = uuid4()
        initial_retry_count = 1

        event = MockOutboxEvent(
            id=event_id,
            aggregate_id=str(uuid4()),
            aggregate_type="essay",
            event_type="essay.status.updated.v1",
            event_data={
                "data": {"status": "completed"},
                "topic": "essay.status.events",
            },
            retry_count=initial_retry_count,
        )
        outbox_repository.events.append(event)

        # Configure Kafka to fail
        kafka_error = ConnectionError("Kafka broker unavailable")
        kafka_publisher.publish_error = kafka_error

        # Act
        await worker._process_event(event)

        # Assert
        # Should not be marked as published
        assert event_id not in outbox_repository.published_event_ids

        # Should increment retry count
        assert event_id in outbox_repository.retry_counts
        new_count, error_msg = outbox_repository.retry_counts[event_id]
        assert new_count == initial_retry_count + 1
        assert "Kafka broker unavailable" in error_msg
        assert "Failed to publish event to Kafka" in error_msg

        # Event object should be updated
        assert event.retry_count == initial_retry_count + 1
        assert event.last_error == error_msg

        # Should not be marked as permanently failed (still has retries left)
        assert event_id not in outbox_repository.failed_event_ids

    async def test_process_event_max_retries_marks_failed(
        self,
        worker: EventRelayWorker,
        kafka_publisher: MockKafkaPublisher,
        outbox_repository: MockOutboxRepository,
        settings: Settings,
    ) -> None:
        """Test that events exceeding max retries are marked as permanently failed."""
        # Arrange
        event_id = uuid4()

        event = MockOutboxEvent(
            id=event_id,
            aggregate_id=str(uuid4()),
            aggregate_type="essay",
            event_type="essay.status.updated.v1",
            event_data={
                "data": {"status": "completed"},
                "topic": "essay.status.events",
            },
            retry_count=settings.OUTBOX_MAX_RETRIES,  # Already at max
            last_error="Previous Kafka error",
        )

        # Act
        await worker._process_event(event)

        # Assert
        # Should not attempt to publish
        assert kafka_publisher.call_count == 0

        # Should be marked as permanently failed
        assert event_id in outbox_repository.failed_event_ids
        error_msg = outbox_repository.failed_event_ids[event_id]
        assert f"Exceeded max retries ({settings.OUTBOX_MAX_RETRIES})" in error_msg

        # Should not increment retry count further
        assert event_id not in outbox_repository.retry_counts

        # Should not be marked as published
        assert event_id not in outbox_repository.published_event_ids

    async def test_polling_processes_batch_correctly(
        self,
        worker: EventRelayWorker,
        kafka_publisher: MockKafkaPublisher,
        outbox_repository: MockOutboxRepository,
        settings: Settings,
    ) -> None:
        """Test that polling processes a batch of events correctly."""
        # Arrange
        events = []
        for i in range(3):
            event = MockOutboxEvent(
                id=uuid4(),
                aggregate_id=str(uuid4()),
                aggregate_type="essay",
                event_type="essay.status.updated.v1",
                event_data={
                    "correlation_id": str(uuid4()),
                    "data": {"index": i, "status": f"status_{i}"},
                    "topic": f"topic.{i}",
                },
                retry_count=0,
            )
            events.append(event)
            outbox_repository.events.append(event)

        # Act - Run one polling cycle
        worker._running = True
        poll_task = asyncio.create_task(worker._run())

        # Wait for processing
        await asyncio.sleep(0.05)

        # Stop the worker
        worker._running = False
        try:
            await asyncio.wait_for(poll_task, timeout=0.2)
        except (TimeoutError, asyncio.CancelledError):
            pass

        # Assert
        # All events should be published
        assert len(kafka_publisher.published_events) == 3

        # Verify each event was published correctly
        for i, (topic, envelope) in enumerate(kafka_publisher.published_events):
            # Find corresponding event
            matching_event = next(e for e in events if e.event_data["data"]["index"] == i)

            assert topic == f"topic.{i}"
            assert envelope.event_type == "essay.status.updated.v1"
            assert envelope.data == {"index": i, "status": f"status_{i}"}
            assert str(envelope.correlation_id) == matching_event.event_data["correlation_id"]

            # Event should be marked as published
            assert matching_event.id in outbox_repository.published_event_ids

    async def test_envelope_data_extraction_without_data_field(
        self,
        worker: EventRelayWorker,
        kafka_publisher: MockKafkaPublisher,
    ) -> None:
        """Test that envelope uses entire event_data when 'data' field is missing."""
        # Arrange
        event_id = uuid4()

        # Event data without a 'data' field
        event_data_content = {
            "correlation_id": str(uuid4()),
            "topic": "essay.status.events",
            "status": "completed",
            "score": 95,
            "metadata": {"reviewer": "system"},
        }

        event = MockOutboxEvent(
            id=event_id,
            aggregate_id=str(uuid4()),
            aggregate_type="essay",
            event_type="essay.status.updated.v1",
            event_data=event_data_content,
            retry_count=0,
        )

        # Act
        await worker._process_event(event)

        # Assert
        assert len(kafka_publisher.published_events) == 1
        _, envelope = kafka_publisher.published_events[0]

        # Should use entire event_data (minus 'topic') as data
        expected_data = {
            "correlation_id": event_data_content["correlation_id"],
            "status": "completed",
            "score": 95,
            "metadata": {"reviewer": "system"},
        }
        assert envelope.data == expected_data

    async def test_worker_lifecycle_start_stop(
        self,
        worker: EventRelayWorker,
        outbox_repository: MockOutboxRepository,
    ) -> None:
        """Test worker start and stop lifecycle management."""
        # Initially not running
        assert worker._running is False
        assert worker._task is None

        # Start the worker
        await worker.start()
        assert worker._running is True
        assert worker._task is not None
        assert not worker._task.done()

        # Repository should return empty list to prevent processing
        outbox_repository.events = []

        # Let it run briefly
        await asyncio.sleep(0.15)

        # Verify it's still running
        assert worker._running is True
        assert not worker._task.done()

        # Stop the worker
        await worker.stop()

        # Verify stopped state
        assert worker._running is False
        assert worker._task is None

    async def test_worker_handles_exception_in_polling_loop(
        self,
        worker: EventRelayWorker,
        outbox_repository: MockOutboxRepository,
        settings: Settings,
    ) -> None:
        """Test that worker continues running after exceptions in the polling loop."""
        # Arrange
        # Make get_unpublished_events fail once, then return empty
        call_count = 0

        async def failing_get_unpublished_events(limit: int = 100) -> list[OutboxEvent]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Database connection lost")
            return []

        # Type: ignore needed for monkey patching
        outbox_repository.get_unpublished_events = failing_get_unpublished_events  # type: ignore[method-assign]

        # Act
        worker._running = True
        poll_task = asyncio.create_task(worker._run())

        # Wait for error and recovery
        await asyncio.sleep(settings.OUTBOX_ERROR_RETRY_INTERVAL_SECONDS + 0.1)

        # Stop the worker
        worker._running = False
        try:
            await asyncio.wait_for(poll_task, timeout=0.2)
        except (TimeoutError, asyncio.CancelledError):
            pass

        # Assert
        # Should have called get_unpublished_events at least twice (error + recovery)
        assert call_count >= 2

    async def test_polling_with_mixed_success_and_failures(
        self,
        worker: EventRelayWorker,
        kafka_publisher: MockKafkaPublisher,
        outbox_repository: MockOutboxRepository,
    ) -> None:
        """Test that batch processing continues when some events fail."""
        # Arrange
        events = []
        for i in range(3):
            event = MockOutboxEvent(
                id=uuid4(),
                aggregate_id=str(uuid4()),
                aggregate_type="essay",
                event_type="essay.status.updated.v1",
                event_data={
                    "correlation_id": str(uuid4()),
                    "data": {"index": i},
                    "topic": f"topic.{i}",
                },
                retry_count=0,
            )
            events.append(event)
            outbox_repository.events.append(event)

        # Make the second event fail to publish
        original_publish = kafka_publisher.publish

        async def selective_fail_publish(topic: str, envelope: EventEnvelope[Any]) -> None:
            if envelope.data.get("index") == 1:  # Fail the second event
                raise ConnectionError("Kafka unavailable for event 1")
            await original_publish(topic, envelope)

        # Type: ignore needed for monkey patching
        kafka_publisher.publish = selective_fail_publish  # type: ignore[method-assign]

        # Act - Run one polling cycle
        worker._running = True
        poll_task = asyncio.create_task(worker._run())
        await asyncio.sleep(0.05)
        worker._running = False
        try:
            await asyncio.wait_for(poll_task, timeout=0.2)
        except (TimeoutError, asyncio.CancelledError):
            pass

        # Assert
        # First and third should succeed
        assert len(kafka_publisher.published_events) == 2
        published_indices = [e.data["index"] for _, e in kafka_publisher.published_events]
        assert 0 in published_indices
        assert 2 in published_indices
        assert 1 not in published_indices

        # First and third should be marked as published
        assert events[0].id in outbox_repository.published_event_ids
        assert events[2].id in outbox_repository.published_event_ids
        assert events[1].id not in outbox_repository.published_event_ids

        # Second event should have retry count incremented
        assert events[1].id in outbox_repository.retry_counts
        assert events[1].retry_count == 1
