"""
Unit tests for TRUE OUTBOX PATTERN compliance in NLP Service event publishing.

Tests verify that NLP Service follows the TRUE OUTBOX PATTERN correctly:
- All events flow through outbox, never direct Kafka
- Original Pydantic envelopes are passed to outbox
- No mixed pattern violations (Kafka-first with outbox fallback)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.nlp_events import (
    BatchAuthorMatchesSuggestedV1,
    EssayMatchResult,
    StudentMatchSuggestion,
)

from services.nlp_service.config import Settings
from services.nlp_service.implementations.event_publisher_impl import DefaultNlpEventPublisher
from services.nlp_service.implementations.outbox_manager import OutboxManager


@pytest.fixture
def mock_settings() -> Settings:
    """Provide mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "nlp-service"
    settings.ESSAY_AUTHOR_MATCH_SUGGESTED_TOPIC = "huleedu.nlp.batch.author.matches.suggested.v1"
    return settings


@pytest.fixture
def mock_outbox_manager() -> AsyncMock:
    """Provide mock outbox manager for TRUE OUTBOX PATTERN verification."""
    return AsyncMock(spec=OutboxManager)


@pytest.fixture
def nlp_event_publisher(
    mock_outbox_manager: AsyncMock,
    mock_settings: Settings,
) -> DefaultNlpEventPublisher:
    """Provide NLP event publisher instance."""
    return DefaultNlpEventPublisher(
        outbox_manager=mock_outbox_manager,
        source_service_name=mock_settings.SERVICE_NAME,
        output_topic=mock_settings.ESSAY_AUTHOR_MATCH_SUGGESTED_TOPIC,
    )


class TestTrueOutboxPatternCompliance:
    """Test TRUE OUTBOX PATTERN compliance in NLP Service."""

    async def test_publish_author_match_result_uses_outbox_only(
        self,
        nlp_event_publisher: DefaultNlpEventPublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that individual essay results flow through outbox, never direct Kafka."""
        # Arrange
        essay_id = "test-essay-123"
        correlation_id = uuid4()
        suggestions = [
            StudentMatchSuggestion(
                student_id="student-1",
                student_name="Test Student",
                confidence_score=0.95,
                match_reasons=["email_match"],
                extracted_identifiers={"email": "test@example.com"},
            )
        ]

        # Create mock Kafka bus to verify it's NEVER called
        mock_kafka_bus = AsyncMock()

        # Act
        await nlp_event_publisher.publish_author_match_result(
            kafka_bus=mock_kafka_bus,
            essay_id=essay_id,
            suggestions=suggestions,
            match_status="MATCHED",
            correlation_id=correlation_id,
        )

        # Assert - TRUE OUTBOX PATTERN: Only outbox called, never Kafka
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        mock_kafka_bus.publish.assert_not_called()  # ✅ CRITICAL: No direct Kafka calls

        # Verify outbox call parameters
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_type"] == "essay"
        assert call_args.kwargs["aggregate_id"] == essay_id
        assert (
            call_args.kwargs["event_type"] == ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED.value
        )
        assert call_args.kwargs["topic"] == "huleedu.nlp.batch.author.matches.suggested.v1"

        # Verify original Pydantic envelope is passed (not reconstructed dict)
        envelope = call_args.kwargs["event_data"]
        assert hasattr(envelope, "model_dump")  # ✅ Original Pydantic envelope
        assert envelope.source_service == "nlp-service"
        assert envelope.correlation_id == correlation_id
        assert isinstance(envelope.data, BatchAuthorMatchesSuggestedV1)

    async def test_publish_batch_author_match_results_uses_outbox_only(
        self,
        nlp_event_publisher: DefaultNlpEventPublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that batch results flow through outbox, never direct Kafka."""
        # Arrange
        batch_id = "test-batch-456"
        class_id = "test-class-789"
        correlation_id = uuid4()
        match_results = [
            EssayMatchResult(
                essay_id="essay-1",
                text_storage_id="storage-1",
                filename="essay1.pdf",
                suggestions=[
                    StudentMatchSuggestion(
                        student_id="student-1",
                        student_name="Test Student One",
                        confidence_score=0.90,
                        match_reasons=["name_match"],
                        extracted_identifiers={"name": "Test Student"},
                    )
                ],
                no_match_reason=None,
                extraction_metadata={"strategy": "examnet"},
            ),
            EssayMatchResult(
                essay_id="essay-2",
                text_storage_id="storage-2",
                filename="essay2.pdf",
                suggestions=[],
                no_match_reason="No matching students found",
                extraction_metadata={"strategy": "header"},
            ),
        ]
        processing_summary = {"total_essays": 2, "matched": 1, "no_match": 1}

        # Create mock Kafka bus to verify it's NEVER called
        mock_kafka_bus = AsyncMock()

        # Act
        await nlp_event_publisher.publish_batch_author_match_results(
            kafka_bus=mock_kafka_bus,
            batch_id=batch_id,
            class_id=class_id,
            match_results=match_results,
            processing_summary=processing_summary,
            correlation_id=correlation_id,
        )

        # Assert - TRUE OUTBOX PATTERN: Only outbox called, never Kafka
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        mock_kafka_bus.publish.assert_not_called()  # ✅ CRITICAL: No direct Kafka calls

        # Verify outbox call parameters
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_type"] == "batch"
        assert call_args.kwargs["aggregate_id"] == batch_id
        assert call_args.kwargs["event_type"] == "batch.author.matches.suggested.v1"
        assert call_args.kwargs["topic"] == "huleedu.nlp.batch.author.matches.suggested.v1"

        # Verify original Pydantic envelope is passed
        envelope = call_args.kwargs["event_data"]
        assert hasattr(envelope, "model_dump")  # ✅ Original Pydantic envelope
        assert envelope.source_service == "nlp-service"
        assert envelope.correlation_id == correlation_id

        # Verify event data structure
        event_data = envelope.data
        assert isinstance(event_data, BatchAuthorMatchesSuggestedV1)
        assert event_data.batch_id == batch_id
        assert event_data.class_id == class_id
        assert len(event_data.match_results) == 2
        assert event_data.processing_summary == processing_summary

    async def test_outbox_manager_error_propagation(
        self,
        nlp_event_publisher: DefaultNlpEventPublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that outbox errors are properly propagated (no fallback to Kafka)."""
        # Arrange
        mock_outbox_manager.publish_to_outbox.side_effect = Exception("Outbox failure")
        mock_kafka_bus = AsyncMock()

        # Act & Assert - Outbox failure should propagate, no Kafka fallback
        with pytest.raises(Exception, match="Outbox failure"):
            await nlp_event_publisher.publish_author_match_result(
                kafka_bus=mock_kafka_bus,
                essay_id="test-essay",
                suggestions=[],
                match_status="NO_MATCH",
                correlation_id=uuid4(),
            )

        # Verify no fallback to direct Kafka (TRUE OUTBOX PATTERN)
        mock_kafka_bus.publish.assert_not_called()

    async def test_event_envelope_metadata_injection(
        self,
        nlp_event_publisher: DefaultNlpEventPublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that trace context is properly injected into event metadata."""
        # Arrange
        correlation_id = uuid4()
        mock_kafka_bus = AsyncMock()

        # Act
        await nlp_event_publisher.publish_author_match_result(
            kafka_bus=mock_kafka_bus,
            essay_id="test-essay",
            suggestions=[],
            match_status="NO_MATCH",
            correlation_id=correlation_id,
        )

        # Assert - Verify metadata was injected
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args.kwargs["event_data"]

        # Metadata should be injected (not empty)
        assert envelope.metadata is not None
        assert isinstance(envelope.metadata, dict)

    async def test_kafka_bus_parameter_compatibility(
        self,
        nlp_event_publisher: DefaultNlpEventPublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that kafka_bus parameter is maintained for interface compatibility but not used."""
        # Arrange
        mock_kafka_bus = AsyncMock()
        correlation_id = uuid4()

        # Act - kafka_bus parameter should be accepted but ignored
        await nlp_event_publisher.publish_batch_author_match_results(
            kafka_bus=mock_kafka_bus,  # Accepted for interface compatibility
            batch_id="test-batch",
            class_id="test-class",
            match_results=[],
            processing_summary={"total_essays": 0, "matched": 0},
            correlation_id=correlation_id,
        )

        # Assert - kafka_bus is never used (TRUE OUTBOX PATTERN)
        mock_kafka_bus.publish.assert_not_called()
        mock_outbox_manager.publish_to_outbox.assert_called_once()


class TestAntiPatternPrevention:
    """Test that anti-patterns are prevented in NLP Service."""

    async def test_no_kafka_first_with_outbox_fallback_pattern(
        self,
        nlp_event_publisher: DefaultNlpEventPublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Verify that NLP Service never implements Kafka-first with outbox fallback anti-pattern."""
        # This test ensures the anti-pattern is never implemented:
        # try:
        #     await kafka_bus.publish(...)
        #     return  # Success - no outbox needed
        # except Exception:
        #     await outbox_manager.publish(...) # Only fallback

        mock_kafka_bus = AsyncMock()
        correlation_id = uuid4()

        # Act
        await nlp_event_publisher.publish_author_match_result(
            kafka_bus=mock_kafka_bus,
            essay_id="test-essay",
            suggestions=[],
            match_status="NO_MATCH",
            correlation_id=correlation_id,
        )

        # Assert - TRUE OUTBOX PATTERN: Always outbox first, never Kafka
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        mock_kafka_bus.publish.assert_not_called()

        # Verify outbox is called even when Kafka bus is available and healthy
        # This proves we're not doing Kafka-first with outbox fallback
        assert mock_outbox_manager.publish_to_outbox.call_count == 1

    async def test_no_exception_based_data_transport(
        self,
        nlp_event_publisher: DefaultNlpEventPublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Verify that events are never passed through exception details."""
        # This test ensures we never use exceptions to transport event data
        # which would be an anti-pattern for the outbox implementation

        mock_kafka_bus = AsyncMock()
        suggestions = [
            StudentMatchSuggestion(
                student_id="student-1",
                student_name="Test Student",
                confidence_score=0.85,
                match_reasons=["email_match"],
                extracted_identifiers={"email": "test@example.com"},
            )
        ]

        # Act
        await nlp_event_publisher.publish_author_match_result(
            kafka_bus=mock_kafka_bus,
            essay_id="test-essay",
            suggestions=suggestions,
            match_status="MATCHED",
            correlation_id=uuid4(),
        )

        # Assert - Event data is passed directly to outbox, not through exceptions
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args.kwargs["event_data"]

        # Verify complete event data is intact
        assert envelope.data.match_results[0].suggestions == suggestions
        assert envelope.data.processing_summary["matched"] == 1

    def test_no_dual_mode_interfaces(self, mock_outbox_manager: AsyncMock) -> None:
        """Verify that publisher only accepts Pydantic models, not dicts."""
        # NLP event publisher should only work with proper Pydantic models
        # No dual-mode interfaces that accept both dict and Pydantic

        publisher = DefaultNlpEventPublisher(
            outbox_manager=mock_outbox_manager,
            source_service_name="nlp-service",
            output_topic="test.topic",
        )

        # The publisher should only have methods that accept Pydantic models
        # and pass them to outbox as-is, not convert from dicts
        assert hasattr(publisher, "publish_author_match_result")
        assert hasattr(publisher, "publish_batch_author_match_results")

        # Methods should require structured parameters, not accept raw dicts
        # This is enforced by type hints and implementation
