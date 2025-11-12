"""
Unit tests for EventRelayWorker from the shared outbox pattern library.

Tests focus on behavior verification with minimal mocking of external dependencies,
following the proven File Service test patterns.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.outbox import EventRelayWorker
from huleedu_service_libs.outbox.monitoring import OutboxMetrics
from huleedu_service_libs.outbox.protocols import OutboxEvent
from huleedu_service_libs.outbox.relay import OutboxSettings


class FakeOutboxEvent:
    """Test implementation of OutboxEvent protocol."""

    def __init__(
        self,
        id: UUID,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data: dict[str, Any],
        event_key: str | None,
        topic: str,
        created_at: datetime,
        published_at: datetime | None = None,
        retry_count: int = 0,
        last_error: str | None = None,
    ) -> None:
        self._id = id
        self._aggregate_id = aggregate_id
        self._aggregate_type = aggregate_type
        self._event_type = event_type
        self._event_data = event_data
        self._event_key = event_key
        self._topic = topic
        self._created_at = created_at
        self._published_at = published_at
        self._retry_count = retry_count
        self._last_error = last_error

    @property
    def id(self) -> UUID:
        return self._id

    @property
    def aggregate_id(self) -> str:
        return self._aggregate_id

    @property
    def aggregate_type(self) -> str:
        return self._aggregate_type

    @property
    def event_type(self) -> str:
        return self._event_type

    @property
    def event_data(self) -> dict[str, Any]:
        return self._event_data

    @property
    def event_key(self) -> str | None:
        return self._event_key

    @property
    def topic(self) -> str:
        return self._topic

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def published_at(self) -> datetime | None:
        return self._published_at

    @property
    def retry_count(self) -> int:
        return self._retry_count

    @property
    def last_error(self) -> str | None:
        return self._last_error


class FakeOutboxRepository:
    """Test implementation of OutboxRepositoryProtocol."""

    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []
        self.published_events: set[UUID] = set()
        self.failed_events: dict[UUID, str] = {}
        self.retry_counts: dict[UUID, tuple[int, str]] = {}
        self._next_id = 0

    async def add_event(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data: dict[str, Any],
        topic: str,
        event_key: str | None = None,
        session: Any = None,
    ) -> UUID:
        """Add a new event to the outbox."""
        event_id = uuid4()
        event = FakeOutboxEvent(
            id=event_id,
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            event_data=event_data,
            event_key=event_key,
            topic=event_data.get("topic", "processing.cj.assessment.v1"),
            created_at=datetime.now(timezone.utc),
            published_at=None,
            retry_count=0,
            last_error=None,
        )
        self.events.append(event)
        return event_id

    async def get_event_by_id(self, event_id: UUID) -> OutboxEvent | None:
        """Get an event by its ID."""
        return next((e for e in self.events if e.id == event_id), None)

    async def get_unpublished_events(self, limit: int = 100) -> list[OutboxEvent]:
        """Return unpublished events up to limit."""
        unpublished = [
            e
            for e in self.events
            if e.id not in self.published_events and e.id not in self.failed_events
        ]
        return unpublished[:limit]

    async def mark_event_published(self, event_id: UUID) -> None:
        """Mark event as published."""
        self.published_events.add(event_id)

    async def mark_event_failed(self, event_id: UUID, error: str) -> None:
        """Mark event as permanently failed."""
        self.failed_events[event_id] = error

    async def increment_retry_count(self, event_id: UUID, error: str) -> None:
        """Increment retry count and record error."""
        event = next((e for e in self.events if e.id == event_id), None)
        if event and isinstance(event, FakeOutboxEvent):
            # Update internal state rather than modifying read-only properties
            event._retry_count += 1
            event._last_error = error
            self.retry_counts[event_id] = (event._retry_count, error)


class FakeKafkaPublisher:
    """Test implementation of KafkaPublisherProtocol."""

    def __init__(self) -> None:
        self.published_messages: list[tuple[str, Any, str | None]] = []
        self.should_fail = False
        self.failure_message = "Kafka unavailable"

    async def publish(
        self,
        topic: str,
        envelope: Any,
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Simulate publishing to Kafka."""
        if self.should_fail:
            raise Exception(self.failure_message)
        self.published_messages.append((topic, envelope, key))

    async def start(self) -> None:
        """No-op for test."""
        pass

    async def stop(self) -> None:
        """No-op for test."""
        pass


@pytest.fixture
def fake_repository() -> FakeOutboxRepository:
    """Provide a fake repository for testing."""
    return FakeOutboxRepository()


@pytest.fixture
def fake_kafka() -> FakeKafkaPublisher:
    """Provide a fake Kafka publisher for testing."""
    return FakeKafkaPublisher()


@pytest.fixture
def test_settings() -> OutboxSettings:
    """Test settings with fast intervals."""
    return OutboxSettings(
        poll_interval_seconds=0.05,
        batch_size=10,
        max_retries=3,
        error_retry_interval_seconds=0.05,
        enable_metrics=False,  # Disable for most tests
    )


@pytest.fixture
def sample_event(
    fake_repository: FakeOutboxRepository,
) -> FakeOutboxEvent:
    """Create a sample event for testing."""
    event = FakeOutboxEvent(
        id=uuid4(),
        aggregate_id="test-aggregate-123",
        aggregate_type="cj_batch",
        event_type="processing.cj.assessment.completed.v1",
        event_data={
            "data": {"entity_id": "batch-123", "cj_assessment_job_id": "job-456"},
            "correlation_id": str(uuid4()),
            "source_service": "cj_assessment_service",
            "metadata": {"user_id": "user-123"},
        },
        event_key="test-aggregate-123",
        topic="processing.cj.assessment.completed.v1",
        created_at=datetime.now(timezone.utc),
        published_at=None,
        retry_count=0,
        last_error=None,
    )
    fake_repository.events.append(event)
    return event


class TestEventRelayWorker:
    """Test EventRelayWorker behavior using File Service patterns."""

    async def test_publishes_events_successfully(
        self,
        fake_repository: FakeOutboxRepository,
        fake_kafka: FakeKafkaPublisher,
        test_settings: OutboxSettings,
        sample_event: FakeOutboxEvent,
    ) -> None:
        """Verify events are published to Kafka with correct envelope structure."""
        # Given
        worker = EventRelayWorker(
            outbox_repository=fake_repository,
            kafka_bus=fake_kafka,
            settings=test_settings,
            service_name="cj_assessment_service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)  # Allow processing
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 1
        topic, envelope, key = fake_kafka.published_messages[0]

        assert topic == "processing.cj.assessment.completed.v1"
        assert key == "test-aggregate-123"
        assert envelope.event_type == "processing.cj.assessment.completed.v1"
        assert envelope.source_service == "cj_assessment_service"
        assert envelope.data == {"entity_id": "batch-123", "cj_assessment_job_id": "job-456"}
        assert envelope.metadata == {"user_id": "user-123"}

        assert sample_event.id in fake_repository.published_events

    async def test_handles_kafka_failures_with_retry(
        self,
        fake_repository: FakeOutboxRepository,
        fake_kafka: FakeKafkaPublisher,
        test_settings: OutboxSettings,
        sample_event: FakeOutboxEvent,
    ) -> None:
        """Verify retry mechanism when Kafka publish fails."""
        # Given
        fake_kafka.should_fail = True

        # Use longer poll interval to avoid multiple retries in test
        test_settings.poll_interval_seconds = 1.0

        worker = EventRelayWorker(
            outbox_repository=fake_repository,
            kafka_bus=fake_kafka,
            settings=test_settings,
            service_name="cj_assessment_service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)  # Just enough for one poll
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 0
        assert sample_event.id not in fake_repository.published_events
        assert sample_event.retry_count >= 1  # At least one retry
        assert sample_event.last_error is not None
        assert "Kafka unavailable" in sample_event.last_error

    async def test_marks_events_failed_after_max_retries(
        self,
        fake_repository: FakeOutboxRepository,
        fake_kafka: FakeKafkaPublisher,
        test_settings: OutboxSettings,
        sample_event: FakeOutboxEvent,
    ) -> None:
        """Verify events are marked failed after exceeding max retries."""
        # Given
        sample_event._retry_count = test_settings.max_retries
        worker = EventRelayWorker(
            outbox_repository=fake_repository,
            kafka_bus=fake_kafka,
            settings=test_settings,
            service_name="cj_assessment_service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 0
        assert sample_event.id in fake_repository.failed_events
        assert "Exceeded max retries" in fake_repository.failed_events[sample_event.id]

    async def test_processes_multiple_events_in_batch(
        self,
        fake_repository: FakeOutboxRepository,
        fake_kafka: FakeKafkaPublisher,
        test_settings: OutboxSettings,
    ) -> None:
        """Verify batch processing of multiple events."""
        # Given
        events = []
        for i in range(3):
            event = FakeOutboxEvent(
                id=uuid4(),
                aggregate_id=f"aggregate-{i}",
                aggregate_type="cj_batch",
                event_type="processing.cj.assessment.completed.v1",
                event_data={
                    "data": {"entity_id": f"batch-{i}"},
                },
                event_key=f"key-{i}",
                topic="processing.cj.assessment.completed.v1",
                created_at=datetime.now(timezone.utc),
                published_at=None,
                retry_count=0,
                last_error=None,
            )
            fake_repository.events.append(event)
            events.append(event)

        worker = EventRelayWorker(
            outbox_repository=fake_repository,
            kafka_bus=fake_kafka,
            settings=test_settings,
            service_name="cj_assessment_service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 3
        for i, (topic, envelope, key) in enumerate(fake_kafka.published_messages):
            assert topic == "processing.cj.assessment.completed.v1"
            assert key == f"key-{i}"
            assert envelope.data == {"entity_id": f"batch-{i}"}
            assert events[i].id in fake_repository.published_events

    async def test_continues_running_after_repository_errors(
        self,
        test_settings: OutboxSettings,
    ) -> None:
        """Verify worker continues after transient repository errors."""
        # Given
        call_count = 0
        second_poll = asyncio.Event()

        class FlakyRepository(FakeOutboxRepository):
            async def get_unpublished_events(self, limit: int = 100) -> list[OutboxEvent]:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Database timeout")
                second_poll.set()
                return []

        repository = FlakyRepository()
        worker = EventRelayWorker(
            outbox_repository=repository,
            kafka_bus=FakeKafkaPublisher(),
            settings=test_settings,
            service_name="cj_assessment_service",
        )

        # When
        await worker.start()
        try:
            await asyncio.wait_for(second_poll.wait(), timeout=1.0)
        finally:
            await worker.stop()

        # Then
        assert call_count >= 2  # Should have retried after error

    async def test_metrics_enabled_creates_metrics_object(
        self,
        fake_repository: FakeOutboxRepository,
        fake_kafka: FakeKafkaPublisher,
        sample_event: FakeOutboxEvent,
    ) -> None:
        """Verify metrics object is created when enabled in settings."""
        # Given
        settings = OutboxSettings(
            poll_interval_seconds=0.05,
            batch_size=10,
            max_retries=3,
            enable_metrics=True,  # Enable metrics
        )

        worker = EventRelayWorker(
            outbox_repository=fake_repository,
            kafka_bus=fake_kafka,
            settings=settings,
            service_name="cj_assessment_service",
        )

        # Then - Verify metrics object was created
        assert worker.metrics is not None
        assert isinstance(worker.metrics, OutboxMetrics)

        # When - Process an event to verify metrics are used
        await worker.start()
        await asyncio.sleep(0.1)
        await worker.stop()

        # Then - Event should be processed normally
        assert sample_event.id in fake_repository.published_events
