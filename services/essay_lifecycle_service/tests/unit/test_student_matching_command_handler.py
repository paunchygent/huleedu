"""
Unit tests for StudentMatchingCommandHandler.

Tests the Phase 1 student matching integration logic for handling
student matching initiation commands from BOS and publishing to NLP.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.batch_service_models import BatchServiceStudentMatchingInitiateCommandDataV1
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.essay_lifecycle_events import BatchStudentMatchingRequestedV1
from common_core.metadata_models import EssayProcessingInputRefV1
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.essay_lifecycle_service.implementations.student_matching_command_handler import (
    StudentMatchingCommandHandler,
)
from services.essay_lifecycle_service.models_db import EssayStateDB
from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    EssayRepositoryProtocol,
    OutboxManagerProtocol,
)


class TestStudentMatchingCommandHandler:
    """Test suite for StudentMatchingCommandHandler."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock essay repository."""
        return AsyncMock(spec=EssayRepositoryProtocol)

    @pytest.fixture
    def mock_batch_tracker(self) -> AsyncMock:
        """Create mock batch essay tracker."""
        return AsyncMock(spec=BatchEssayTracker)

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        """Create mock outbox manager."""
        return AsyncMock(spec=OutboxManagerProtocol)

    @pytest.fixture
    def mock_session_factory(self) -> MagicMock:
        """Create mock session factory."""
        mock_factory = MagicMock(spec=async_sessionmaker)
        mock_session = AsyncMock(spec=AsyncSession)
        mock_transaction = AsyncMock()

        # Set up the async context managers properly
        mock_factory.return_value = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session
        mock_factory.return_value.__aexit__.return_value = None

        mock_session.begin.return_value = AsyncMock()
        mock_session.begin.return_value.__aenter__.return_value = mock_transaction
        mock_session.begin.return_value.__aexit__.return_value = None

        return mock_factory

    @pytest.fixture
    def handler(
        self,
        mock_repository: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_outbox_manager: AsyncMock,
        mock_session_factory: AsyncMock,
    ) -> StudentMatchingCommandHandler:
        """Create handler instance with mocked dependencies."""
        return StudentMatchingCommandHandler(
            repository=mock_repository,
            batch_tracker=mock_batch_tracker,
            outbox_manager=mock_outbox_manager,
            session_factory=mock_session_factory,
        )

    @pytest.fixture
    def sample_essays(self) -> list[EssayProcessingInputRefV1]:
        """Create sample essay references."""
        return [
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id=str(uuid4()),
            )
            for _ in range(3)
        ]

    @pytest.fixture
    def sample_essay_states(
        self, sample_essays: list[EssayProcessingInputRefV1]
    ) -> list[EssayStateDB]:
        """Create sample essay states matching the essay references."""
        return [
            EssayStateDB(
                essay_id=essay_ref.essay_id,
                batch_id=str(uuid4()),
                text_storage_id=essay_ref.text_storage_id,
                processing_metadata={},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            for essay_ref in sample_essays
        ]

    @pytest.fixture
    def command_data(
        self, sample_essays: list[EssayProcessingInputRefV1]
    ) -> BatchServiceStudentMatchingInitiateCommandDataV1:
        """Create sample student matching command data."""
        from common_core.event_enums import ProcessingEvent

        return BatchServiceStudentMatchingInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND,
            entity_id=str(uuid4()),
            entity_type="batch",
            parent_id=None,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            essays_to_process=sample_essays,
        )

    @pytest.mark.asyncio
    async def test_handler_is_stateless_during_phase1(
        self,
        handler: StudentMatchingCommandHandler,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
        mock_session_factory: AsyncMock,
        command_data: BatchServiceStudentMatchingInitiateCommandDataV1,
    ) -> None:
        """Test that handler operates statelessly during Phase 1 - no essay state updates."""
        # Arrange
        correlation_id = uuid4()

        # Act
        await handler.handle_student_matching_command(command_data, correlation_id)

        # Assert
        # Handler should NOT access essay states during Phase 1
        mock_repository.get_essay_state.assert_not_called()

        # Handler should NOT update essay metadata during Phase 1
        mock_repository.update_essay_processing_metadata.assert_not_called()

        # Handler should still publish the event
        mock_outbox_manager.publish_to_outbox.assert_called_once()

    @pytest.mark.asyncio
    async def test_publishes_batch_student_matching_requested(
        self,
        handler: StudentMatchingCommandHandler,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
        mock_session_factory: AsyncMock,
        command_data: BatchServiceStudentMatchingInitiateCommandDataV1,
        sample_essay_states: list[EssayStateDB],
    ) -> None:
        """Test that handler publishes BatchStudentMatchingRequestedV1 event."""
        # Arrange
        correlation_id = uuid4()
        session = mock_session_factory.return_value.__aenter__.return_value

        # Act
        await handler.handle_student_matching_command(command_data, correlation_id)

        # Assert
        # Should publish to outbox
        mock_outbox_manager.publish_to_outbox.assert_called_once()

        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_id"] == command_data.entity_id
        assert call_args.kwargs["aggregate_type"] == "batch"
        assert call_args.kwargs["event_type"] == topic_name(
            ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED
        )
        assert call_args.kwargs["topic"] == topic_name(
            ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED
        )
        assert call_args.kwargs["session"] == session

        # Verify event data
        event_envelope = call_args.kwargs["event_data"]
        assert isinstance(event_envelope, EventEnvelope)
        assert event_envelope.correlation_id == correlation_id
        assert event_envelope.source_service == "essay_lifecycle_service"

        event_data = event_envelope.data
        assert isinstance(event_data, BatchStudentMatchingRequestedV1)
        assert event_data.entity_id == command_data.entity_id
        assert event_data.batch_id == command_data.entity_id
        assert event_data.class_id == command_data.class_id
        assert event_data.essays_to_process == command_data.essays_to_process

    @pytest.mark.asyncio
    async def test_uses_outbox_for_reliable_delivery(
        self,
        handler: StudentMatchingCommandHandler,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
        mock_session_factory: AsyncMock,
        command_data: BatchServiceStudentMatchingInitiateCommandDataV1,
    ) -> None:
        """Test that handler uses outbox pattern for reliable event delivery."""
        # Arrange
        correlation_id = uuid4()
        session = mock_session_factory.return_value.__aenter__.return_value

        # Act
        await handler.handle_student_matching_command(command_data, correlation_id)

        # Assert
        # Should use the session from the transaction
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["session"] == session

        # Verify transaction structure
        mock_session_factory.assert_called_once()
        session.begin.assert_called_once()

    @pytest.mark.asyncio
    async def test_processes_all_commands_regardless_of_essay_existence(
        self,
        handler: StudentMatchingCommandHandler,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
        command_data: BatchServiceStudentMatchingInitiateCommandDataV1,
    ) -> None:
        """Test that handler processes commands without checking essay existence."""
        # Arrange
        correlation_id = uuid4()

        # Act - Should not raise exception regardless of essay existence
        await handler.handle_student_matching_command(command_data, correlation_id)

        # Assert
        # Handler should NOT check essay states during Phase 1
        mock_repository.get_essay_state.assert_not_called()

        # Should still publish the event
        mock_outbox_manager.publish_to_outbox.assert_called_once()

        # Should NOT update any metadata during Phase 1
        mock_repository.update_essay_processing_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_validates_command_data(
        self,
        handler: StudentMatchingCommandHandler,
        sample_essays: list[EssayProcessingInputRefV1],
    ) -> None:
        """Test that handler validates command data before processing."""
        # Arrange
        correlation_id = uuid4()

        # Create command with missing batch_id
        invalid_command = BatchServiceStudentMatchingInitiateCommandDataV1(
            event_name=ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND,
            entity_id="",  # Empty batch_id should cause validation error
            entity_type="batch",
            parent_id=None,
            class_id="class_456",
            course_code=CourseCode.ENG5,
            essays_to_process=sample_essays,
        )

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await handler.handle_student_matching_command(invalid_command, correlation_id)

        error = exc_info.value
        assert error.error_detail.service == "essay_lifecycle_service"
        assert error.error_detail.operation == "handle_student_matching_command"
        assert "Missing batch_id" in error.error_detail.message

    @pytest.mark.asyncio
    async def test_error_handling_and_rollback(
        self,
        handler: StudentMatchingCommandHandler,
        mock_outbox_manager: AsyncMock,
        command_data: BatchServiceStudentMatchingInitiateCommandDataV1,
    ) -> None:
        """Test that handler properly handles errors and maintains transaction integrity."""
        # Arrange
        correlation_id = uuid4()

        # Mock outbox to raise an error
        mock_outbox_manager.publish_to_outbox.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await handler.handle_student_matching_command(command_data, correlation_id)

        error = exc_info.value
        assert error.error_detail.service == "essay_lifecycle_service"
        assert error.error_detail.operation == "handle_student_matching_command"
        assert "Failed to process student matching command" in error.error_detail.message
        assert error.error_detail.details.get("batch_id") == command_data.entity_id
        assert error.error_detail.details.get("error_type") == "Exception"

    @pytest.mark.asyncio
    async def test_command_processing_completes_successfully(
        self,
        handler: StudentMatchingCommandHandler,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
        command_data: BatchServiceStudentMatchingInitiateCommandDataV1,
    ) -> None:
        """Test that handler processes command successfully as a stateless router."""
        # Arrange
        correlation_id = uuid4()

        # Act
        await handler.handle_student_matching_command(command_data, correlation_id)

        # Assert
        # Handler should NOT access essay states during Phase 1
        mock_repository.get_essay_state.assert_not_called()

        # Handler should NOT update any metadata during Phase 1
        mock_repository.update_essay_processing_metadata.assert_not_called()

        # Verify event was published
        mock_outbox_manager.publish_to_outbox.assert_called_once()

        # Verify event data
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_id"] == command_data.entity_id
        assert call_args.kwargs["topic"] == topic_name(
            ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED
        )
