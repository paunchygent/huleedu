"""
Unit tests for StudentAssociationsConfirmedHandler.

Tests the Phase 1 student matching integration logic for handling
student associations confirmation events and updating batch status.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.validation_events import StudentAssociationsConfirmedV1
from common_core.status_enums import BatchStatus
from huleedu_service_libs.error_handling import HuleEduError

from services.batch_orchestrator_service.implementations.student_associations_confirmed_handler import (  # noqa: E501
    StudentAssociationsConfirmedHandler,
)
from services.batch_orchestrator_service.protocols import (
    BatchRepositoryProtocol,
)


class TestStudentAssociationsConfirmedHandler:
    """Test suite for StudentAssociationsConfirmedHandler."""

    @pytest.fixture
    def mock_batch_repo(self) -> AsyncMock:
        """Create mock batch repository."""
        return AsyncMock(spec=BatchRepositoryProtocol)

    @pytest.fixture
    def handler(
        self,
        mock_batch_repo: AsyncMock,
    ) -> StudentAssociationsConfirmedHandler:
        """Create handler instance with mocked dependencies."""
        return StudentAssociationsConfirmedHandler(
            batch_repo=mock_batch_repo,
        )

    @pytest.fixture
    def sample_associations(self) -> dict[str, str]:
        """Create sample student associations."""
        return {str(uuid4()): f"student_{i}" for i in range(3)}

    @pytest.fixture
    def valid_batch_dict(self) -> dict:
        """Create a batch dict in AWAITING_STUDENT_VALIDATION status."""
        return {
            "id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "name": "Test Batch",
            "description": "Test batch for student associations",
            "status": BatchStatus.AWAITING_STUDENT_VALIDATION.value,
            "class_id": "class_456",  # REGULAR batch
            "total_essays": 3,
        }

    @pytest.mark.asyncio
    async def test_updates_batch_to_ready_for_pipeline(
        self,
        handler: StudentAssociationsConfirmedHandler,
        mock_batch_repo: AsyncMock,
        valid_batch_dict: dict,
        sample_associations: dict[str, str],
    ) -> None:
        """Test that handler updates batch to STUDENT_VALIDATION_COMPLETED."""
        # Arrange
        batch_id = valid_batch_dict["id"]
        correlation_id = uuid4()

        event = StudentAssociationsConfirmedV1(
            batch_id=batch_id,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            associations=[],
            validation_summary={"human": 0, "timeout": 0, "auto": 0},
        )

        envelope = EventEnvelope[StudentAssociationsConfirmedV1](
            event_type="validation.student.associations.confirmed",
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event,
        )

        mock_msg = MagicMock()
        mock_msg.value = envelope.model_dump_json().encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED)

        # Mock batch retrieval
        mock_batch_repo.get_batch_by_id.return_value = valid_batch_dict

        # Act
        await handler.handle_student_associations_confirmed(mock_msg)

        # Assert
        # Should retrieve the batch
        mock_batch_repo.get_batch_by_id.assert_called_once_with(batch_id)

        # Should update batch status
        mock_batch_repo.update_batch_status.assert_called_once_with(
            batch_id, BatchStatus.STUDENT_VALIDATION_COMPLETED
        )

    @pytest.mark.asyncio
    async def test_wrong_batch_state_returns_early(
        self,
        handler: StudentAssociationsConfirmedHandler,
        mock_batch_repo: AsyncMock,
        sample_associations: dict[str, str],
    ) -> None:
        """Test that wrong batch state causes early return without processing."""
        # Arrange
        batch_dict = {
            "id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "name": "Test Batch Wrong Status",
            "description": "Test batch with wrong status",
            "status": BatchStatus.STUDENT_VALIDATION_COMPLETED.value,  # Wrong status
            "class_id": "class_456",
            "total_essays": 3,
        }

        event = StudentAssociationsConfirmedV1(
            batch_id=batch_dict["id"],
            class_id="class_456",
            course_code=CourseCode.ENG5,
            associations=[],
            validation_summary={"human": 0, "timeout": 0, "auto": 0},
        )

        envelope = EventEnvelope[StudentAssociationsConfirmedV1](
            event_type="validation.student.associations.confirmed",
            source_service="class_management_service",
            correlation_id=uuid4(),
            data=event,
        )

        mock_msg = MagicMock()
        mock_msg.value = envelope.model_dump_json().encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED)

        mock_batch_repo.get_batch_by_id.return_value = batch_dict

        # Act
        await handler.handle_student_associations_confirmed(mock_msg)

        # Assert - Should retrieve batch but not update anything (early return)
        mock_batch_repo.get_batch_by_id.assert_called_once_with(batch_dict["id"])
        mock_batch_repo.update_batch_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_batch_raises_error(
        self,
        handler: StudentAssociationsConfirmedHandler,
        mock_batch_repo: AsyncMock,
        sample_associations: dict[str, str],
    ) -> None:
        """Test that missing batch raises not found error."""
        # Arrange
        batch_id = str(uuid4())
        correlation_id = uuid4()

        event = StudentAssociationsConfirmedV1(
            batch_id=batch_id,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            associations=[],
            validation_summary={"human": 0, "timeout": 0, "auto": 0},
        )

        envelope = EventEnvelope[StudentAssociationsConfirmedV1](
            event_type="validation.student.associations.confirmed",
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event,
        )

        mock_msg = MagicMock()
        mock_msg.value = envelope.model_dump_json().encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED)

        # Mock batch not found
        mock_batch_repo.get_batch_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await handler.handle_student_associations_confirmed(mock_msg)

            error = exc_info.value
            assert error.error_detail.service == "batch_orchestrator_service"
            assert error.error_detail.operation == "student_associations_confirmed_handling"
            assert error.error_detail.details.get("field") == "batch_id"
            assert f"Batch {batch_id} not found" in error.error_detail.message

    @pytest.mark.asyncio
    async def test_handles_empty_associations(
        self,
        handler: StudentAssociationsConfirmedHandler,
        mock_batch_repo: AsyncMock,
        valid_batch_dict: dict,
    ) -> None:
        """Test that handler can handle empty associations dictionary."""
        # Arrange
        batch_id = valid_batch_dict["id"]
        correlation_id = uuid4()

        event = StudentAssociationsConfirmedV1(
            batch_id=batch_id,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            associations=[],  # Empty associations
            validation_summary={"human": 0, "timeout": 0, "auto": 0},
        )

        envelope = EventEnvelope[StudentAssociationsConfirmedV1](
            event_type="validation.student.associations.confirmed",
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event,
        )

        mock_msg = MagicMock()
        mock_msg.value = envelope.model_dump_json().encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED)

        mock_batch_repo.get_batch_by_id.return_value = valid_batch_dict

        # Act
        await handler.handle_student_associations_confirmed(mock_msg)

        # Assert - Should still process even with empty associations
        mock_batch_repo.update_batch_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotency_on_duplicate_events(
        self,
        handler: StudentAssociationsConfirmedHandler,
        mock_batch_repo: AsyncMock,
        valid_batch_dict: dict,
    ) -> None:
        """Test that duplicate events are handled idempotently."""
        # Arrange
        batch_id = valid_batch_dict["id"]
        correlation_id = uuid4()

        event = StudentAssociationsConfirmedV1(
            batch_id=batch_id,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            associations=[],
            validation_summary={"human": 0, "timeout": 0, "auto": 0},
        )

        envelope = EventEnvelope[StudentAssociationsConfirmedV1](
            event_type="validation.student.associations.confirmed",
            source_service="class_management_service",
            correlation_id=correlation_id,
            data=event,
        )

        mock_msg = MagicMock()
        mock_msg.value = envelope.model_dump_json().encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED)

        # First call - batch in correct state
        mock_batch_repo.get_batch_by_id.return_value = valid_batch_dict

        await handler.handle_student_associations_confirmed(mock_msg)

        # Second call - batch already processed
        processed_batch_dict = valid_batch_dict.copy()
        processed_batch_dict["status"] = BatchStatus.STUDENT_VALIDATION_COMPLETED.value
        mock_batch_repo.get_batch_by_id.return_value = processed_batch_dict

        await handler.handle_student_associations_confirmed(mock_msg)

        # Assert - Second call should return early without further updates
        assert mock_batch_repo.get_batch_by_id.call_count == 2
        assert mock_batch_repo.update_batch_status.call_count == 1  # Only called once

    @pytest.mark.asyncio
    async def test_invalid_json_message_raises_error(
        self,
        handler: StudentAssociationsConfirmedHandler,
    ) -> None:
        """Test that invalid JSON in Kafka message raises validation error."""
        # Arrange
        mock_msg = MagicMock()
        mock_msg.value = b"invalid json {"  # Invalid JSON
        mock_msg.topic = topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED)

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await handler.handle_student_associations_confirmed(mock_msg)

        error = exc_info.value
        assert error.error_detail.service == "batch_orchestrator_service"
        assert error.error_detail.operation == "student_associations_confirmed_handling"
        assert error.error_detail.details.get("field") == "message_format"
        assert "Invalid JSON" in error.error_detail.message
