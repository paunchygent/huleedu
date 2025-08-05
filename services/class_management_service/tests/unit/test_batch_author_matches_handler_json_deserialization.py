"""Unit tests for BatchAuthorMatchesHandler JSON deserialization scenarios.

This test file specifically covers the critical gap where EventEnvelope loses type information
during JSON deserialization, which is what happens in production Kafka message processing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import CourseCode
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
    session.scalar.return_value = None  # No existing associations by default
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
def sample_batch_event() -> BatchAuthorMatchesSuggestedV1:
    """Create sample batch author matches suggested event."""
    suggestion = StudentMatchSuggestion(
        student_id=str(uuid4()),
        student_name="John Doe",
        student_email="john@example.com",
        confidence_score=0.95,
        match_reasons=["Name found in header", "High similarity score"],
        extraction_metadata={
            "extraction_method": "header",
            "matched_name": "John Doe",
        },
    )

    return BatchAuthorMatchesSuggestedV1(
        event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
        batch_id=str(uuid4()),
        class_id=str(uuid4()),
        course_code=CourseCode.ENG5,
        match_results=[
            EssayMatchResult(
                essay_id=str(uuid4()),
                text_storage_id="storage-1",
                filename="essay1.txt",
                suggestions=[suggestion],
                extraction_metadata={"processing_time": 1.5},
            ),
        ],
        processing_summary={"total_essays": 1, "matched": 1, "no_match": 0, "errors": 0},
        processing_metadata={"nlp_model": "phase1_matcher_v1.0"},
    )


class TestBatchAuthorMatchesHandlerJsonDeserialization:
    """Test cases for JSON deserialization scenarios."""

    def create_kafka_message_from_json(
        self, batch_event: BatchAuthorMatchesSuggestedV1
    ) -> ConsumerRecord:
        """Create a Kafka message that simulates real-world JSON deserialization."""
        # Create envelope with proper typing
        envelope = EventEnvelope[BatchAuthorMatchesSuggestedV1](
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            event_timestamp=datetime.now(UTC),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=batch_event,
        )

        # Serialize to JSON (what Kafka producer does)
        json_data = envelope.model_dump(mode="json")
        json_bytes = json.dumps(json_data).encode("utf-8")

        # Create mock Kafka message
        msg = Mock(spec=ConsumerRecord)
        msg.value = json_bytes
        msg.topic = topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED)
        msg.partition = 0
        msg.offset = 100
        return msg

    def create_envelope_from_json_deserialization(self, kafka_msg: ConsumerRecord) -> EventEnvelope:
        """Create envelope using JSON deserialization (loses type information)."""
        raw_message = kafka_msg.value.decode("utf-8")

        # This is the established pattern used in production event processors
        # Parse JSON manually and create envelope with data as dict
        import json

        json_data = json.loads(raw_message)

        return EventEnvelope(
            event_id=json_data.get("event_id"),
            event_type=json_data.get("event_type", ""),
            event_timestamp=json_data.get("event_timestamp"),
            source_service=json_data.get("source_service", ""),
            schema_version=json_data.get("schema_version", 1),
            correlation_id=json_data.get("correlation_id"),
            data_schema_uri=json_data.get("data_schema_uri"),
            data=json_data.get("data", {}),  # Keep as dict for model_validate()
            metadata=json_data.get("metadata"),
        )

    @pytest.mark.asyncio
    async def test_handler_processes_json_deserialized_envelope(
        self,
        handler: BatchAuthorMatchesHandler,
        sample_batch_event: BatchAuthorMatchesSuggestedV1,
        mock_class_repository: AsyncMock,
        mock_session_factory: Mock,
    ) -> None:
        """Test that handler can process envelopes created from JSON deserialization.

        This is the critical test that was missing from the original unit tests.
        It simulates the real-world scenario where Kafka messages are deserialized from JSON,
        which causes EventEnvelope to lose type information for the data field.
        """
        # Arrange - Create message through JSON serialization/deserialization
        kafka_msg = self.create_kafka_message_from_json(sample_batch_event)
        envelope = self.create_envelope_from_json_deserialization(kafka_msg)

        # Verify the data is a dict (not a typed model)
        assert isinstance(envelope.data, dict)
        assert "batch_id" in envelope.data
        assert "class_id" in envelope.data

        # Act - Process the message (handler should handle type conversion)
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Assert - Processing should succeed despite type issue
        assert result is True

        # Verify student lookup was performed
        mock_class_repository.get_student_by_id.assert_called_once()

        # Verify database operations
        session = mock_session_factory.session
        session.add.assert_called_once()
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_json_deserialized_data_raises_error(
        self,
        handler: BatchAuthorMatchesHandler,
        mock_session_factory: Mock,
    ) -> None:
        """Test that malformed data from JSON deserialization raises appropriate error."""
        # Arrange - Create envelope with malformed data (missing required fields)
        malformed_data = {
            "batch_id": "test-batch",
            # Missing required fields: class_id, match_results, processing_summary
        }

        envelope: EventEnvelope = EventEnvelope(
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data=malformed_data,  # This will become a generic BaseModel
        )

        # Create mock Kafka message
        kafka_msg = Mock(spec=ConsumerRecord)
        kafka_msg.value = b'{"fake": "message"}'
        kafka_msg.topic = "test"
        kafka_msg.partition = 0
        kafka_msg.offset = 1

        # Act & Assert - Should raise HuleEduError due to validation failure
        with pytest.raises(HuleEduError) as exc_info:
            await handler.handle(
                msg=kafka_msg,
                envelope=envelope,
                http_session=AsyncMock(),
                correlation_id=uuid4(),
                span=None,
            )

        # Verify it's a processing error with validation details
        assert "Failed to process batch author matches" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_json_data_field_raises_error(
        self,
        handler: BatchAuthorMatchesHandler,
    ) -> None:
        """Test that empty data field from JSON deserialization raises appropriate error."""
        # This simulates when EventEnvelope deserialization creates an empty data dict
        # Use a real EventEnvelope with empty data to avoid mock issues
        envelope: EventEnvelope[Any] = EventEnvelope(
            event_type=topic_name(ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED),
            source_service="nlp_service",
            correlation_id=uuid4(),
            data={},  # Empty data dict - this will fail model_validate
        )

        kafka_msg = Mock(spec=ConsumerRecord)
        kafka_msg.value = b'{"empty": "data"}'

        # Should raise HuleEduError due to empty data
        with pytest.raises(HuleEduError):
            await handler.handle(
                msg=kafka_msg,
                envelope=envelope,
                http_session=AsyncMock(),
                correlation_id=uuid4(),
                span=None,
            )

    @pytest.mark.asyncio
    async def test_json_deserialization_preserves_all_event_data(
        self,
        sample_batch_event: BatchAuthorMatchesSuggestedV1,
    ) -> None:
        """Test that the JSON contains all necessary data even if EventEnvelope loses typing."""
        # Arrange
        kafka_msg = self.create_kafka_message_from_json(sample_batch_event)

        # Act - Parse raw JSON directly (bypass EventEnvelope)
        raw_message = kafka_msg.value.decode("utf-8")
        json_data = json.loads(raw_message)

        # Assert - All data should be present in JSON
        assert "data" in json_data
        data_dict = json_data["data"]

        # Verify required fields are present
        assert "batch_id" in data_dict
        assert "class_id" in data_dict
        assert "match_results" in data_dict
        assert "processing_summary" in data_dict

        # Verify we can reconstruct the correct object from JSON
        reconstructed = BatchAuthorMatchesSuggestedV1.model_validate(data_dict)
        assert reconstructed.batch_id == sample_batch_event.batch_id
        assert reconstructed.class_id == sample_batch_event.class_id
        assert len(reconstructed.match_results) == len(sample_batch_event.match_results)

    @pytest.mark.asyncio
    async def test_handler_with_multiple_essays_json_deserialization(
        self,
        handler: BatchAuthorMatchesHandler,
        mock_class_repository: AsyncMock,
        mock_session_factory: Mock,
    ) -> None:
        """Test handler with multiple essays through JSON deserialization."""
        # Arrange - Create event with multiple essays
        suggestions = [
            StudentMatchSuggestion(
                student_id=str(uuid4()),
                student_name="John Doe",
                student_email="john@example.com",
                confidence_score=0.95,
                match_reasons=["header_match"],
                extraction_metadata={"method": "header"},
            ),
            StudentMatchSuggestion(
                student_id=str(uuid4()),
                student_name="Jane Smith",
                student_email="jane@example.com",
                confidence_score=0.85,
                match_reasons=["content_match"],
                extraction_metadata={"method": "content"},
            ),
        ]

        batch_event = BatchAuthorMatchesSuggestedV1(
            event_name=ProcessingEvent.BATCH_AUTHOR_MATCHES_SUGGESTED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            course_code=CourseCode.ENG5,
            match_results=[
                EssayMatchResult(
                    essay_id=str(uuid4()),
                    text_storage_id="storage-1",
                    filename="essay1.txt",
                    suggestions=[suggestions[0]],
                    extraction_metadata={},
                ),
                EssayMatchResult(
                    essay_id=str(uuid4()),
                    text_storage_id="storage-2",
                    filename="essay2.txt",
                    suggestions=[suggestions[1]],
                    extraction_metadata={},
                ),
            ],
            processing_summary={"total_essays": 2, "matched": 2, "no_match": 0, "errors": 0},
        )

        # Create message through JSON serialization/deserialization
        kafka_msg = self.create_kafka_message_from_json(batch_event)
        envelope = self.create_envelope_from_json_deserialization(kafka_msg)

        # Act
        result = await handler.handle(
            msg=kafka_msg,
            envelope=envelope,
            http_session=AsyncMock(),
            correlation_id=uuid4(),
            span=None,
        )

        # Assert
        assert result is True

        # Verify both students were looked up
        assert mock_class_repository.get_student_by_id.call_count == 2

        # Verify both associations were created
        session = mock_session_factory.session
        assert session.add.call_count == 2
