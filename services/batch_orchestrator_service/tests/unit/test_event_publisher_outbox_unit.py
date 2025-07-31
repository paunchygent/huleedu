"""
Unit tests for DefaultBatchEventPublisherImpl with TRUE OUTBOX PATTERN.

Tests focus on verifying the correct interaction with the OutboxManager,
aggregate type determination, and error handling using simplified test data.

This test suite verifies compliance with Rule 042.1 (True Transactional Outbox Pattern):
- ALWAYS use outbox for transactional safety
- NEVER try Kafka first
- Store events in database transaction with business data
- Relay worker publishes asynchronously
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from common_core.events.envelope import EventEnvelope

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.implementations.event_publisher_impl import (
    DefaultBatchEventPublisherImpl,
)


class FakeOutboxManager:
    """Fake implementation of OutboxManager for testing."""

    def __init__(self) -> None:
        self.publish_calls: list[dict[str, Any]] = []
        self.should_fail = False
        self.failure_message = "Outbox storage failed"

    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,
        topic: str,
        session: Any | None = None,
    ) -> None:
        """Store event in fake outbox."""
        if self.should_fail:
            raise Exception(self.failure_message)

        call_data = {
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "event_data": event_data,
            "topic": topic,
            "session": session,
        }
        self.publish_calls.append(call_data)


@pytest.fixture
def test_settings() -> Settings:
    """Test settings for batch orchestrator service."""
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "batch-orchestrator-service"
    return settings


@pytest.fixture
def fake_outbox_manager() -> FakeOutboxManager:
    """Fake outbox manager for testing."""
    return FakeOutboxManager()


@pytest.fixture
def event_publisher(
    fake_outbox_manager: FakeOutboxManager,
    test_settings: Settings,
) -> DefaultBatchEventPublisherImpl:
    """Create event publisher with fake dependencies for TRUE OUTBOX PATTERN."""
    return DefaultBatchEventPublisherImpl(
        outbox_manager=fake_outbox_manager,  # type: ignore
        settings=test_settings,
    )


@pytest.fixture
def sample_correlation_id() -> UUID:
    """Sample correlation ID for testing."""
    return uuid4()


class TestDefaultBatchEventPublisherImpl:
    """Test DefaultBatchEventPublisherImpl behavior with TRUE OUTBOX PATTERN."""

    def test_constructor_initialization(self, test_settings: Settings) -> None:
        """Test that constructor properly initializes with TRUE OUTBOX PATTERN dependencies."""
        # Given
        fake_outbox_manager = FakeOutboxManager()

        # When
        publisher = DefaultBatchEventPublisherImpl(
            outbox_manager=fake_outbox_manager,  # type: ignore
            settings=test_settings,
        )

        # Then
        assert publisher.outbox_manager is fake_outbox_manager
        assert publisher.settings is test_settings

    async def test_publish_batch_event_success(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox_manager: FakeOutboxManager,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify batch event is correctly stored in outbox using TRUE OUTBOX PATTERN."""
        # Given - using realistic test data structure
        test_data = {
            "event_name": "batch.spellcheck.initiate.command",
            "entity_ref": {"entity_id": "batch-001", "entity_type": "batch"},
            "essays_to_process": [
                {"essay_id": "essay1", "text_storage_id": "storage1"},
                {"essay_id": "essay2", "text_storage_id": "storage2"},
            ],
            "language": "en",
        }

        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.spellcheck.initiate.command.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data=test_data,
        )

        # When
        await event_publisher.publish_batch_event(event_envelope, key="batch-001")

        # Then - TRUE OUTBOX PATTERN: Always use outbox
        assert len(fake_outbox_manager.publish_calls) == 1
        call = fake_outbox_manager.publish_calls[0]

        assert call["aggregate_id"] == "batch-001"
        assert call["aggregate_type"] == "batch"
        assert call["event_type"] == "huleedu.batch.spellcheck.initiate.command.v1"
        assert call["topic"] == "huleedu.batch.spellcheck.initiate.command.v1"
        assert call["session"] is None

        # Verify original envelope was passed
        stored_envelope = call["event_data"]
        assert stored_envelope is event_envelope
        assert stored_envelope.correlation_id == sample_correlation_id

    async def test_publish_batch_event_with_session(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox_manager: FakeOutboxManager,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify batch event supports session parameter for transactional atomicity."""
        # Given
        test_data = {"event_name": "test.event"}
        event_envelope = EventEnvelope[Any](
            event_type="test.event.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data=test_data,
        )
        mock_session = Mock()

        # When
        await event_publisher.publish_batch_event(
            event_envelope, key="batch-001", session=mock_session
        )

        # Then
        assert len(fake_outbox_manager.publish_calls) == 1
        call = fake_outbox_manager.publish_calls[0]
        assert call["session"] is mock_session

    async def test_outbox_failure_propagates_exception(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox_manager: FakeOutboxManager,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify that outbox storage failures are propagated as exceptions."""
        # Given
        fake_outbox_manager.should_fail = True
        fake_outbox_manager.failure_message = "Database connection lost"

        test_data = {
            "event_name": "batch.spellcheck.initiate.command",
            "entity_ref": {"entity_id": "batch-fail", "entity_type": "batch"},
            "essays_to_process": [{"essay_id": "essay1", "text_storage_id": "storage1"}],
            "language": "en",
        }

        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.spellcheck.initiate.command.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data=test_data,
        )

        # When/Then
        with pytest.raises(Exception) as exc_info:
            await event_publisher.publish_batch_event(event_envelope, key="batch-fail")

        # Verify original exception is raised
        error = exc_info.value
        assert str(error) == "Database connection lost"

        # Verify no calls were recorded due to failure
        assert len(fake_outbox_manager.publish_calls) == 0

    async def test_aggregate_type_determination_batch(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox_manager: FakeOutboxManager,
        sample_correlation_id: UUID,
    ) -> None:
        """Test that batch-related events get correct aggregate type."""
        # Given
        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.processing.completed.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data={"test": "data"},
        )

        # When
        await event_publisher.publish_batch_event(event_envelope, key="test-key")

        # Then
        assert len(fake_outbox_manager.publish_calls) == 1
        call = fake_outbox_manager.publish_calls[0]
        assert call["aggregate_type"] == "batch"

    async def test_aggregate_type_determination_pipeline(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox_manager: FakeOutboxManager,
        sample_correlation_id: UUID,
    ) -> None:
        """Test that pipeline-related events get correct aggregate type."""
        # Given
        event_envelope = EventEnvelope[Any](
            event_type="huleedu.pipeline.phase.started.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data={"test": "data"},
        )

        # When
        await event_publisher.publish_batch_event(event_envelope, key="test-key")

        # Then
        assert len(fake_outbox_manager.publish_calls) == 1
        call = fake_outbox_manager.publish_calls[0]
        assert call["aggregate_type"] == "pipeline"

    async def test_aggregate_type_determination_unknown(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox_manager: FakeOutboxManager,
        sample_correlation_id: UUID,
    ) -> None:
        """Test that unknown event types get unknown aggregate type."""
        # Given
        event_envelope = EventEnvelope[Any](
            event_type="huleedu.something.else.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data={"test": "data"},
        )

        # When
        await event_publisher.publish_batch_event(event_envelope, key="test-key")

        # Then
        assert len(fake_outbox_manager.publish_calls) == 1
        call = fake_outbox_manager.publish_calls[0]
        assert call["aggregate_type"] == "unknown"

    async def test_correlation_id_as_aggregate_id_fallback(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox_manager: FakeOutboxManager,
        sample_correlation_id: UUID,
    ) -> None:
        """Test that correlation ID is used as aggregate ID when no key provided."""
        # Given
        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.test.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data={"test": "data"},
        )

        # When
        await event_publisher.publish_batch_event(event_envelope)  # No key provided

        # Then
        assert len(fake_outbox_manager.publish_calls) == 1
        call = fake_outbox_manager.publish_calls[0]
        assert call["aggregate_id"] == str(sample_correlation_id)

    async def test_true_outbox_pattern_compliance(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox_manager: FakeOutboxManager,
        sample_correlation_id: UUID,
    ) -> None:
        """
        Verify TRUE OUTBOX PATTERN compliance:
        - ALWAYS use outbox (never direct Kafka)
        - Store events for transactional safety
        - Relay worker publishes asynchronously
        """
        # Given
        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.test.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data={"test": "data"},
        )

        # When
        await event_publisher.publish_batch_event(event_envelope, key="test-batch")

        # Then - TRUE OUTBOX PATTERN expectations
        assert len(fake_outbox_manager.publish_calls) == 1, "Event must be stored in outbox"

        call = fake_outbox_manager.publish_calls[0]
        assert call["event_data"] is event_envelope, "Original envelope must be passed"
        assert call["aggregate_id"] == "test-batch", "Aggregate ID must be preserved"
        assert call["topic"] == event_envelope.event_type, "Topic must match event type"

        # Verify NO direct Kafka usage (TRUE OUTBOX PATTERN)
        # OutboxManager handles all Kafka publishing via relay worker
