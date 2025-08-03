"""Unit tests for the BatchAuthorMatchesHandler."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.nlp_events import (
    BatchAuthorMatchesSuggestedV1,
    EssayMatchResult,
    StudentMatchSuggestion,
)
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from services.class_management_service.implementations.batch_author_matches_handler import (
        BatchAuthorMatchesHandler,
    )


@pytest.fixture
def mock_class_repository() -> AsyncMock:
    """Mock class repository for tests."""
    repository = AsyncMock()
    # Default: student exists
    repository.get_student_by_id.return_value = Mock(id=uuid4(), first_name="John", last_name="Doe")
    return repository


@pytest.fixture
def mock_session_factory() -> Mock:
    """Mock session factory for tests."""
    # Create mock session with required methods
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = (
        None  # No existing associations by default (handler uses scalar, not get)
    )
    session.add = Mock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    # Mock session.begin() async context manager
    begin_cm = AsyncMock()
    begin_cm.__aenter__ = AsyncMock(return_value=session)
    begin_cm.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = begin_cm

    # Mock session factory() async context manager
    factory_cm = AsyncMock()
    factory_cm.__aenter__ = AsyncMock(return_value=session)
    factory_cm.__aexit__ = AsyncMock(return_value=None)

    # Mock the session factory itself (NOT AsyncMock - it's a regular function)
    factory = Mock()
    factory.return_value = factory_cm

    # Store session reference for test access
    factory.session = session

    return factory


@pytest.fixture
def handler(
    mock_class_repository: AsyncMock,
    mock_session_factory: Mock,
) -> BatchAuthorMatchesHandler:
    """Create handler with mocked dependencies."""
    from services.class_management_service.implementations.batch_author_matches_handler import (
        BatchAuthorMatchesHandler,
    )

    return BatchAuthorMatchesHandler(
        class_repository=mock_class_repository,
        session_factory=mock_session_factory,
    )


@pytest.fixture
def sample_match_suggestions() -> list[StudentMatchSuggestion]:
    """Create sample student match suggestions."""
    return [
        StudentMatchSuggestion(
            student_id=str(uuid4()),
            student_name="John Doe",
            student_email="john@example.com",
            confidence_score=0.95,
            match_reasons=["Name found in header", "High similarity score"],
            extraction_metadata={
                "extraction_method": "header",
                "matched_name": "John Doe",
            },
        ),
        StudentMatchSuggestion(
            student_id=str(uuid4()),
            student_name="Jane Smith",
            student_email="jane@example.com",
            confidence_score=0.85,
            match_reasons=["Name similarity"],
            extraction_metadata={
                "extraction_method": "content",
                "matched_name": "J. Smith",
            },
        ),
    ]


@pytest.fixture
def sample_batch_event(
    sample_match_suggestions: list[StudentMatchSuggestion],
) -> BatchAuthorMatchesSuggestedV1:
    """Create sample batch author matches suggested event."""
    return BatchAuthorMatchesSuggestedV1(
        event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
        batch_id="batch-123",
        class_id="class-456",
        match_results=[
            EssayMatchResult(
                essay_id=str(uuid4()),  # Use proper UUID strings
                text_storage_id="storage-1",
                filename="essay1.txt",
                suggestions=sample_match_suggestions[:1],  # Only first suggestion
                extraction_metadata={"processing_time": 1.5},
            ),
            EssayMatchResult(
                essay_id=str(uuid4()),  # Use proper UUID strings
                text_storage_id="storage-2",
                filename="essay2.txt",
                suggestions=sample_match_suggestions[1:],  # Only second suggestion
                extraction_metadata={"processing_time": 2.1},
            ),
        ],
        processing_summary={"total_essays": 2, "matched": 2, "no_match": 0, "errors": 0},
        processing_metadata={"nlp_model": "phase1_matcher_v1.0"},
    )


@pytest.fixture
def sample_kafka_message(sample_batch_event: BatchAuthorMatchesSuggestedV1) -> ConsumerRecord:
    """Create sample Kafka message."""
    envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
        event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
        event_timestamp=datetime.now(UTC),
        source_service="nlp_service",
        correlation_id=uuid4(),
        data=sample_batch_event,
    )

    msg = Mock(spec=ConsumerRecord)
    msg.value = envelope.model_dump_json().encode("utf-8")
    msg.topic = topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED)
    msg.partition = 0
    msg.offset = 100
    return msg


class TestBatchAuthorMatchesHandler:
    """Test cases for BatchAuthorMatchesHandler."""

    @pytest.mark.asyncio
    async def test_can_handle_correct_event_type(self, handler: BatchAuthorMatchesHandler) -> None:
        """Test handler recognizes correct event type."""
        assert await handler.can_handle(topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED)) is True
        assert await handler.can_handle(topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED)) is False
        assert await handler.can_handle("some.other.event.v1") is False

    @pytest.mark.asyncio
    async def test_successful_batch_processing(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_event: BatchAuthorMatchesSuggestedV1,
        mock_class_repository: AsyncMock,
        mock_session_factory: Mock,
    ) -> None:
        """Test successful processing of batch author matches."""
        # Create envelope with proper data
        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=sample_batch_event,
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

        # Verify student lookups were performed
        assert mock_class_repository.get_student_by_id.call_count == 2

        # Verify database operations
        session = mock_session_factory.session
        assert session.add.call_count == 2  # Two associations created
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_student_not_found_skips_suggestion(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_event: BatchAuthorMatchesSuggestedV1,
        mock_class_repository: AsyncMock,
        mock_session_factory: Mock,
    ) -> None:
        """Test that missing students are skipped gracefully."""
        # Make first student lookup return None (not found)
        mock_class_repository.get_student_by_id.side_effect = [None, Mock()]

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=sample_batch_event,
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

        # Verify only one association was created (second student found)
        session = mock_session_factory.session
        assert session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_existing_association_skipped(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_event: BatchAuthorMatchesSuggestedV1,
        mock_class_repository: AsyncMock,
        mock_session_factory: Mock,
    ) -> None:
        """Test that existing associations are skipped."""
        # Mock existing association for first essay
        existing_association = Mock()
        existing_association.student_id = uuid4()

        session = mock_session_factory.session
        session.scalar.side_effect = [existing_association, None]  # First exists, second doesn't

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=sample_batch_event,
        )

        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        assert result is True

        # Both students should be looked up (validation happens before association check)
        assert mock_class_repository.get_student_by_id.call_count == 2

        # Only one new association should be created (first skipped due to existing)
        assert session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_match_results_handled_gracefully(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        mock_session_factory: Mock,
    ) -> None:
        """Test handling of empty match results."""
        # Create event with no match results
        empty_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id="batch-123",
            class_id="class-456",
            match_results=[],
            processing_summary={"total_essays": 0, "matched": 0, "no_match": 0, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=empty_event,
        )

        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Should return True for empty results (not an error)
        assert result is True

        # No database operations should occur
        session = mock_session_factory.session
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_suggestions_only_stores_first(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        mock_class_repository: AsyncMock,
        mock_session_factory: Mock,
        sample_match_suggestions: list[StudentMatchSuggestion],
    ) -> None:
        """Test that only the first (highest confidence) suggestion is stored per essay."""
        # Create event with multiple suggestions for one essay
        event_with_multiple = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id="batch-123",
            class_id="class-456",
            match_results=[
                EssayMatchResult(
                    essay_id=str(uuid4()),
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=sample_match_suggestions,  # Multiple suggestions
                    extraction_metadata={},
                ),
            ],
            processing_summary={"total_essays": 1, "matched": 1, "no_match": 0, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=event_with_multiple,
        )

        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        assert result is True

        # Only first student should be looked up (handler breaks after first match)
        assert mock_class_repository.get_student_by_id.call_count == 1

        # Only one association should be created despite multiple suggestions
        session = mock_session_factory.session
        assert session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_partial_batch_failure_continues_processing(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_event: BatchAuthorMatchesSuggestedV1,
        mock_class_repository: AsyncMock,
        mock_session_factory: Mock,
    ) -> None:
        """Test that individual essay failures don't stop batch processing."""
        # Make first student lookup fail, second succeed
        mock_class_repository.get_student_by_id.side_effect = [
            Exception("Database error"),
            Mock(id=uuid4()),
        ]

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=sample_batch_event,
        )

        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Should still succeed (partial success is acceptable)
        assert result is True

        # Both students should be attempted
        assert mock_class_repository.get_student_by_id.call_count == 2

        # Only one association should be created (second one succeeded)
        session = mock_session_factory.session
        assert session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_database_flush_failure_propagates(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_event: BatchAuthorMatchesSuggestedV1,
        mock_session_factory: Mock,
    ) -> None:
        """Test that database constraint violations are handled properly."""
        # Make flush fail (simulates constraint violation)
        session = mock_session_factory.session
        session.flush.side_effect = Exception("Constraint violation")

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=sample_batch_event,
        )

        # Should raise HuleEduError due to processing failure
        with pytest.raises(HuleEduError):
            await handler.handle(
                msg=sample_kafka_message,
                envelope=envelope,
                http_session=AsyncMock(),
                correlation_id=uuid4(),
                span=None,
            )

    @pytest.mark.asyncio
    async def test_malformed_event_data_raises_error(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        mock_session_factory: Mock,
    ) -> None:
        """Test that malformed event data raises appropriate error."""
        # Create envelope with invalid data
        envelope: EventEnvelope = EventEnvelope(
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data={"invalid": "data", "missing_required_fields": True},
        )

        # Should raise HuleEduError due to validation failure
        with pytest.raises(HuleEduError):
            await handler.handle(
                msg=sample_kafka_message,
                envelope=envelope,
                http_session=AsyncMock(),
                correlation_id=uuid4(),
                span=None,
            )

    @pytest.mark.asyncio
    async def test_no_suggestions_for_essay_skipped(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        mock_session_factory: Mock,
    ) -> None:
        """Test essays with no suggestions are skipped gracefully."""
        # Create event with essay having no suggestions
        event_no_suggestions = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id="batch-123",
            class_id="class-456",
            match_results=[
                EssayMatchResult(
                    essay_id=str(uuid4()),
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=[],  # No suggestions
                    no_match_reason="No student names found",
                    extraction_metadata={},
                ),
            ],
            processing_summary={"total_essays": 1, "matched": 0, "no_match": 1, "errors": 0},
        )

        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=event_no_suggestions,
        )

        result = await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        assert result is True

        # No database operations should occur
        session = mock_session_factory.session
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_association_creation_uses_correct_data(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_kafka_message: ConsumerRecord,
        sample_batch_event: BatchAuthorMatchesSuggestedV1,
        mock_class_repository: AsyncMock,
        mock_session_factory: Mock,
    ) -> None:
        """Test that EssayStudentAssociation is created with correct data."""
        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=sample_batch_event,
        )

        await handler.handle(
            msg=sample_kafka_message,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Check that associations were created with correct structure
        session = mock_session_factory.session
        assert session.add.call_count == 2

        # Verify the add calls contained EssayStudentAssociation objects
        add_calls = session.add.call_args_list
        for call in add_calls:
            association = call[0][0]  # First argument to session.add()

            # Verify it's the correct type and has required fields
            from services.class_management_service.models_db import EssayStudentAssociation

            assert isinstance(association, EssayStudentAssociation)
            assert association.created_by_user_id == "nlp_service_phase1"
            assert association.essay_id is not None
            assert association.student_id is not None
