"""Unit tests for the Phase 1 Essay Student Matching Handler."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.error_enums import ErrorCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.essay_lifecycle_events import BatchStudentMatchingRequestedV1
from common_core.events.nlp_events import StudentMatchSuggestion
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling import HuleEduError

if TYPE_CHECKING:
    from services.nlp_service.command_handlers.essay_student_matching_handler import (
        EssayStudentMatchingHandler,
    )


@pytest.fixture
def mock_content_client() -> AsyncMock:
    """Mock content client for tests."""
    client = AsyncMock()
    client.fetch_content = AsyncMock(return_value="Test essay content with student name John Doe")
    return client


@pytest.fixture
def mock_class_management_client() -> AsyncMock:
    """Mock class management client for tests."""
    client = AsyncMock()
    client.get_class_roster = AsyncMock(
        return_value=[
            {"student_id": "student-1", "name": "John Doe", "email": "john@example.com"},
            {"student_id": "student-2", "name": "Jane Smith", "email": "jane@example.com"},
        ]
    )
    return client


@pytest.fixture
def mock_roster_cache() -> AsyncMock:
    """Mock roster cache for tests."""
    cache = AsyncMock()
    cache.get_roster = AsyncMock(return_value=None)  # Force fetching from service
    cache.set_roster = AsyncMock()
    return cache


@pytest.fixture
def mock_student_matcher() -> AsyncMock:
    """Mock student matcher for tests."""
    matcher = AsyncMock()
    matcher.find_matches = AsyncMock(
        return_value=[
            StudentMatchSuggestion(
                student_id="student-1",
                student_name="John Doe",
                student_email="john@example.com",
                confidence_score=0.95,
                match_reasons=["Name found in header", "High similarity score"],
                extraction_metadata={
                    "extraction_method": "header",
                    "matched_name": "John Doe",
                    "student_roster_name": "John Doe",
                },
            )
        ]
    )
    return matcher


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock event publisher for tests."""
    publisher = AsyncMock()
    publisher.publish_author_match_result = AsyncMock()
    publisher.publish_batch_author_match_results = AsyncMock()
    return publisher


@pytest.fixture
def mock_outbox_repository() -> AsyncMock:
    """Mock outbox repository for tests."""
    return AsyncMock()


@pytest.fixture
def mock_kafka_bus() -> AsyncMock:
    """Mock Kafka bus for tests."""
    return AsyncMock()


@pytest.fixture
def handler(
    mock_content_client: AsyncMock,
    mock_class_management_client: AsyncMock,
    mock_roster_cache: AsyncMock,
    mock_student_matcher: AsyncMock,
    mock_event_publisher: AsyncMock,
    mock_outbox_repository: AsyncMock,
    mock_kafka_bus: AsyncMock,
) -> EssayStudentMatchingHandler:
    """Create handler with mocked dependencies."""
    from services.nlp_service.command_handlers.essay_student_matching_handler import (
        EssayStudentMatchingHandler,
    )

    return EssayStudentMatchingHandler(
        content_client=mock_content_client,
        class_management_client=mock_class_management_client,
        roster_cache=mock_roster_cache,
        student_matcher=mock_student_matcher,
        event_publisher=mock_event_publisher,
        outbox_repository=mock_outbox_repository,
        kafka_bus=mock_kafka_bus,
        tracer=None,
    )


@pytest.fixture
def sample_batch_request() -> BatchStudentMatchingRequestedV1:
    """Create sample batch student matching request."""
    return BatchStudentMatchingRequestedV1(
        batch_id="batch-123",
        class_id="class-456",
        essays_to_process=[
            EssayProcessingInputRefV1(
                essay_id="essay-1",
                text_storage_id="storage-1",
                filename="essay1.txt",
            ),
            EssayProcessingInputRefV1(
                essay_id="essay-2",
                text_storage_id="storage-2",
                filename="essay2.txt",
            ),
        ],
    )


@pytest.fixture
def sample_kafka_message(sample_batch_request: BatchStudentMatchingRequestedV1) -> ConsumerRecord:
    """Create sample Kafka message."""
    envelope = EventEnvelope[BatchStudentMatchingRequestedV1](
        event_type=topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED),
        source_service="essay_lifecycle_service",
        correlation_id=uuid4(),
        data=sample_batch_request,
    )

    msg = Mock(spec=ConsumerRecord)
    msg.value = envelope.model_dump_json().encode("utf-8")
    msg.topic = topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED)
    msg.partition = 0
    msg.offset = 100
    return msg


class TestEssayStudentMatchingHandler:
    """Test cases for Phase 1 Essay Student Matching Handler."""

    @pytest.mark.asyncio
    async def test_can_handle_correct_event_type(
        self, handler: EssayStudentMatchingHandler
    ) -> None:
        """Test handler recognizes correct event type."""
        assert (
            await handler.can_handle(topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED))
            is True
        )
        assert await handler.can_handle("huleedu.essay.student.matching.requested.v1") is False
        assert await handler.can_handle("some.other.event.v1") is False

    @pytest.mark.asyncio
    async def test_successful_batch_processing(
        self,
        handler: EssayStudentMatchingHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_request: BatchStudentMatchingRequestedV1,
        mock_event_publisher: AsyncMock,
        mock_roster_cache: AsyncMock,
        mock_class_management_client: AsyncMock,
    ) -> None:
        """Test successful processing of batch student matching request."""
        # Create envelope with proper data
        envelope = EventEnvelope[BatchStudentMatchingRequestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=sample_batch_request,
        )

        http_session = AsyncMock()
        correlation_id = uuid4()

        # Process the message
        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=http_session,
            correlation_id=correlation_id,
            span=None,
        )

        # Verify success
        assert result is True

        # Verify roster was fetched and cached
        mock_roster_cache.get_roster.assert_called_once_with("class-456")
        mock_class_management_client.get_class_roster.assert_called_once()
        mock_roster_cache.set_roster.assert_called_once()

        # Verify batch results were published
        mock_event_publisher.publish_batch_author_match_results.assert_called_once()

        # Check the published data
        call_args = mock_event_publisher.publish_batch_author_match_results.call_args
        assert call_args.kwargs["batch_id"] == "batch-123"
        assert call_args.kwargs["class_id"] == "class-456"
        assert len(call_args.kwargs["match_results"]) == 2
        assert call_args.kwargs["processing_summary"]["total_essays"] == 2
        assert call_args.kwargs["processing_summary"]["processed"] == 2
        assert call_args.kwargs["processing_summary"]["matched"] == 2

    @pytest.mark.asyncio
    async def test_partial_failure_continues_processing(
        self,
        handler: EssayStudentMatchingHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_request: BatchStudentMatchingRequestedV1,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that partial failures don't stop entire batch processing."""
        # Make first essay fail
        mock_content_client.fetch_content.side_effect = [
            Exception("Content fetch failed"),
            "Essay 2 content with Jane Smith",
        ]

        envelope = EventEnvelope[BatchStudentMatchingRequestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=sample_batch_request,
        )

        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Should still succeed
        assert result is True

        # Verify batch results were published with partial results
        mock_event_publisher.publish_batch_author_match_results.assert_called_once()
        call_args = mock_event_publisher.publish_batch_author_match_results.call_args
        assert len(call_args.kwargs["match_results"]) == 2  # Both essays in results
        assert call_args.kwargs["processing_summary"]["processed"] == 1
        assert call_args.kwargs["processing_summary"]["failed"] == 1

    @pytest.mark.asyncio
    async def test_no_matches_found(
        self,
        handler: EssayStudentMatchingHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_request: BatchStudentMatchingRequestedV1,
        mock_student_matcher: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling when no student matches are found."""
        # No matches found
        mock_student_matcher.find_matches.return_value = []

        envelope = EventEnvelope[BatchStudentMatchingRequestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=sample_batch_request,
        )

        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        assert result is True

        # Verify results show unmatched essays
        call_args = mock_event_publisher.publish_batch_author_match_results.call_args
        assert call_args.kwargs["processing_summary"]["matched"] == 0
        assert call_args.kwargs["processing_summary"]["unmatched"] == 2

        # Check match results have no_match_reason
        match_results = call_args.kwargs["match_results"]
        for result in match_results:
            assert result.no_match_reason == "No matches found"
            assert len(result.suggestions) == 0

    @pytest.mark.asyncio
    async def test_roster_cache_hit(
        self,
        handler: EssayStudentMatchingHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_request: BatchStudentMatchingRequestedV1,
        mock_roster_cache: AsyncMock,
        mock_class_management_client: AsyncMock,
    ) -> None:
        """Test that cached roster is used when available."""
        # Cache returns roster
        cached_roster = [
            {"student_id": "cached-1", "name": "Cached Student", "email": "cached@example.com"}
        ]
        mock_roster_cache.get_roster.return_value = cached_roster

        envelope = EventEnvelope[BatchStudentMatchingRequestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=sample_batch_request,
        )

        await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Verify cache was used, not the client
        mock_roster_cache.get_roster.assert_called_once()
        mock_class_management_client.get_class_roster.assert_not_called()
        mock_roster_cache.set_roster.assert_not_called()

    @pytest.mark.asyncio
    async def test_huleedu_error_propagation(
        self,
        handler: EssayStudentMatchingHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_request: BatchStudentMatchingRequestedV1,
        mock_content_client: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that HuleEduError is propagated correctly."""
        # Mock HuleEdu error
        error_detail = ErrorDetail(
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            message="Content not found",
            correlation_id=uuid4(),
            timestamp=datetime.now(UTC),
            service="content_service",
            operation="fetch_content",
            details={
                "resource_type": "content",
                "resource_id": "storage-1",
            },
        )
        mock_content_client.fetch_content.side_effect = HuleEduError(error_detail)

        envelope = EventEnvelope[BatchStudentMatchingRequestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED),
            source_service="essay_lifecycle_service",
            correlation_id=uuid4(),
            data=sample_batch_request,
        )

        # Should still process batch but with failures
        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Handler returns False when no essays are processed successfully
        assert result is False

        # But it should still publish results with failure information
        mock_event_publisher.publish_batch_author_match_results.assert_called_once()
        call_args = mock_event_publisher.publish_batch_author_match_results.call_args
        assert call_args.kwargs["processing_summary"]["failed"] == 2
        assert call_args.kwargs["processing_summary"]["processed"] == 0

        # Check that error details are included in match results
        match_results = call_args.kwargs["match_results"]
        assert len(match_results) == 2
        for result in match_results:
            assert "Processing error:" in result.no_match_reason
            assert result.extraction_metadata["match_status"] == "ERROR"
