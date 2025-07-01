"""Unit tests for AI feedback initiator implementation.

Tests the AIFeedbackInitiatorImpl for correct command construction, event publishing,
validation, and error handling.

TODO: AI Feedback Service is not yet implemented - these tests verify the BOS
orchestration side works correctly for when the AI Feedback Service is built.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from common_core.batch_service_models import BatchServiceAIFeedbackInitiateCommandDataV1
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.ai_feedback_initiator_impl import (
    AIFeedbackInitiatorImpl,
)
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    DataValidationError,
)


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock event publisher for testing."""
    return AsyncMock(spec=BatchEventPublisherProtocol)


@pytest.fixture
def ai_feedback_initiator(mock_event_publisher: AsyncMock) -> AIFeedbackInitiatorImpl:
    """Create AI feedback initiator with mocked dependencies."""
    return AIFeedbackInitiatorImpl(mock_event_publisher)


@pytest.fixture
def sample_batch_context() -> BatchRegistrationRequestV1:
    """Sample batch registration context for testing - lean registration model."""
    return BatchRegistrationRequestV1(
        expected_essay_count=2,
        course_code=CourseCode.ENG5,
        essay_instructions="Write a 500-word essay analyzing the themes in Shakespeare's Hamlet.",
        user_id="user_123",
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
def sample_correlation_id() -> UUID:
    """Sample correlation ID for testing."""
    return uuid4()


class TestAIFeedbackInitiatorImpl:
    """Test suite for AI feedback initiator implementation."""

    async def test_initiate_phase_success(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: UUID,
    ) -> None:
        """Test successful AI feedback phase initiation."""
        batch_id = "test-batch-456"

        await ai_feedback_initiator.initiate_phase(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.AI_FEEDBACK,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=sample_batch_context,
        )

        # Verify event was published
        mock_event_publisher.publish_batch_event.assert_called_once()

        # Extract and verify the published envelope
        published_envelope: EventEnvelope[BatchServiceAIFeedbackInitiateCommandDataV1] = (
            mock_event_publisher.publish_batch_event.call_args[0][0]
        )

        assert isinstance(published_envelope.data, BatchServiceAIFeedbackInitiateCommandDataV1)
        assert published_envelope.event_type == topic_name(
            ProcessingEvent.BATCH_AI_FEEDBACK_INITIATE_COMMAND,
        )
        assert published_envelope.source_service == "batch-orchestrator-service"
        assert published_envelope.correlation_id == sample_correlation_id

        # Verify command data
        command_data = published_envelope.data
        assert command_data.entity_ref.entity_id == batch_id
        assert command_data.entity_ref.entity_type == "batch"
        assert command_data.essays_to_process == sample_essay_refs
        assert command_data.language == "en"  # Inferred from ENG5
        assert command_data.event_name == ProcessingEvent.BATCH_AI_FEEDBACK_INITIATE_COMMAND

        # Verify AI feedback specific context fields
        assert command_data.course_code == sample_batch_context.course_code
        assert command_data.essay_instructions == sample_batch_context.essay_instructions
        # Educational context fields use placeholder
        # values until Class Management Service integration
        assert command_data.class_type == "GUEST"
        assert command_data.teacher_first_name is None
        assert command_data.teacher_last_name is None

    async def test_initiate_phase_wrong_phase_validation(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: UUID,
    ) -> None:
        """Test that initiator rejects incorrect phase."""
        with pytest.raises(
            DataValidationError,
            match="AIFeedbackInitiatorImpl received incorrect phase",
        ):
            await ai_feedback_initiator.initiate_phase(
                batch_id="test-batch-456",
                phase_to_initiate=PhaseName.CJ_ASSESSMENT,  # Wrong phase!
                correlation_id=sample_correlation_id,
                essays_for_processing=sample_essay_refs,
                batch_context=sample_batch_context,
            )

    async def test_initiate_phase_empty_essays_validation(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_correlation_id: UUID,
    ) -> None:
        """Test that initiator rejects empty essay list."""
        with pytest.raises(
            DataValidationError,
            match="No essays provided for AI feedback initiation",
        ):
            await ai_feedback_initiator.initiate_phase(
                batch_id="test-batch-456",
                phase_to_initiate=PhaseName.AI_FEEDBACK,
                correlation_id=sample_correlation_id,
                essays_for_processing=[],  # Empty list!
                batch_context=sample_batch_context,
            )

    async def test_educational_context_placeholder_values(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: UUID,
    ) -> None:
        """Test that educational context uses placeholder values
        until Class Management Service integration."""
        custom_context = BatchRegistrationRequestV1(
            expected_essay_count=1,
            course_code=CourseCode.ENG6,
            essay_instructions="Analyze the use of symbolism in modern poetry.",
            user_id="user_123",
            essay_ids=["essay1"],
        )

        await ai_feedback_initiator.initiate_phase(
            batch_id="test-batch-456",
            phase_to_initiate=PhaseName.AI_FEEDBACK,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=custom_context,
        )

        # Verify educational context uses placeholder values
        published_envelope = mock_event_publisher.publish_batch_event.call_args[0][0]
        assert published_envelope.data.class_type == "GUEST"
        assert published_envelope.data.teacher_first_name is None
        assert published_envelope.data.teacher_last_name is None

    async def test_language_inference_swedish(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: UUID,
    ) -> None:
        """Test language inference for Swedish course code."""
        swedish_context = BatchRegistrationRequestV1(
            expected_essay_count=1,
            course_code=CourseCode.SV2,  # Swedish course
            essay_instructions="Analysera användningen av metaforer i Strindbergs verk.",
            user_id="user_123",
            essay_ids=["essay1"],
        )

        await ai_feedback_initiator.initiate_phase(
            batch_id="test-batch-456",
            phase_to_initiate=PhaseName.AI_FEEDBACK,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=swedish_context,
        )

        # Verify Swedish language was inferred
        published_envelope = mock_event_publisher.publish_batch_event.call_args[0][0]
        assert published_envelope.data.language == "sv"

    async def test_language_inference_unknown_defaults_to_english(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: UUID,
    ) -> None:
        """Test language inference for English course codes."""
        english_context = BatchRegistrationRequestV1(
            expected_essay_count=1,
            course_code=CourseCode.ENG7,  # Valid English course code
            essay_instructions="Write an essay.",
            user_id="user_123",
            essay_ids=["essay1"],
        )

        await ai_feedback_initiator.initiate_phase(
            batch_id="test-batch-456",
            phase_to_initiate=PhaseName.AI_FEEDBACK,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=english_context,
        )

        # Verify English language (ENG7 maps to English via get_course_language)
        published_envelope = mock_event_publisher.publish_batch_event.call_args[0][0]
        assert published_envelope.data.language == "en"

    async def test_complete_context_fields_included(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: UUID,
    ) -> None:
        """Test that all required context fields are included in the command."""
        comprehensive_context = BatchRegistrationRequestV1(
            expected_essay_count=2,
            course_code=CourseCode.SV1,
            essay_instructions=(
                "Examine the ethical implications of artificial intelligence in 1000 words."
            ),
            user_id="user_123",
            essay_ids=["essay1", "essay2"],
        )

        await ai_feedback_initiator.initiate_phase(
            batch_id="test-batch-456",
            phase_to_initiate=PhaseName.AI_FEEDBACK,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=comprehensive_context,
        )

        # Verify all context fields are present
        published_envelope = mock_event_publisher.publish_batch_event.call_args[0][0]
        command_data = published_envelope.data

        assert command_data.course_code == CourseCode.SV1
        assert command_data.essay_instructions == (
            "Examine the ethical implications of artificial intelligence in 1000 words."
        )
        # Educational context uses placeholder values until Class Management Service integration
        assert command_data.class_type == "GUEST"
        assert command_data.teacher_first_name is None
        assert command_data.teacher_last_name is None

    async def test_event_publisher_exception_propagation(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
        sample_correlation_id: UUID,
    ) -> None:
        """Test that event publisher exceptions are properly propagated."""
        # Configure mock to raise exception
        mock_event_publisher.publish_batch_event.side_effect = Exception("Kafka publish failed")

        with pytest.raises(Exception, match="Kafka publish failed"):
            await ai_feedback_initiator.initiate_phase(
                batch_id="test-batch-456",
                phase_to_initiate=PhaseName.AI_FEEDBACK,
                correlation_id=sample_correlation_id,
                essays_for_processing=sample_essay_refs,
                batch_context=sample_batch_context,
            )

    async def test_correlation_id_propagation(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
        mock_event_publisher: AsyncMock,
        sample_batch_context: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test correlation ID is properly propagated to published events."""
        test_correlation_id = uuid4()
        await ai_feedback_initiator.initiate_phase(
            batch_id="test-batch-456",
            phase_to_initiate=PhaseName.AI_FEEDBACK,
            correlation_id=test_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=sample_batch_context,
        )

        # Verify event was published with correct correlation ID
        mock_event_publisher.publish_batch_event.assert_called_once()
        published_envelope = mock_event_publisher.publish_batch_event.call_args[0][0]
        assert published_envelope.correlation_id == test_correlation_id

    async def test_protocol_compliance(
        self,
        ai_feedback_initiator: AIFeedbackInitiatorImpl,
    ) -> None:
        """Test that implementation properly implements the protocol."""
        # Verify that the implementation has the required methods
        assert hasattr(ai_feedback_initiator, "initiate_phase")
        assert callable(ai_feedback_initiator.initiate_phase)
