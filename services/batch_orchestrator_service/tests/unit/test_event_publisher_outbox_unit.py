"""
Unit tests for DefaultBatchEventPublisherImpl with outbox pattern integration.

Tests focus on verifying the correct interaction with the outbox repository,
aggregate type determination, and error handling using simplified test data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from sqlalchemy.ext.asyncio import AsyncSession

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.implementations.event_publisher_impl import (
    DefaultBatchEventPublisherImpl,
)


class FakeOutboxRepository:
    """Fake implementation of OutboxRepositoryProtocol for testing."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.add_event_calls: list[dict[str, Any]] = []
        self.should_fail = False
        self.failure_message = "Outbox storage failed"

    async def add_event(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data: dict[str, Any],
        topic: str,
        event_key: str | None = None,
        session: AsyncSession | None = None,
    ) -> UUID:
        """Store event in fake outbox."""
        if self.should_fail:
            raise Exception(self.failure_message)

        event_id = uuid4()
        call_data = {
            "id": event_id,
            "aggregate_id": aggregate_id,
            "aggregate_type": aggregate_type,
            "event_type": event_type,
            "event_data": event_data,
            "topic": topic,
            "event_key": event_key,
            "session": session,
        }
        self.add_event_calls.append(call_data)
        self.events.append(call_data)
        return event_id


@pytest.fixture
def test_settings() -> Settings:
    """Test settings for batch orchestrator service."""
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "batch-orchestrator-service"
    return settings


@pytest.fixture
def fake_kafka() -> Mock:
    """Fake Kafka publisher (not used with outbox pattern)."""
    return Mock(spec=KafkaPublisherProtocol)


@pytest.fixture
def fake_outbox() -> FakeOutboxRepository:
    """Fake outbox repository for testing."""
    return FakeOutboxRepository()


@pytest.fixture
def event_publisher(
    fake_kafka: Mock,
    fake_outbox: FakeOutboxRepository,
    test_settings: Settings,
) -> DefaultBatchEventPublisherImpl:
    """Create event publisher with fake dependencies."""
    return DefaultBatchEventPublisherImpl(
        kafka_bus=fake_kafka,
        outbox_repository=fake_outbox,  # type: ignore
        settings=test_settings,
    )


@pytest.fixture
def sample_correlation_id() -> UUID:
    """Sample correlation ID for testing."""
    return uuid4()


class TestDefaultBatchEventPublisherImpl:
    """Test DefaultBatchEventPublisherImpl behavior with outbox pattern."""

    def test_constructor_initialization(self) -> None:
        """Test that constructor properly initializes all dependencies."""
        # Given
        kafka_bus = Mock(spec=KafkaPublisherProtocol)
        outbox_repo = FakeOutboxRepository()
        settings = Mock(spec=Settings)

        # When
        publisher = DefaultBatchEventPublisherImpl(
            kafka_bus=kafka_bus,
            outbox_repository=outbox_repo,  # type: ignore
            settings=settings,
        )

        # Then
        assert publisher.kafka_bus is kafka_bus
        assert publisher.outbox_repository is outbox_repo
        assert publisher.settings is settings

    async def test_publish_batch_event_success(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify batch event is correctly stored in outbox."""
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
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            await event_publisher.publish_batch_event(event_envelope, key="batch-001")

        # Then
        assert len(fake_outbox.add_event_calls) == 1
        call = fake_outbox.add_event_calls[0]

        assert call["aggregate_id"] == "batch-001"
        assert call["aggregate_type"] == "batch"
        assert call["event_type"] == "huleedu.batch.spellcheck.initiate.command.v1"
        assert call["topic"] == "huleedu.batch.spellcheck.initiate.command.v1"
        assert call["event_key"] == "batch-001"

        # Verify envelope structure
        envelope_data = call["event_data"]
        assert envelope_data["event_type"] == "huleedu.batch.spellcheck.initiate.command.v1"
        assert envelope_data["source_service"] == "batch-orchestrator-service"
        assert envelope_data["correlation_id"] == str(sample_correlation_id)
        assert envelope_data["data"]["entity_ref"]["entity_id"] == "batch-001"
        assert len(envelope_data["data"]["essays_to_process"]) == 2

    async def test_outbox_failure_propagates_exception(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify that outbox storage failures are propagated as structured errors."""
        # Given
        fake_outbox.should_fail = True
        fake_outbox.failure_message = "Database connection lost"

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
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            with pytest.raises(Exception) as exc_info:
                await event_publisher.publish_batch_event(event_envelope, key="batch-fail")

            # Verify structured error is raised
            error = exc_info.value
            assert hasattr(error, "error_detail")
            assert error.error_detail.error_code == "KAFKA_PUBLISH_ERROR"
            # The error message is wrapped, but the original exception is preserved
            assert "Exception" in str(error)
            assert error.error_detail.correlation_id == sample_correlation_id

        assert len(fake_outbox.add_event_calls) == 0

    async def test_aggregate_type_determination_batch(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Test that batch-related events get correct aggregate type."""
        # Given
        batch_events = [
            "huleedu.batch.spellcheck.initiate.command.v1",
            "huleedu.batch.nlp.initiate.command.v1",
            "huleedu.batch.ai_feedback.initiate.command.v1",
            "some.service.batch.processing.started.v1",
        ]

        # When
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            for event_type in batch_events:
                envelope = EventEnvelope[Any](
                    event_type=event_type,
                    source_service="batch-orchestrator-service",
                    correlation_id=sample_correlation_id,
                    data={"test": "data"},
                )
                await event_publisher.publish_batch_event(envelope, key="test-key")

        # Then
        assert len(fake_outbox.add_event_calls) == 4
        for call in fake_outbox.add_event_calls:
            assert call["aggregate_type"] == "batch"

    async def test_aggregate_type_determination_pipeline(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Test that pipeline-related events get correct aggregate type."""
        # Given
        pipeline_events = [
            "huleedu.pipeline.status.updated.v1",
            "orchestrator.pipeline.created.v1",
            "some.service.pipeline.completed.v1",
        ]

        # When
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            for event_type in pipeline_events:
                envelope = EventEnvelope[Any](
                    event_type=event_type,
                    source_service="batch-orchestrator-service",
                    correlation_id=sample_correlation_id,
                    data={"test": "data"},
                )
                await event_publisher.publish_batch_event(envelope, key="test-key")

        # Then
        assert len(fake_outbox.add_event_calls) == 3
        for call in fake_outbox.add_event_calls:
            assert call["aggregate_type"] == "pipeline"

    async def test_aggregate_type_determination_unknown(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Test that unrecognized events get 'unknown' aggregate type."""
        # Given
        unknown_events = [
            "huleedu.user.created.v1",
            "system.health.check.v1",
            "some.random.event.v1",
        ]

        # When
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            for event_type in unknown_events:
                envelope = EventEnvelope[Any](
                    event_type=event_type,
                    source_service="batch-orchestrator-service",
                    correlation_id=sample_correlation_id,
                    data={"test": "data"},
                )
                await event_publisher.publish_batch_event(envelope, key="test-key")

        # Then
        assert len(fake_outbox.add_event_calls) == 3
        for call in fake_outbox.add_event_calls:
            assert call["aggregate_type"] == "unknown"

    async def test_trace_context_injection_when_span_active(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify trace context is injected when active span exists."""
        # Given
        test_data = {
            "event_name": "batch.spellcheck.initiate.command",
            "entity_ref": {"entity_id": "batch-trace", "entity_type": "batch"},
            "essays_to_process": [{"essay_id": "essay1", "text_storage_id": "storage1"}],
            "language": "en",
        }

        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.spellcheck.initiate.command.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data=test_data,
        )

        mock_span = Mock()
        mock_inject = Mock()

        # When
        with patch("huleedu_service_libs.observability.get_current_span", return_value=mock_span):
            with patch(
                "services.batch_orchestrator_service.implementations.event_publisher_impl.inject_trace_context",
                mock_inject,
            ):
                await event_publisher.publish_batch_event(event_envelope, key="batch-trace")

        # Then
        mock_inject.assert_called_once()
        # Verify inject_trace_context was called with the envelope metadata
        call_args = mock_inject.call_args[0]
        assert isinstance(call_args[0], dict)  # metadata dict

    async def test_trace_context_not_injected_when_no_span(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify trace context is not injected when no active span exists."""
        # Given
        test_data = {
            "event_name": "batch.spellcheck.initiate.command",
            "entity_ref": {"entity_id": "batch-no-trace", "entity_type": "batch"},
            "essays_to_process": [{"essay_id": "essay1", "text_storage_id": "storage1"}],
            "language": "en",
        }

        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.spellcheck.initiate.command.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data=test_data,
            metadata={"existing": "metadata"},
        )

        mock_inject = Mock()

        # When
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            with patch("huleedu_service_libs.observability.inject_trace_context", mock_inject):
                await event_publisher.publish_batch_event(event_envelope, key="batch-no-trace")

        # Then
        assert not mock_inject.called
        # Verify existing metadata is preserved
        call = fake_outbox.add_event_calls[0]
        envelope_data = call["event_data"]
        assert envelope_data["metadata"]["existing"] == "metadata"

    async def test_events_not_published_directly_to_kafka(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_kafka: Mock,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify events are NOT published directly to Kafka, only to outbox."""
        # Given
        test_data = {
            "event_name": "batch.ai_feedback.initiate.command",
            "entity_ref": {"entity_id": "batch-no-kafka", "entity_type": "batch"},
            "essays_to_process": [{"essay_id": "essay1", "text_storage_id": "storage1"}],
            "language": "en",
            "course_code": "ENG5",
            "essay_instructions": "Instructions",
            "class_type": "REGULAR",
            "teacher_first_name": "John",
            "teacher_last_name": "Doe",
        }

        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.ai_feedback.initiate.command.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data=test_data,
        )

        # When
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            await event_publisher.publish_batch_event(event_envelope, key="batch-no-kafka")

        # Then
        # Verify event was stored in outbox
        fake_outbox_instance = event_publisher.outbox_repository
        assert isinstance(fake_outbox_instance, FakeOutboxRepository)
        assert len(fake_outbox_instance.add_event_calls) == 1

        # Verify Kafka was NOT called
        fake_kafka.publish.assert_not_called()

    async def test_event_envelope_serialization(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify event envelope is properly serialized with model_dump(mode='json')."""
        # Given
        timestamp = datetime.now(timezone.utc)

        test_data = {
            "event_name": "batch.nlp.initiate.command",
            "entity_ref": {"entity_id": "batch-serial", "entity_type": "batch"},
            "essays_to_process": [
                {"essay_id": "essay1", "text_storage_id": "storage1"},
                {"essay_id": "essay2", "text_storage_id": "storage2"},
            ],
            "language": "fr",
        }

        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.nlp.initiate.command.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data=test_data,
            event_timestamp=timestamp,
        )

        # When
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            await event_publisher.publish_batch_event(event_envelope, key="batch-serial")

        # Then
        call = fake_outbox.add_event_calls[0]
        envelope_data = call["event_data"]

        # Verify timestamps are serialized as ISO strings
        assert isinstance(envelope_data["event_timestamp"], str)

        # Verify UUIDs are serialized as strings
        assert isinstance(envelope_data["correlation_id"], str)
        assert envelope_data["correlation_id"] == str(sample_correlation_id)

        # Verify the topic is included in the data
        assert envelope_data["topic"] == "huleedu.batch.nlp.initiate.command.v1"

        # Verify the entire structure is JSON-serializable
        json_str = json.dumps(envelope_data)
        assert json_str  # Should not raise exception

    async def test_key_defaults_to_correlation_id_when_not_provided(
        self,
        event_publisher: DefaultBatchEventPublisherImpl,
        fake_outbox: FakeOutboxRepository,
        sample_correlation_id: UUID,
    ) -> None:
        """Verify that when key is not provided, correlation_id is used as aggregate_id."""
        # Given
        test_data = {
            "event_name": "batch.spellcheck.initiate.command",
            "entity_ref": {"entity_id": "batch-no-key", "entity_type": "batch"},
            "essays_to_process": [{"essay_id": "essay1", "text_storage_id": "storage1"}],
            "language": "en",
        }

        event_envelope = EventEnvelope[Any](
            event_type="huleedu.batch.spellcheck.initiate.command.v1",
            source_service="batch-orchestrator-service",
            correlation_id=sample_correlation_id,
            data=test_data,
        )

        # When
        with patch("huleedu_service_libs.observability.get_current_span", return_value=None):
            await event_publisher.publish_batch_event(event_envelope)  # No key provided

        # Then
        assert len(fake_outbox.add_event_calls) == 1
        call = fake_outbox.add_event_calls[0]

        assert call["aggregate_id"] == str(sample_correlation_id)
        assert call["event_key"] is None
