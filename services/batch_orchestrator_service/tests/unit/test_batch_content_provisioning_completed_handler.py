"""
Unit tests for BatchContentProvisioningCompletedHandler.

Tests the Phase 1 student matching integration logic for handling
content provisioning completion events and routing GUEST vs REGULAR batches.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.events.batch_coordination_events import BatchContentProvisioningCompletedV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.error_handling import HuleEduError

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler import (  # noqa: E501
    BatchContentProvisioningCompletedHandler,
)
from services.batch_orchestrator_service.protocols import (
    BatchRepositoryProtocol,
    PipelinePhaseInitiatorProtocol,
)


class TestBatchContentProvisioningCompletedHandler:
    """Test suite for BatchContentProvisioningCompletedHandler."""

    @pytest.fixture
    def mock_batch_repo(self) -> AsyncMock:
        """Create mock batch repository."""
        return AsyncMock(spec=BatchRepositoryProtocol)

    @pytest.fixture
    def mock_student_matching_initiator(self) -> AsyncMock:
        """Create mock student matching initiator."""
        return AsyncMock(spec=PipelinePhaseInitiatorProtocol)

    @pytest.fixture
    def phase_initiators_map(
        self, mock_student_matching_initiator: AsyncMock
    ) -> dict[PhaseName, PipelinePhaseInitiatorProtocol]:
        """Create phase initiators map."""
        return {PhaseName.STUDENT_MATCHING: mock_student_matching_initiator}

    @pytest.fixture
    def handler(
        self,
        mock_batch_repo: AsyncMock,
        phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol],
    ) -> BatchContentProvisioningCompletedHandler:
        """Create handler instance with mocked dependencies."""
        return BatchContentProvisioningCompletedHandler(
            batch_repo=mock_batch_repo,
            phase_initiators_map=phase_initiators_map,
        )

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
    async def test_regular_batch_initiates_student_matching(
        self,
        handler: BatchContentProvisioningCompletedHandler,
        mock_batch_repo: AsyncMock,
        mock_student_matching_initiator: AsyncMock,
        regular_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test that REGULAR batches initiate student matching phase."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=3,
            expected_count=3,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            user_id="teacher_123",
            essays_for_processing=sample_essays,
        )

        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_type="batch.content.provisioning.completed",
            source_service="essay_lifecycle_service",
            correlation_id=correlation_id,
            data=event,
        )

        # Create mock Kafka message
        mock_msg = MagicMock()
        mock_msg.value = json.dumps(envelope.model_dump()).encode("utf-8")
        mock_msg.topic = "huleedu.batch.content.provisioning.completed.v1"

        # Mock repository to return REGULAR batch context
        mock_batch_repo.get_batch_context.return_value = regular_batch_context
        mock_batch_repo.get_batch_essays.return_value = sample_essays

        # Act
        with patch(
            "services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler.use_trace_context"
        ) as mock_trace:
            mock_trace.side_effect = lambda _, __, fn: fn()
            await handler.handle_batch_content_provisioning_completed(mock_msg)

        # Assert
        # Should retrieve batch context
        mock_batch_repo.get_batch_context.assert_called_once_with(batch_id)

        # Should retrieve essays from repository
        mock_batch_repo.get_batch_essays.assert_called_once_with(batch_id)

        # Should initiate student matching phase for REGULAR batch
        mock_student_matching_initiator.initiate_phase.assert_called_once_with(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.STUDENT_MATCHING,
            correlation_id=correlation_id,
            essays_for_processing=sample_essays,
            batch_context=regular_batch_context,
        )

    @pytest.mark.asyncio
    async def test_guest_batch_skips_student_matching(
        self,
        handler: BatchContentProvisioningCompletedHandler,
        mock_batch_repo: AsyncMock,
        mock_student_matching_initiator: AsyncMock,
        guest_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test that GUEST batches skip student matching and let ELS handle readiness."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=3,
            expected_count=3,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            user_id="teacher_123",
            essays_for_processing=sample_essays,
        )

        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_type="batch.content.provisioning.completed",
            source_service="essay_lifecycle_service",
            correlation_id=correlation_id,
            data=event,
        )

        # Create mock Kafka message
        mock_msg = MagicMock()
        mock_msg.value = json.dumps(envelope.model_dump()).encode("utf-8")
        mock_msg.topic = "huleedu.batch.content.provisioning.completed.v1"

        # Mock repository to return GUEST batch context
        mock_batch_repo.get_batch_context.return_value = guest_batch_context

        # Act
        with patch(
            "services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler.use_trace_context"
        ) as mock_trace:
            mock_trace.side_effect = lambda _, __, fn: fn()
            await handler.handle_batch_content_provisioning_completed(mock_msg)

        # Assert
        # Should retrieve batch context
        mock_batch_repo.get_batch_context.assert_called_once_with(batch_id)

        # Should NOT retrieve essays for GUEST batch
        mock_batch_repo.get_batch_essays.assert_not_called()

        # Should NOT initiate any phase for GUEST batch
        mock_student_matching_initiator.initiate_phase.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_batch_context_raises_error(
        self,
        handler: BatchContentProvisioningCompletedHandler,
        mock_batch_repo: AsyncMock,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test that missing batch context raises validation error."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=3,
            expected_count=3,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            user_id="teacher_123",
            essays_for_processing=sample_essays,
        )

        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_type="batch.content.provisioning.completed",
            source_service="essay_lifecycle_service",
            correlation_id=correlation_id,
            data=event,
        )

        # Create mock Kafka message
        mock_msg = MagicMock()
        mock_msg.value = json.dumps(envelope.model_dump()).encode("utf-8")
        mock_msg.topic = "huleedu.batch.content.provisioning.completed.v1"

        # Mock repository to return None (batch context not found)
        mock_batch_repo.get_batch_context.return_value = None

        # Act & Assert
        with patch(
            "services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler.use_trace_context"
        ) as mock_trace:
            mock_trace.side_effect = lambda _, __, fn: fn()

            with pytest.raises(HuleEduError) as exc_info:
                await handler.handle_batch_content_provisioning_completed(mock_msg)

            error = exc_info.value
            assert error.error_detail.service == "batch_orchestrator_service"
            assert error.error_detail.operation == "content_provisioning_completed_handling"
            assert error.error_detail.details.get("field") == "batch_context"
            assert "Batch context not found" in error.error_detail.message

    @pytest.mark.asyncio
    async def test_invalid_json_message_raises_error(
        self,
        handler: BatchContentProvisioningCompletedHandler,
    ) -> None:
        """Test that invalid JSON in Kafka message raises validation error."""
        # Arrange
        mock_msg = MagicMock()
        mock_msg.value = b"invalid json {"  # Invalid JSON
        mock_msg.topic = "huleedu.batch.content.provisioning.completed.v1"

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await handler.handle_batch_content_provisioning_completed(mock_msg)

        error = exc_info.value
        assert error.error_detail.service == "batch_orchestrator_service"
        assert error.error_detail.operation == "content_provisioning_completed_handling"
        assert error.error_detail.details.get("field") == "message_format"
        assert "Invalid JSON" in error.error_detail.message

    @pytest.mark.asyncio
    async def test_batch_type_logging(
        self,
        handler: BatchContentProvisioningCompletedHandler,
        mock_batch_repo: AsyncMock,
        mock_student_matching_initiator: AsyncMock,
        regular_batch_context: BatchRegistrationRequestV1,
        guest_batch_context: BatchRegistrationRequestV1,
        sample_essays: list[EssayProcessingInputRefV1],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test that batch type (REGULAR/GUEST) is properly logged."""
        # Test REGULAR batch
        batch_id = str(uuid4())
        correlation_id = uuid4()

        event = BatchContentProvisioningCompletedV1(
            batch_id=batch_id,
            provisioned_count=3,
            expected_count=3,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            user_id="teacher_123",
            essays_for_processing=sample_essays,
        )

        envelope = EventEnvelope[BatchContentProvisioningCompletedV1](
            event_type="batch.content.provisioning.completed",
            source_service="essay_lifecycle_service",
            correlation_id=correlation_id,
            data=event,
        )

        mock_msg = MagicMock()
        mock_msg.value = json.dumps(envelope.model_dump()).encode("utf-8")
        mock_msg.topic = "huleedu.batch.content.provisioning.completed.v1"

        # Test REGULAR batch
        mock_batch_repo.get_batch_context.return_value = regular_batch_context

        with patch(
            "services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler.use_trace_context"
        ) as mock_trace:
            mock_trace.side_effect = lambda _, __, fn: fn()
            await handler.handle_batch_content_provisioning_completed(mock_msg)

        assert f"Batch {batch_id} identified as REGULAR batch (class_id: class_456)" in caplog.text
        assert f"Initiating Phase 1 student matching for REGULAR batch {batch_id}" in caplog.text

        # Clear logs and test GUEST batch
        caplog.clear()
        mock_batch_repo.get_batch_context.return_value = guest_batch_context

        with patch(
            "services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler.use_trace_context"
        ) as mock_trace:
            mock_trace.side_effect = lambda _, __, fn: fn()
            await handler.handle_batch_content_provisioning_completed(mock_msg)

        assert f"Batch {batch_id} identified as GUEST batch (class_id: None)" in caplog.text
        assert f"GUEST batch {batch_id} content provisioning completed" in caplog.text
        assert "No student matching required - ELS will handle essay readiness" in caplog.text
