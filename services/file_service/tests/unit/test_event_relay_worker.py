"""
Unit tests for EventRelayWorker from the outbox pattern implementation.

Tests focus on behavior verification with minimal mocking of external dependencies.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest
from huleedu_service_libs.outbox import EventRelayWorker
from huleedu_service_libs.outbox.monitoring import OutboxMetrics
from huleedu_service_libs.outbox.protocols import OutboxEvent
from huleedu_service_libs.outbox.relay import OutboxSettings


@dataclass
class FakeOutboxEvent:
    """Test implementation of OutboxEvent protocol."""

    id: UUID
    aggregate_id: str
    aggregate_type: str
    event_type: str
    event_data: dict[str, Any]
    event_key: str | None
    created_at: datetime
    published_at: datetime | None
    retry_count: int
    last_error: str | None


class FakeOutboxRepository:
    """Test implementation of OutboxRepositoryProtocol."""

    def __init__(self) -> None:
        self.events: list[OutboxEvent] = []
        self.published_events: set[UUID] = set()
        self.failed_events: dict[UUID, str] = {}
        self.retry_counts: dict[UUID, tuple[int, str]] = {}

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
        if event:
            event.retry_count += 1
            event.last_error = error
            self.retry_counts[event_id] = (event.retry_count, error)


class FakeKafkaPublisher:
    """Test implementation of KafkaPublisherProtocol."""

    def __init__(self) -> None:
        self.published_messages: list[tuple[str, Any, str | None]] = []
        self.should_fail = False
        self.failure_message = "Kafka unavailable"

    async def publish(self, topic: str, envelope: Any, key: str | None = None) -> None:
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
        aggregate_type="test_entity",
        event_type="test.event.created.v1",
        event_data={
            "topic": "test.events.v1",
            "data": {"test": "data", "value": 42},
            "correlation_id": str(uuid4()),
            "source_service": "test-service",
            "metadata": {"user_id": "user-123"},
        },
        event_key="test-aggregate-123",
        created_at=datetime.now(timezone.utc),
        published_at=None,
        retry_count=0,
        last_error=None,
    )
    fake_repository.events.append(event)
    return event


class TestEventRelayWorker:
    """Test EventRelayWorker behavior."""

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
            service_name="test-service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)  # Allow processing
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 1
        topic, envelope, key = fake_kafka.published_messages[0]

        assert topic == "test.events.v1"
        assert key == "test-aggregate-123"
        assert envelope.event_type == "test.event.created.v1"
        assert envelope.source_service == "test-service"
        assert envelope.data == {"test": "data", "value": 42}
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
            service_name="test-service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)  # Just enough for one poll
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 0
        assert sample_event.id not in fake_repository.published_events
        assert sample_event.retry_count >= 1  # At least one retry
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
        sample_event.retry_count = test_settings.max_retries
        worker = EventRelayWorker(
            outbox_repository=fake_repository,
            kafka_bus=fake_kafka,
            settings=test_settings,
            service_name="test-service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 0
        assert sample_event.id in fake_repository.failed_events
        assert "Exceeded max retries" in fake_repository.failed_events[sample_event.id]

    async def test_uses_event_mapper_for_topic_resolution(
        self,
        fake_repository: FakeOutboxRepository,
        fake_kafka: FakeKafkaPublisher,
        test_settings: OutboxSettings,
        sample_event: FakeOutboxEvent,
    ) -> None:
        """Verify event mapper is used when topic not in event data."""
        # Given
        sample_event.event_data.pop("topic")

        class TestEventMapper:
            def get_topic_for_event(self, event_type: str) -> str:
                return f"mapped.{event_type}"

        worker = EventRelayWorker(
            outbox_repository=fake_repository,
            kafka_bus=fake_kafka,
            settings=test_settings,
            service_name="test-service",
            event_mapper=TestEventMapper(),
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 1
        topic, _, _ = fake_kafka.published_messages[0]
        assert topic == "mapped.test.event.created.v1"

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
                aggregate_type="test_entity",
                event_type="test.batch.event.v1",
                event_data={
                    "topic": "test.batch.v1",
                    "data": {"index": i},
                },
                event_key=f"key-{i}",
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
            service_name="test-service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.1)
        await worker.stop()

        # Then
        assert len(fake_kafka.published_messages) == 3
        for i, (topic, envelope, key) in enumerate(fake_kafka.published_messages):
            assert topic == "test.batch.v1"
            assert key == f"key-{i}"
            assert envelope.data == {"index": i}
            assert events[i].id in fake_repository.published_events

    async def test_continues_running_after_repository_errors(
        self,
        test_settings: OutboxSettings,
    ) -> None:
        """Verify worker continues after transient repository errors."""
        # Given
        call_count = 0

        class FlakyRepository(FakeOutboxRepository):
            async def get_unpublished_events(self, limit: int = 100) -> list[OutboxEvent]:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Database timeout")
                return []

        repository = FlakyRepository()
        worker = EventRelayWorker(
            outbox_repository=repository,
            kafka_bus=FakeKafkaPublisher(),
            settings=test_settings,
            service_name="test-service",
        )

        # When
        await worker.start()
        await asyncio.sleep(0.2)  # Allow multiple poll cycles
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
            service_name="test-service",
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
