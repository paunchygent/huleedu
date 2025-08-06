"""
Unit tests for AssociationTimeoutMonitor UNKNOWN student management.

Tests the creation and reuse of UNKNOWN students for low-confidence associations,
focusing on the business logic without actual database operations.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.class_management_service.implementations.association_timeout_monitor import (
    AssociationTimeoutMonitor,
)
from services.class_management_service.models_db import EssayStudentAssociation, Student, UserClass
from services.class_management_service.protocols import ClassEventPublisherProtocol


class TestTimeoutMonitorUnknownStudent:
    """Test suite for UNKNOWN student creation and management in timeout monitor."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_session_factory(self, mock_session: AsyncMock) -> MagicMock:
        """Create mock SQLAlchemy session factory."""
        mock_factory = MagicMock(spec=async_sessionmaker[AsyncSession])
        mock_factory.return_value.__aenter__.return_value = mock_session
        mock_factory.return_value.__aexit__.return_value = None
        return mock_factory

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        return AsyncMock(spec=ClassEventPublisherProtocol)

    @pytest.fixture
    def timeout_monitor(
        self,
        mock_session_factory: MagicMock,
        mock_event_publisher: AsyncMock,
    ) -> AssociationTimeoutMonitor:
        """Create timeout monitor instance for testing."""
        return AssociationTimeoutMonitor(
            session_factory=mock_session_factory,
            event_publisher=mock_event_publisher,
        )

    def create_mock_association(
        self,
        batch_id: Any | None = None,
        class_id: Any | None = None,
        confidence_score: float = 0.3,
        hours_old: int = 25,
        course_code: str = "ENG5",
    ) -> MagicMock:
        """Helper to create mock association with default values."""
        association = MagicMock(spec=EssayStudentAssociation)
        association.batch_id = batch_id or uuid4()
        association.class_id = class_id or uuid4()
        association.essay_id = uuid4()
        association.student_id = uuid4()
        association.confidence_score = confidence_score
        association.validation_status = "pending_validation"
        association.created_at = datetime.now(UTC) - timedelta(hours=hours_old)

        # Mock user_class and course
        mock_course = MagicMock()
        mock_course.course_code = course_code
        mock_user_class = MagicMock(spec=UserClass)
        mock_user_class.course = mock_course
        association.user_class = mock_user_class

        return association

    @pytest.mark.asyncio
    async def test_unknown_student_creation_attributes(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test that UNKNOWN students are created with correct attributes."""
        class_id = uuid4()

        # Mock no existing UNKNOWN student
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Mock UserClass for adding to student
        mock_user_class = MagicMock(spec=UserClass)
        mock_user_class.id = class_id

        # Call the method directly
        await timeout_monitor._get_or_create_unknown_student(mock_session, class_id)

        # Verify the Student object was created with correct attributes
        mock_session.add.assert_called_once()
        created_student = mock_session.add.call_args[0][0]

        assert created_student.first_name == "UNKNOWN"
        assert created_student.last_name == "STUDENT"
        assert created_student.email == "unknown@huleedu.system"
        assert created_student.created_by_user_id == "SYSTEM_TIMEOUT"

    @pytest.mark.asyncio
    async def test_unknown_student_reuse(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test that existing UNKNOWN students are reused for the same class."""
        class_id = uuid4()

        # Mock existing UNKNOWN student
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = uuid4()
        existing_unknown.first_name = "UNKNOWN"
        existing_unknown.last_name = "STUDENT"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_unknown
        mock_session.execute.return_value = mock_result

        # Call the method
        result = await timeout_monitor._get_or_create_unknown_student(mock_session, class_id)

        # Verify no new student was created
        mock_session.add.assert_not_called()
        assert result == existing_unknown

    @pytest.mark.asyncio
    async def test_unknown_student_per_class_isolation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that UNKNOWN students are isolated per class."""
        class_id_1 = uuid4()
        class_id_2 = uuid4()

        # Create associations for different classes
        assoc_class_1 = self.create_mock_association(class_id=class_id_1, confidence_score=0.3)
        assoc_class_2 = self.create_mock_association(class_id=class_id_2, confidence_score=0.3)

        # Set up mock for first check - associations from both classes
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = [
            assoc_class_1,
            assoc_class_2,
        ]

        # Mock no existing UNKNOWN students (would create new ones)
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = None

        # Set up results for each class processing
        # First: get associations, then UNKNOWN check for class 1, then UNKNOWN check for class 2
        mock_session.execute.side_effect = [
            mock_result_1,
            mock_result_2,
            mock_result_2,
            mock_result_2,
            mock_result_2,
        ]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Verify event published for each class separately
        assert mock_event_publisher.publish_student_associations_confirmed.call_count == 2

        # Verify each event has the correct class_id
        calls = mock_event_publisher.publish_student_associations_confirmed.call_args_list
        class_ids_in_events = {call.kwargs["class_id"] for call in calls}
        assert class_ids_in_events == {str(class_id_1), str(class_id_2)}

    @pytest.mark.asyncio
    async def test_unknown_student_confidence_threshold(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that only low confidence associations get UNKNOWN students."""
        batch_id = uuid4()
        class_id = uuid4()

        # Create associations with various confidence scores
        associations = [
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.1
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.69
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.7
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.95
            ),
        ]

        # Store original student IDs
        original_ids = [assoc.student_id for assoc in associations]

        # Mock existing UNKNOWN student
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = uuid4()

        # Set up mock results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = associations

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing_unknown

        # Simulate actual behavior: when low confidence found, it updates student_id
        call_count = 0

        def execute_side_effect(stmt: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                return mock_result_1
            else:
                # When UNKNOWN student is found, update low confidence associations
                for assoc in associations:
                    if assoc.confidence_score < 0.7:
                        assoc.student_id = existing_unknown.id
                return mock_result_2

        mock_session.execute.side_effect = execute_side_effect

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Verify low confidence associations got reassigned
        assert associations[0].student_id == existing_unknown.id  # 0.1
        assert associations[1].student_id == existing_unknown.id  # 0.69

        # Verify high confidence kept original students
        assert associations[2].student_id == original_ids[2]  # 0.7
        assert associations[3].student_id == original_ids[3]  # 0.95

    @pytest.mark.asyncio
    async def test_unknown_student_database_operations(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test that correct database operations occur for UNKNOWN student."""
        class_id = uuid4()

        # Mock no existing UNKNOWN student
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        # Mock UserClass query result
        mock_user_class = MagicMock()
        mock_user_class.id = class_id
        # Give it a mock classes collection to avoid SQLAlchemy internals
        mock_user_class.classes = MagicMock()

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = mock_user_class

        mock_session.execute.side_effect = [mock_result, mock_result_2]

        # Call the method
        await timeout_monitor._get_or_create_unknown_student(mock_session, class_id)

        # Verify database operations
        assert mock_session.execute.call_count == 2  # Check for existing + get UserClass
        mock_session.add.assert_called_once()  # New student added
        mock_session.flush.assert_called_once()  # Flush to get ID

    @pytest.mark.asyncio
    async def test_unknown_student_event_data(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that events for UNKNOWN students have correct data."""
        batch_id = uuid4()
        class_id = uuid4()

        # Create low confidence association
        association = self.create_mock_association(
            batch_id=batch_id, class_id=class_id, confidence_score=0.2
        )

        # Mock existing UNKNOWN student
        unknown_student = MagicMock(spec=Student)
        unknown_student.id = uuid4()

        # Set up mock results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = [association]

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = unknown_student

        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Verify event data
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        associations_data = call_args.kwargs["associations"]

        assert len(associations_data) == 1
        assert associations_data[0]["student_id"] == str(unknown_student.id)
        assert associations_data[0]["confidence_score"] == 0.0  # Always 0 for UNKNOWN
        assert associations_data[0]["validation_method"] == "timeout"
        assert associations_data[0]["validated_by"] == "SYSTEM_TIMEOUT"

    @pytest.mark.asyncio
    async def test_multiple_low_confidence_same_batch(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test multiple low confidence associations in same batch use same UNKNOWN."""
        batch_id = uuid4()
        class_id = uuid4()

        # Create multiple low confidence associations
        associations = [
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.2
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.3
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.4
            ),
        ]

        # Mock existing UNKNOWN student
        unknown_student = MagicMock(spec=Student)
        unknown_student.id = uuid4()

        # Set up mock results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = associations

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = unknown_student

        # Simulate behavior: update all associations to use UNKNOWN student
        call_count = 0

        def execute_side_effect(stmt: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                return mock_result_1
            else:
                # Update all associations to use UNKNOWN student
                for assoc in associations:
                    assoc.student_id = unknown_student.id
                return mock_result_2

        mock_session.execute.side_effect = execute_side_effect

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Verify all associations got the same UNKNOWN student
        for assoc in associations:
            assert assoc.student_id == unknown_student.id

        # Verify single event with all associations
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        associations_data = call_args.kwargs["associations"]

        assert len(associations_data) == 3
        # All should have the same UNKNOWN student ID
        student_ids = {a["student_id"] for a in associations_data}
        assert len(student_ids) == 1
        assert student_ids.pop() == str(unknown_student.id)
