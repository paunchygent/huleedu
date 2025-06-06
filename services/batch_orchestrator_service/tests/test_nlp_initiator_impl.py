"""Unit tests for NLP initiator implementation.

Tests the NLPInitiatorImpl for correct command construction, event publishing,
validation, and error handling. 

TODO: NLP Service is not yet implemented - these tests verify the BOS
orchestration side works correctly for when the NLP Service is built.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from api_models import BatchRegistrationRequestV1
from implementations.nlp_initiator_impl import NLPInitiatorImpl
from protocols import BatchEventPublisherProtocol, DataValidationError

from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV1
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock event publisher for testing."""
    return AsyncMock(spec=BatchEventPublisherProtocol)


@pytest.fixture
def nlp_initiator(mock_event_publisher: AsyncMock) -> NLPInitiatorImpl:
    """Create NLP initiator with mocked dependencies."""
    return NLPInitiatorImpl(mock_event_publisher)


@pytest.fixture
def sample_batch_context() -> BatchRegistrationRequestV1:
    """Sample batch registration context for testing."""
    return BatchRegistrationRequestV1(
        expected_essay_count=2,
        course_code="ENG101",
        class_designation="Advanced Writing",
        teacher_name="Dr. Smith",
        essay_instructions="Write a 500-word essay on climate change.",
        essay_ids=["essay1", "essay2"],
    )


@pytest.fixture
def sample_essay_refs() -> list[EssayProcessingInputRefV1]:
    """Sample essay references for processing."""
    return [
        EssayProcessingInputRefV1(
            essay_id="essay1",
            text_storage_id="storage1",
        ),
        EssayProcessingInputRefV1(
            essay_id="essay2",
            text_storage_id="storage2",
        ),
    ]


@pytest.fixture
def sample_correlation_id() -> uuid.UUID:
    """Sample correlation ID for testing."""
    return uuid.uuid4()


class TestNLPInitiatorImpl:
    """Test suite for NLP initiator implementation."""

    async def test_initiate_phase_success(
        self,
        nlp_initiator: NLPInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: uuid.UUID,
    ) -> None:
        """Test successful NLP phase initiation."""
        batch_id = "test-batch-123"

        await nlp_initiator.initiate_phase(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.NLP,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=sample_batch_context,
        )

        # Verify event was published
        mock_event_publisher.publish_batch_event.assert_called_once()

        # Extract and verify the published envelope
        published_envelope: EventEnvelope[BatchServiceNLPInitiateCommandDataV1] = (
            mock_event_publisher.publish_batch_event.call_args[0][0]
        )

        assert isinstance(published_envelope.data, BatchServiceNLPInitiateCommandDataV1)
        assert published_envelope.event_type == topic_name(ProcessingEvent.BATCH_NLP_INITIATE_COMMAND)
        assert published_envelope.source_service == "batch-orchestrator-service"
        assert published_envelope.correlation_id == sample_correlation_id

        # Verify command data
        command_data = published_envelope.data
        assert command_data.entity_ref.entity_id == batch_id
        assert command_data.entity_ref.entity_type == "batch"
        assert command_data.essays_to_process == sample_essay_refs
        assert command_data.language == "en"  # Inferred from ENG101
        assert command_data.event_name == ProcessingEvent.BATCH_NLP_INITIATE_COMMAND

    async def test_initiate_phase_wrong_phase_validation(
        self,
        nlp_initiator: NLPInitiatorImpl,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: uuid.UUID,
    ) -> None:
        """Test that initiator rejects incorrect phase."""
        with pytest.raises(DataValidationError, match="NLPInitiatorImpl received incorrect phase"):
            await nlp_initiator.initiate_phase(
                batch_id="test-batch-123",
                phase_to_initiate=PhaseName.SPELLCHECK,  # Wrong phase!
                correlation_id=sample_correlation_id,
                essays_for_processing=sample_essay_refs,
                batch_context=sample_batch_context,
            )

    async def test_initiate_phase_empty_essays_validation(
        self,
        nlp_initiator: NLPInitiatorImpl,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_correlation_id: uuid.UUID,
    ) -> None:
        """Test that initiator rejects empty essay list."""
        with pytest.raises(DataValidationError, match="No essays provided for NLP initiation"):
            await nlp_initiator.initiate_phase(
                batch_id="test-batch-123",
                phase_to_initiate=PhaseName.NLP,
                correlation_id=sample_correlation_id,
                essays_for_processing=[],  # Empty list!
                batch_context=sample_batch_context,
            )

    async def test_language_inference_swedish(
        self,
        nlp_initiator: NLPInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: uuid.UUID,
    ) -> None:
        """Test language inference for Swedish course code."""
        swedish_context = BatchRegistrationRequestV1(
            expected_essay_count=1,
            course_code="SV1",  # Swedish course
            class_designation="Svenska språket",
            teacher_name="Professor Andersson",
            essay_instructions="Skriv en uppsats om miljöfrågor.",
            essay_ids=["essay1"],
        )

        await nlp_initiator.initiate_phase(
            batch_id="test-batch-123",
            phase_to_initiate=PhaseName.NLP,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=swedish_context,
        )

        # Verify Swedish language was inferred
        published_envelope = mock_event_publisher.publish_batch_event.call_args[0][0]
        assert published_envelope.data.language == "sv"

    async def test_language_inference_unknown_defaults_to_english(
        self,
        nlp_initiator: NLPInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: uuid.UUID,
    ) -> None:
        """Test that unknown course codes default to English."""
        unknown_context = BatchRegistrationRequestV1(
            expected_essay_count=1,
            course_code="XYZ999",  # Unknown course code
            class_designation="Mystery Subject",
            teacher_name="Professor Unknown",
            essay_instructions="Write something.",
            essay_ids=["essay1"],
        )

        await nlp_initiator.initiate_phase(
            batch_id="test-batch-123",
            phase_to_initiate=PhaseName.NLP,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=unknown_context,
        )

        # Verify defaulted to English
        published_envelope = mock_event_publisher.publish_batch_event.call_args[0][0]
        assert published_envelope.data.language == "en"

    async def test_event_publisher_exception_propagation(
        self,
        nlp_initiator: NLPInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: uuid.UUID,
    ) -> None:
        """Test that event publisher exceptions are properly propagated."""
        # Configure mock to raise exception
        mock_event_publisher.publish_batch_event.side_effect = Exception("Kafka connection failed")

        with pytest.raises(Exception, match="Kafka connection failed"):
            await nlp_initiator.initiate_phase(
                batch_id="test-batch-123",
                phase_to_initiate=PhaseName.NLP,
                correlation_id=sample_correlation_id,
                essays_for_processing=sample_essay_refs,
                batch_context=sample_batch_context,
            )

    async def test_none_correlation_id_handling(
        self,
        nlp_initiator: NLPInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test handling of None correlation ID."""
        await nlp_initiator.initiate_phase(
            batch_id="test-batch-123",
            phase_to_initiate=PhaseName.NLP,
            correlation_id=None,  # None correlation ID
            essays_for_processing=sample_essay_refs,
            batch_context=sample_batch_context,
        )

        # Verify event was still published successfully
        mock_event_publisher.publish_batch_event.assert_called_once()
        published_envelope = mock_event_publisher.publish_batch_event.call_args[0][0]
        assert published_envelope.correlation_id is None
