"""
Unit tests for StudentMatchingInitiatorImpl.

Tests the Phase 1 student matching initiator implementation that publishes
student matching commands to ELS for REGULAR batches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.batch_service_models import BatchServiceStudentMatchingInitiateCommandDataV1
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.error_handling import HuleEduError

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.student_matching_initiator_impl import (
    StudentMatchingInitiatorImpl,
)
from services.batch_orchestrator_service.protocols import BatchEventPublisherProtocol


class TestStudentMatchingInitiatorImpl:
    """Test suite for StudentMatchingInitiatorImpl."""

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        return AsyncMock(spec=BatchEventPublisherProtocol)

    @pytest.fixture
    def initiator(self, mock_event_publisher: AsyncMock) -> StudentMatchingInitiatorImpl:
        """Create initiator instance with mocked dependencies."""
        return StudentMatchingInitiatorImpl(event_publisher=mock_event_publisher)

    @pytest.fixture
    def sample_essays(self) -> list[EssayProcessingInputRefV1]:
        """Create sample essay references."""
        return [
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id=str(uuid4()),
            )
            for i in range(3)
        ]

    @pytest.fixture
    def regular_batch_context(self) -> BatchRegistrationRequestV1:
        """Create REGULAR batch context with class_id."""
        return BatchRegistrationRequestV1(
            course_code=CourseCode.ENG5,
            teacher_first_name="Jane",
            teacher_last_name="Smith",
            school_name="Lincoln High",
            essay_instructions="Write about your summer vacation",
            expected_essay_count=3,
            user_id="teacher_123",
            class_id="class_456",  # REGULAR batch has class_id
        )

    @pytest.fixture
    def guest_batch_context(self) -> BatchRegistrationRequestV1:
        """Create GUEST batch context without class_id."""
        return BatchRegistrationRequestV1(
            course_code=CourseCode.ENG5,
            teacher_first_name="John",
            teacher_last_name="Doe",
            school_name="Guest School",
            essay_instructions="Write a short story",
            expected_essay_count=2,
            user_id="guest_teacher_789",
            class_id=None,  # GUEST batch has no class_id
        )

    @pytest.mark.asyncio
    async def test_successful_student_matching_initiation(
        self,
        initiator: StudentMatchingInitiatorImpl,
        mock_event_publisher: AsyncMock,
        regular_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test successful student matching initiation for REGULAR batch."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Act
        await initiator.initiate_phase(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.STUDENT_MATCHING,
            correlation_id=correlation_id,
            essays_for_processing=sample_essays,
            batch_context=regular_batch_context,
        )

        # Assert
        mock_event_publisher.publish_batch_event.assert_called_once()

        # Verify the published event
        call_args = mock_event_publisher.publish_batch_event.call_args
        assert call_args.kwargs["key"] == batch_id

        # Verify the envelope
        envelope = call_args.kwargs["event_envelope"]
        assert isinstance(envelope, EventEnvelope)
        assert envelope.event_type == topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND)
        assert envelope.source_service == "batch_orchestrator_service"
        assert envelope.correlation_id == correlation_id

        # Verify the command data
        command_data = envelope.data
        assert isinstance(command_data, BatchServiceStudentMatchingInitiateCommandDataV1)
        assert command_data.entity_id == batch_id
        assert command_data.class_id == "class_456"
        assert command_data.essays_to_process == sample_essays

    @pytest.mark.asyncio
    async def test_wrong_phase_raises_error(
        self,
        initiator: StudentMatchingInitiatorImpl,
        regular_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test that incorrect phase raises validation error."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await initiator.initiate_phase(
                batch_id=batch_id,
                phase_to_initiate=PhaseName.SPELLCHECK,  # Wrong phase
                correlation_id=correlation_id,
                essays_for_processing=sample_essays,
                batch_context=regular_batch_context,
            )

        error = exc_info.value
        assert error.error_detail.service == "batch_orchestrator_service"
        assert error.error_detail.operation == "student_matching_initiation"
        assert error.error_detail.details.get("field") == "phase_to_initiate"
        assert "StudentMatchingInitiatorImpl received incorrect phase" in error.error_detail.message
        assert error.error_detail.details.get("expected_phase") == "STUDENT_MATCHING"
        assert error.error_detail.details.get("received_phase") == "spellcheck"

    @pytest.mark.asyncio
    async def test_guest_batch_raises_error(
        self,
        initiator: StudentMatchingInitiatorImpl,
        guest_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test that GUEST batch (no class_id) raises validation error."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await initiator.initiate_phase(
                batch_id=batch_id,
                phase_to_initiate=PhaseName.STUDENT_MATCHING,
                correlation_id=correlation_id,
                essays_for_processing=sample_essays,
                batch_context=guest_batch_context,  # GUEST batch with no class_id
            )

        error = exc_info.value
        assert error.error_detail.service == "batch_orchestrator_service"
        assert error.error_detail.operation == "student_matching_initiation"
        assert error.error_detail.details.get("field") == "class_id"
        assert "Student matching initiated for GUEST batch" in error.error_detail.message
        assert error.error_detail.details.get("batch_id") == batch_id
        assert error.error_detail.details.get("batch_type") == "GUEST"

    @pytest.mark.asyncio
    async def test_empty_essays_raises_error(
        self,
        initiator: StudentMatchingInitiatorImpl,
        regular_batch_context: BatchRegistrationRequestV1,
    ) -> None:
        """Test that empty essays list raises validation error."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await initiator.initiate_phase(
                batch_id=batch_id,
                phase_to_initiate=PhaseName.STUDENT_MATCHING,
                correlation_id=correlation_id,
                essays_for_processing=[],  # Empty list
                batch_context=regular_batch_context,
            )

        error = exc_info.value
        assert error.error_detail.service == "batch_orchestrator_service"
        assert error.error_detail.operation == "student_matching_initiation"
        assert error.error_detail.details.get("field") == "essays_for_processing"
        assert "No essays provided for student matching initiation" in error.error_detail.message

    @pytest.mark.asyncio
    async def test_event_publisher_failure_propagates(
        self,
        initiator: StudentMatchingInitiatorImpl,
        mock_event_publisher: AsyncMock,
        regular_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test that event publisher failures propagate correctly."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Mock publisher to raise an exception
        mock_event_publisher.publish_batch_event.side_effect = Exception("Kafka connection failed")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await initiator.initiate_phase(
                batch_id=batch_id,
                phase_to_initiate=PhaseName.STUDENT_MATCHING,
                correlation_id=correlation_id,
                essays_for_processing=sample_essays,
                batch_context=regular_batch_context,
            )

        assert "Kafka connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_student_matching_command_contains_correct_context(
        self,
        initiator: StudentMatchingInitiatorImpl,
        mock_event_publisher: AsyncMock,
        regular_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test that student matching command contains correct class_id and essay count."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Act
        await initiator.initiate_phase(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.STUDENT_MATCHING,
            correlation_id=correlation_id,
            essays_for_processing=sample_essays,
            batch_context=regular_batch_context,
        )

        # Assert - Test actual behavior and side effects
        mock_event_publisher.publish_batch_event.assert_called_once()

        # Verify the command data contains correct context
        call_args = mock_event_publisher.publish_batch_event.call_args
        envelope = call_args.kwargs["event_envelope"]
        command_data = envelope.data

        # Test the actual behavioral outcomes
        assert command_data.class_id == "class_456"  # class_id from regular_batch_context
        assert len(command_data.essays_to_process) == 3  # len(sample_essays) = 3
        assert command_data.essays_to_process == sample_essays  # Exact essay references preserved
