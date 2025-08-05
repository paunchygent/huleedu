"""
Unit tests for StudentAssociationHandler.

Tests the Phase 1 student matching integration logic for handling
student associations confirmation events from Class Management Service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.batch_coordination_events import BatchEssaysReady
from common_core.events.validation_events import (
    StudentAssociationConfirmation,
    StudentAssociationsConfirmedV1,
)
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.essay_lifecycle_service.implementations.student_association_handler import (
    StudentAssociationHandler,
)
from services.essay_lifecycle_service.models_db import (
    BatchEssayTracker as BatchEssayTrackerDB,
)
from services.essay_lifecycle_service.models_db import (
    EssayStateDB,
)
from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    BatchLifecyclePublisherProtocol,
    EssayRepositoryProtocol,
)


class TestStudentAssociationHandler:
    """Test suite for StudentAssociationHandler."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock essay repository."""
        return AsyncMock(spec=EssayRepositoryProtocol)

    @pytest.fixture
    def mock_batch_tracker(self) -> AsyncMock:
        """Create mock batch essay tracker."""
        return AsyncMock(spec=BatchEssayTracker)

    @pytest.fixture
    def mock_batch_lifecycle_publisher(self) -> AsyncMock:
        """Create mock batch lifecycle publisher."""
        return AsyncMock(spec=BatchLifecyclePublisherProtocol)

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
        mock_batch_lifecycle_publisher: AsyncMock,
        mock_session_factory: MagicMock,
    ) -> StudentAssociationHandler:
        """Create handler instance with mocked dependencies."""
        return StudentAssociationHandler(
            repository=mock_repository,
            batch_tracker=mock_batch_tracker,
            batch_lifecycle_publisher=mock_batch_lifecycle_publisher,
            session_factory=mock_session_factory,
        )

    @pytest.fixture
    def sample_associations(self) -> list[StudentAssociationConfirmation]:
        """Create sample student association confirmations."""
        return [
            StudentAssociationConfirmation(
                essay_id=str(uuid4()),
                student_id=f"student_{i}",
                confidence_score=0.95,
                validation_method="human",
                validated_by="teacher_123",
                validated_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

    @pytest.fixture
    def sample_essay_states(
        self, sample_associations: list[StudentAssociationConfirmation]
    ) -> list[EssayStateDB]:
        """Create sample essay states matching the associations."""
        return [
            EssayStateDB(
                essay_id=assoc.essay_id,
                batch_id=str(uuid4()),
                text_storage_id=str(uuid4()),
                processing_metadata={"course_code": "ENG5"},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            for assoc in sample_associations
        ]

    @pytest.fixture
    def batch_status(self) -> BatchEssayTrackerDB:
        """Create sample batch status."""
        return BatchEssayTrackerDB(
            batch_id=str(uuid4()),
            expected_essay_ids=["essay1", "essay2", "essay3"],
            available_slots=["essay1", "essay2", "essay3"],
            expected_count=3,
            course_code="ENG5",
            essay_instructions="Write a descriptive essay",
            user_id="teacher_123",
            correlation_id=str(uuid4()),
        )

    @pytest.fixture
    def event_data(
        self, sample_associations: list[StudentAssociationConfirmation]
    ) -> StudentAssociationsConfirmedV1:
        """Create sample student associations confirmed event."""
        return StudentAssociationsConfirmedV1(
            event_name=ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED,
            batch_id=str(uuid4()),
            class_id="class_456",
            course_code=CourseCode.ENG5,
            associations=sample_associations,
            timeout_triggered=False,
            validation_summary={"human": 3},
        )

    @pytest.mark.asyncio
    async def test_routes_associations_to_batch_essays_ready(
        self,
        handler: StudentAssociationHandler,
        mock_repository: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_batch_lifecycle_publisher: AsyncMock,
        mock_session_factory: MagicMock,
        event_data: StudentAssociationsConfirmedV1,
        sample_essay_states: list[EssayStateDB],
        batch_status: BatchEssayTrackerDB,
    ) -> None:
        """Test that handler acts as stateless router, publishing BatchEssaysReady without updating essay state."""
        # Arrange
        correlation_id = uuid4()

        # Mock repository to return essay states
        mock_repository.get_essay_state.side_effect = sample_essay_states

        # Mock batch tracker to return status and completion check
        mock_batch_tracker.get_batch_status.return_value = batch_status

        # Create mock BatchEssaysReady event for check_batch_completion
        from common_core.metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata

        mock_ready_event = BatchEssaysReady(
            batch_id=event_data.batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id=assoc.essay_id,
                    text_storage_id=f"storage-{i}",
                    student_name=f"Student {i}",
                )
                for i, assoc in enumerate(event_data.associations)
            ],
            metadata=SystemProcessingMetadata(
                entity_id=event_data.batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test essay instructions",
            class_type="REGULAR",
        )
        mock_batch_tracker.check_batch_completion.return_value = (mock_ready_event, correlation_id)

        # Act
        await handler.handle_student_associations_confirmed(event_data, correlation_id)

        # Assert - ELS acts as stateless event router during Phase 1
        # Should retrieve batch status to get ready essays
        mock_batch_tracker.get_batch_status.assert_called_once_with(event_data.batch_id)
        mock_batch_tracker.check_batch_completion.assert_called_once_with(event_data.batch_id)

        # Should clean up Redis state after successful routing
        mock_batch_tracker.cleanup_batch.assert_called_once_with(event_data.batch_id)

    @pytest.mark.asyncio
    async def test_publishes_batch_essays_ready(
        self,
        handler: StudentAssociationHandler,
        mock_repository: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_batch_lifecycle_publisher: AsyncMock,
        mock_session_factory: MagicMock,
        event_data: StudentAssociationsConfirmedV1,
        sample_essay_states: list[EssayStateDB],
        batch_status: BatchEssayTrackerDB,
    ) -> None:
        """Test that handler publishes BatchEssaysReady event after processing associations."""
        # Arrange
        correlation_id = uuid4()
        session = mock_session_factory.return_value.__aenter__.return_value

        # Mock repository to return essay states
        mock_repository.get_essay_state.side_effect = sample_essay_states

        # Mock batch tracker to return status and completion check
        mock_batch_tracker.get_batch_status.return_value = batch_status

        # Create mock BatchEssaysReady event for check_batch_completion
        from common_core.metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata

        mock_ready_event = BatchEssaysReady(
            batch_id=event_data.batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id=assoc.essay_id,
                    text_storage_id=f"storage-{i}",
                    student_name=f"Student {i}",
                )
                for i, assoc in enumerate(event_data.associations)
            ],
            metadata=SystemProcessingMetadata(
                entity_id=event_data.batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test essay instructions",
            class_type="REGULAR",
        )
        mock_batch_tracker.check_batch_completion.return_value = (mock_ready_event, correlation_id)

        # Act
        await handler.handle_student_associations_confirmed(event_data, correlation_id)

        # Assert
        # Should publish BatchEssaysReady event
        mock_batch_lifecycle_publisher.publish_batch_essays_ready.assert_called_once()

        call_args = mock_batch_lifecycle_publisher.publish_batch_essays_ready.call_args
        event_published = call_args.kwargs["event_data"]

        assert isinstance(event_published, BatchEssaysReady)
        assert event_published.batch_id == event_data.batch_id
        assert len(event_published.ready_essays) == len(sample_essay_states)
        assert event_published.class_type == "REGULAR"
        assert call_args.kwargs["correlation_id"] == correlation_id
        assert call_args.kwargs["session"] == session

    @pytest.mark.asyncio
    async def test_handles_missing_essays_gracefully(
        self,
        handler: StudentAssociationHandler,
        mock_repository: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_batch_lifecycle_publisher: AsyncMock,
        event_data: StudentAssociationsConfirmedV1,
        batch_status: BatchEssayTrackerDB,
    ) -> None:
        """Test that handler acts as stateless router even when essays might be missing."""
        # Arrange
        correlation_id = uuid4()

        # Mock batch tracker to return status and completion check
        mock_batch_tracker.get_batch_status.return_value = batch_status

        # Create mock BatchEssaysReady event for check_batch_completion
        from common_core.metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata

        mock_ready_event = BatchEssaysReady(
            batch_id=event_data.batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id=assoc.essay_id,
                    text_storage_id=f"storage-{i}",
                    student_name=f"Student {i}",
                )
                for i, assoc in enumerate(event_data.associations)
            ],
            metadata=SystemProcessingMetadata(
                entity_id=event_data.batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test essay instructions",
            class_type="REGULAR",
        )
        mock_batch_tracker.check_batch_completion.return_value = (mock_ready_event, correlation_id)

        # Act - Should not raise exception
        await handler.handle_student_associations_confirmed(event_data, correlation_id)

        # Assert - ELS acts as stateless router, doesn't interact with repository
        # Should not interact with essay repository during stateless routing
        mock_repository.get_essay_state.assert_not_called()
        mock_repository.update_student_association.assert_not_called()

        # Should still publish BatchEssaysReady via routing
        mock_batch_lifecycle_publisher.publish_batch_essays_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleans_up_redis_state_after_routing(
        self,
        handler: StudentAssociationHandler,
        mock_repository: AsyncMock,
        mock_batch_tracker: AsyncMock,
        event_data: StudentAssociationsConfirmedV1,
        batch_status: BatchEssayTrackerDB,
    ) -> None:
        """Test that handler cleans up Redis state after successful event routing."""
        # Arrange
        correlation_id = uuid4()

        # Mock batch tracker to return status and completion check
        mock_batch_tracker.get_batch_status.return_value = batch_status

        # Create mock BatchEssaysReady event for check_batch_completion
        from common_core.metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata

        mock_ready_event = BatchEssaysReady(
            batch_id=event_data.batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id=assoc.essay_id,
                    text_storage_id=f"storage-{i}",
                    student_name=f"Student {i}",
                )
                for i, assoc in enumerate(event_data.associations)
            ],
            metadata=SystemProcessingMetadata(
                entity_id=event_data.batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test essay instructions",
            class_type="REGULAR",
        )
        mock_batch_tracker.check_batch_completion.return_value = (mock_ready_event, correlation_id)

        # Act
        await handler.handle_student_associations_confirmed(event_data, correlation_id)

        # Assert - ELS should clean up Redis state after successful routing
        mock_batch_tracker.cleanup_batch.assert_called_once_with(event_data.batch_id)

        # Should not update any database state during stateless routing
        mock_repository.update_essay_processing_metadata.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_timeout_triggered_associations(
        self,
        handler: StudentAssociationHandler,
        mock_repository: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_batch_lifecycle_publisher: AsyncMock,
        sample_associations: list[StudentAssociationConfirmation],
        batch_status: BatchEssayTrackerDB,
    ) -> None:
        """Test that handler routes timeout-triggered associations correctly."""
        # Arrange
        correlation_id = uuid4()

        # Create timeout-triggered event
        timeout_associations = [
            StudentAssociationConfirmation(
                essay_id=assoc.essay_id,
                student_id=assoc.student_id,
                confidence_score=0.85,
                validation_method="timeout",
                validated_by=None,
                validated_at=datetime.now(UTC),
            )
            for assoc in sample_associations
        ]

        event_data = StudentAssociationsConfirmedV1(
            event_name=ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED,
            batch_id=str(uuid4()),
            class_id="class_456",
            course_code=CourseCode.ENG5,
            associations=timeout_associations,
            timeout_triggered=True,
            validation_summary={"timeout": 3},
        )

        # Mock batch tracker to return status and completion check
        mock_batch_tracker.get_batch_status.return_value = batch_status

        # Create mock BatchEssaysReady event for check_batch_completion
        from common_core.metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata

        mock_ready_event = BatchEssaysReady(
            batch_id=event_data.batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id=assoc.essay_id,
                    text_storage_id=f"storage-{i}",
                    student_name=f"Student {i}",
                )
                for i, assoc in enumerate(event_data.associations)
            ],
            metadata=SystemProcessingMetadata(
                entity_id=event_data.batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test essay instructions",
            class_type="REGULAR",
        )
        mock_batch_tracker.check_batch_completion.return_value = (mock_ready_event, correlation_id)

        # Act
        await handler.handle_student_associations_confirmed(event_data, correlation_id)

        # Assert - ELS acts as stateless router regardless of validation method
        # Should not update any database state
        mock_repository.update_student_association.assert_not_called()

        # Should still publish BatchEssaysReady via routing
        mock_batch_lifecycle_publisher.publish_batch_essays_ready.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_for_missing_batch_status(
        self,
        handler: StudentAssociationHandler,
        mock_batch_tracker: AsyncMock,
        event_data: StudentAssociationsConfirmedV1,
    ) -> None:
        """Test that handler raises error when batch status is not found."""
        # Arrange
        correlation_id = uuid4()

        # Mock batch tracker to return None (not found)
        mock_batch_tracker.get_batch_status.return_value = None

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await handler.handle_student_associations_confirmed(event_data, correlation_id)

        error = exc_info.value
        assert error.error_detail.service == "essay_lifecycle_service"
        assert error.error_detail.operation == "handle_student_associations_confirmed"
        assert (
            f"Batch status not found for batch {event_data.batch_id}" in error.error_detail.message
        )

    @pytest.mark.asyncio
    async def test_uses_correct_course_code_and_language(
        self,
        handler: StudentAssociationHandler,
        mock_batch_tracker: AsyncMock,
        mock_batch_lifecycle_publisher: AsyncMock,
        event_data: StudentAssociationsConfirmedV1,
        batch_status: BatchEssayTrackerDB,
    ) -> None:
        """Test that handler uses course code from event data (not essay metadata)."""
        # Arrange
        correlation_id = uuid4()

        # Mock batch tracker to return status and completion check
        mock_batch_tracker.get_batch_status.return_value = batch_status

        # Create mock BatchEssaysReady event for check_batch_completion
        from common_core.metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata

        mock_ready_event = BatchEssaysReady(
            batch_id=event_data.batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id=assoc.essay_id,
                    text_storage_id=f"storage-{i}",
                    student_name=f"Student {i}",
                )
                for i, assoc in enumerate(event_data.associations)
            ],
            metadata=SystemProcessingMetadata(
                entity_id=event_data.batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test essay instructions",
            class_type="REGULAR",
        )
        mock_batch_tracker.check_batch_completion.return_value = (mock_ready_event, correlation_id)

        # Act
        await handler.handle_student_associations_confirmed(event_data, correlation_id)

        # Assert - ELS uses course code from event data, not essay metadata
        call_args = mock_batch_lifecycle_publisher.publish_batch_essays_ready.call_args
        event_published = call_args.kwargs["event_data"]

        # Should use course code from event data (ENG5), not essay metadata
        assert event_published.course_code == CourseCode.ENG5
        assert event_published.course_language == "en"  # ENG5 is English

    @pytest.mark.asyncio
    async def test_handles_mixed_validation_methods(
        self,
        handler: StudentAssociationHandler,
        mock_repository: AsyncMock,
        mock_batch_tracker: AsyncMock,
        mock_batch_lifecycle_publisher: AsyncMock,
        batch_status: BatchEssayTrackerDB,
    ) -> None:
        """Test that handler routes events with mixed validation methods correctly."""
        # Arrange
        correlation_id = uuid4()

        # Create associations with mixed validation methods
        mixed_associations = [
            StudentAssociationConfirmation(
                essay_id=str(uuid4()),
                student_id="student_1",
                confidence_score=0.95,
                validation_method="human",
                validated_by="teacher_123",
                validated_at=datetime.now(UTC),
            ),
            StudentAssociationConfirmation(
                essay_id=str(uuid4()),
                student_id="student_2",
                confidence_score=0.90,
                validation_method="auto",
                validated_by=None,
                validated_at=datetime.now(UTC),
            ),
            StudentAssociationConfirmation(
                essay_id=str(uuid4()),
                student_id="student_3",
                confidence_score=0.85,
                validation_method="timeout",
                validated_by=None,
                validated_at=datetime.now(UTC),
            ),
        ]

        event_data = StudentAssociationsConfirmedV1(
            event_name=ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED,
            batch_id=str(uuid4()),
            class_id="class_456",
            course_code=CourseCode.ENG5,
            associations=mixed_associations,
            timeout_triggered=False,
            validation_summary={"human": 1, "auto": 1, "timeout": 1},
        )

        # Mock batch tracker to return status and completion check
        mock_batch_tracker.get_batch_status.return_value = batch_status

        # Create mock BatchEssaysReady event for check_batch_completion
        from common_core.metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata

        mock_ready_event = BatchEssaysReady(
            batch_id=event_data.batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id=assoc.essay_id,
                    text_storage_id=f"storage-{i}",
                    student_name=f"Student {i}",
                )
                for i, assoc in enumerate(event_data.associations)
            ],
            metadata=SystemProcessingMetadata(
                entity_id=event_data.batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test essay instructions",
            class_type="REGULAR",
        )
        mock_batch_tracker.check_batch_completion.return_value = (mock_ready_event, correlation_id)

        # Act
        await handler.handle_student_associations_confirmed(event_data, correlation_id)

        # Assert - ELS acts as stateless router regardless of validation methods
        # Should not process individual associations in database
        mock_repository.update_student_association.assert_not_called()

        # Should still publish BatchEssaysReady via routing
        mock_batch_lifecycle_publisher.publish_batch_essays_ready.assert_called_once()
