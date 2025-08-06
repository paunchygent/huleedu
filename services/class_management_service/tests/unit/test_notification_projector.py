"""
Unit tests for the NotificationProjector class.

Tests the projection of internal class management events to teacher notifications
following the notification projection pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.class_events import ClassCreatedV1, StudentCreatedV1
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.events.validation_events import (
    StudentAssociation,
    StudentAssociationConfirmation,
    StudentAssociationsConfirmedV1,
    ValidationTimeoutProcessedV1,
)
from common_core.status_enums import AssociationValidationMethod
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory

if TYPE_CHECKING:
    from services.class_management_service.notification_projector import NotificationProjector


@pytest.fixture
def mock_class_repository() -> AsyncMock:
    """Mock class repository for tests."""
    repository = AsyncMock()
    
    # Default: class exists with teacher
    mock_class = Mock()
    mock_class.id = uuid4()
    mock_class.user_id = "teacher-123"
    mock_class.class_designation = "Advanced English"
    repository.get_class_by_id.return_value = mock_class
    
    return repository


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock event publisher for tests."""
    publisher = AsyncMock()
    publisher.publish_class_event = AsyncMock()
    return publisher


@pytest.fixture
def notification_projector(
    mock_class_repository: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> NotificationProjector:
    """Create notification projector with mocked dependencies."""
    from services.class_management_service.notification_projector import NotificationProjector
    
    return NotificationProjector(
        class_repository=mock_class_repository,
        event_publisher=mock_event_publisher,
    )


class TestClassCreatedProjection:
    """Tests for projecting ClassCreatedV1 events to teacher notifications."""

    @pytest.mark.asyncio
    async def test_class_created_projects_to_standard_notification(
        self,
        notification_projector: NotificationProjector,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that class creation projects to STANDARD priority notification."""
        # Arrange
        event = ClassCreatedV1(
            class_id="class-456",
            class_designation="Mathematics 101",
            course_codes=[CourseCode.SV1],
            user_id="teacher-789",
        )

        # Act
        await notification_projector.handle_class_created(event)

        # Assert - verify EventEnvelope was published
        mock_event_publisher.publish_class_event.assert_called_once()
        envelope = mock_event_publisher.publish_class_event.call_args[0][0]
        
        assert isinstance(envelope, EventEnvelope)
        assert envelope.source_service == "class_management_service"
        
        # Extract and verify the notification data
        notification = envelope.data
        assert isinstance(notification, TeacherNotificationRequestedV1)
        assert notification.teacher_id == "teacher-789"
        assert notification.notification_type == "class_created"
        assert notification.category == WebSocketEventCategory.CLASS_MANAGEMENT
        assert notification.priority == NotificationPriority.STANDARD
        assert notification.action_required is False
        assert notification.class_id == "class-456"
        
        # Verify payload content
        assert notification.payload["class_id"] == "class-456"
        assert notification.payload["class_designation"] == "Mathematics 101"
        assert notification.payload["course_codes"] == ["SV1"]
        assert "successfully" in notification.payload["message"].lower()


class TestStudentCreatedProjection:
    """Tests for projecting StudentCreatedV1 events to teacher notifications."""

    @pytest.mark.asyncio
    async def test_student_created_projects_to_low_priority_notification(
        self,
        notification_projector: NotificationProjector,
        mock_class_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that student creation projects to LOW priority notification."""
        # Arrange
        class_id = str(uuid4())
        event = StudentCreatedV1(
            student_id="student-123",
            first_name="Jane",
            last_name="Doe",
            student_email="jane.doe@school.com",
            class_ids=[class_id],
            created_by_user_id="teacher-123",
        )
        
        # Act
        await notification_projector.handle_student_created(event)
        
        # Assert - verify class was fetched
        mock_class_repository.get_class_by_id.assert_called_once_with(UUID(class_id))
        
        # Verify notification was published
        mock_event_publisher.publish_class_event.assert_called_once()
        envelope = mock_event_publisher.publish_class_event.call_args[0][0]
        
        notification = envelope.data
        assert isinstance(notification, TeacherNotificationRequestedV1)
        assert notification.teacher_id == "teacher-123"
        assert notification.notification_type == "student_added_to_class"
        assert notification.category == WebSocketEventCategory.CLASS_MANAGEMENT
        assert notification.priority == NotificationPriority.LOW
        assert notification.action_required is False
        
        # Verify payload
        assert notification.payload["student_id"] == "student-123"
        assert notification.payload["student_name"] == "Jane Doe"
        assert notification.payload["class_designation"] == "Advanced English"

    @pytest.mark.asyncio
    async def test_student_created_without_class_ids_skips_notification(
        self,
        notification_projector: NotificationProjector,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that student creation without class IDs doesn't create notification."""
        # Arrange
        event = StudentCreatedV1(
            student_id="student-456",
            first_name="John",
            last_name="Smith",
            student_email=None,
            class_ids=[],  # Empty class list
            created_by_user_id="teacher-789",
        )
        
        # Act
        await notification_projector.handle_student_created(event)
        
        # Assert - no notification published
        mock_event_publisher.publish_class_event.assert_not_called()

    @pytest.mark.asyncio
    async def test_student_created_with_nonexistent_class_skips_notification(
        self,
        notification_projector: NotificationProjector,
        mock_class_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that student creation with non-existent class doesn't create notification."""
        # Arrange
        mock_class_repository.get_class_by_id.return_value = None  # Class doesn't exist
        
        event = StudentCreatedV1(
            student_id="student-789",
            first_name="Alice",
            last_name="Wonder",
            student_email="alice@school.com",
            class_ids=[str(uuid4())],
            created_by_user_id="teacher-456",
        )
        
        # Act
        await notification_projector.handle_student_created(event)
        
        # Assert - no notification published
        mock_event_publisher.publish_class_event.assert_not_called()


class TestValidationTimeoutProcessedProjection:
    """Tests for projecting ValidationTimeoutProcessedV1 events to teacher notifications."""

    @pytest.mark.asyncio
    async def test_validation_timeout_projects_to_immediate_priority_notification(
        self,
        notification_projector: NotificationProjector,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that validation timeout projects to IMMEDIATE priority notification."""
        # Arrange
        batch_id = str(uuid4())
        from datetime import UTC, datetime
        
        event = ValidationTimeoutProcessedV1(
            event_name=ProcessingEvent.VALIDATION_TIMEOUT_PROCESSED,
            batch_id=batch_id,
            user_id="teacher-555",
            timeout_hours=24,
            auto_confirmed_associations=[
                StudentAssociation(
                    essay_id="essay-1",
                    student_first_name="Erik",
                    student_last_name="Andersson",
                    student_email="erik@school.com",
                    confidence_score=0.92,
                    is_confirmed=True,
                ),
                StudentAssociation(
                    essay_id="essay-2",
                    student_first_name="Anna",
                    student_last_name="Svensson",
                    student_email=None,
                    confidence_score=0.88,
                    is_confirmed=True,
                ),
            ],
            guest_essays=["essay-3", "essay-4"],  # Required field
            guest_class_created=False,  # Required field
            guest_class_id=None,
            processing_timestamp=datetime.now(UTC),
        )
        
        # Act
        await notification_projector.handle_validation_timeout_processed(event)
        
        # Assert
        mock_event_publisher.publish_class_event.assert_called_once()
        envelope = mock_event_publisher.publish_class_event.call_args[0][0]
        
        notification = envelope.data
        assert isinstance(notification, TeacherNotificationRequestedV1)
        assert notification.teacher_id == "teacher-555"
        assert notification.notification_type == "validation_timeout_processed"
        assert notification.category == WebSocketEventCategory.STUDENT_WORKFLOW
        assert notification.priority == NotificationPriority.IMMEDIATE
        assert notification.action_required is False  # Already auto-confirmed
        assert notification.batch_id == batch_id
        
        # Verify payload
        assert notification.payload["auto_confirmed_count"] == 2
        assert notification.payload["timeout_hours"] == 24
        assert len(notification.payload["auto_confirmed_associations"]) == 2
        assert notification.payload["auto_confirmed_associations"][0]["student_name"] == "Erik Andersson"


class TestStudentAssociationsConfirmedProjection:
    """Tests for projecting StudentAssociationsConfirmedV1 events to teacher notifications."""

    @pytest.mark.asyncio
    async def test_associations_confirmed_projects_to_high_priority_notification(
        self,
        notification_projector: NotificationProjector,
        mock_class_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that manual confirmations project to HIGH priority notification."""
        # Arrange
        batch_id = str(uuid4())
        class_id = str(uuid4())
        
        event = StudentAssociationsConfirmedV1(
            event_name=ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED,
            batch_id=batch_id,
            class_id=class_id,
            course_code=CourseCode.ENG5,
            associations=[
                StudentAssociationConfirmation(
                    essay_id="essay-1",
                    student_id="student-1",
                    confidence_score=0.95,
                    validation_method=AssociationValidationMethod.HUMAN,
                    validated_by="teacher-123",
                ),
                StudentAssociationConfirmation(
                    essay_id="essay-2",
                    student_id="student-2",
                    confidence_score=0.85,
                    validation_method=AssociationValidationMethod.TIMEOUT,
                    validated_by=None,
                ),
                StudentAssociationConfirmation(
                    essay_id="essay-3",
                    student_id=None,  # No match found
                    confidence_score=0.0,
                    validation_method=AssociationValidationMethod.HUMAN,
                    validated_by="teacher-123",
                ),
            ],
            timeout_triggered=False,
            validation_summary={"human": 2, "timeout": 1},
        )
        
        # Act
        await notification_projector.handle_student_associations_confirmed(event)
        
        # Assert - verify class was fetched for teacher_id
        mock_class_repository.get_class_by_id.assert_called_once_with(UUID(class_id))
        
        # Verify notification was published
        mock_event_publisher.publish_class_event.assert_called_once()
        envelope = mock_event_publisher.publish_class_event.call_args[0][0]
        
        notification = envelope.data
        assert isinstance(notification, TeacherNotificationRequestedV1)
        assert notification.teacher_id == "teacher-123"  # From mock class
        assert notification.notification_type == "student_associations_confirmed"
        assert notification.category == WebSocketEventCategory.STUDENT_WORKFLOW
        assert notification.priority == NotificationPriority.HIGH
        assert notification.action_required is False
        assert notification.batch_id == batch_id
        assert notification.class_id == class_id
        
        # Verify payload
        assert notification.payload["confirmed_count"] == 3
        assert notification.payload["timeout_triggered"] is False
        assert notification.payload["validation_summary"] == {"human": 2, "timeout": 1}
        assert len(notification.payload["associations"]) == 3
        
        # Verify association details
        first_assoc = notification.payload["associations"][0]
        assert first_assoc["essay_id"] == "essay-1"
        assert first_assoc["student_id"] == "student-1"
        assert first_assoc["validation_method"] == "human"

    @pytest.mark.asyncio
    async def test_associations_confirmed_with_missing_class_skips_notification(
        self,
        notification_projector: NotificationProjector,
        mock_class_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that associations confirmed with non-existent class doesn't create notification."""
        # Arrange
        mock_class_repository.get_class_by_id.return_value = None  # Class doesn't exist
        
        event = StudentAssociationsConfirmedV1(
            event_name=ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED,
            batch_id=str(uuid4()),
            class_id=str(uuid4()),
            course_code=CourseCode.SV1,
            associations=[],
            timeout_triggered=True,
            validation_summary={},
        )
        
        # Act
        await notification_projector.handle_student_associations_confirmed(event)
        
        # Assert - no notification published
        mock_event_publisher.publish_class_event.assert_not_called()


class TestNotificationPublishingError:
    """Tests for error handling in notification publishing."""

    @pytest.mark.asyncio
    async def test_publishing_error_propagates_exception(
        self,
        notification_projector: NotificationProjector,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that publishing errors are propagated for proper error handling."""
        # Arrange
        mock_event_publisher.publish_class_event.side_effect = Exception("Kafka connection failed")
        
        event = ClassCreatedV1(
            class_id="class-999",
            class_designation="Test Class",
            course_codes=[CourseCode.ENG5],
            user_id="teacher-999",
        )
        
        # Act & Assert
        with pytest.raises(Exception, match="Kafka connection failed"):
            await notification_projector.handle_class_created(event)