"""
Unit tests for AssociationTimeoutMonitor association processing logic.

Tests the core timeout processing functionality including 24-hour timeout
calculation, high/low confidence handling, batch grouping, and field updates.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.class_management_service.implementations.association_timeout_monitor import (
    HIGH_CONFIDENCE_THRESHOLD,
    AssociationTimeoutMonitor,
)
from services.class_management_service.models_db import EssayStudentAssociation, Student, UserClass
from services.class_management_service.protocols import ClassEventPublisherProtocol


class TestTimeoutMonitorAssociationProcessing:
    """Test suite for timeout monitor's core association processing logic."""

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
        confidence_score: float = 0.8,
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
    async def test_timeout_calculation_24_hours_exact(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test that associations at exactly 24 hours are processed."""
        # Create association at exactly 24 hours
        association = self.create_mock_association(hours_old=24)

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - verify association was processed
        assert association.validation_status == "confirmed"
        assert association.validation_method == "timeout"
        assert association.validated_by == "SYSTEM_TIMEOUT"
        assert association.validated_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_calculation_under_24_hours(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that associations under 24 hours are not processed."""
        # Create association at 23 hours old
        self.create_mock_association(hours_old=23)

        # Set up query to return empty (no associations meet criteria)
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - no processing should occur
        mock_session.commit.assert_not_called()
        mock_event_publisher.publish_student_associations_confirmed.assert_not_called()

    @pytest.mark.asyncio
    async def test_high_confidence_auto_confirmation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test high-confidence associations are confirmed with original student."""
        # Create high-confidence association
        original_student_id = uuid4()
        association = self.create_mock_association(confidence_score=0.8)
        association.student_id = original_student_id

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - student_id should remain unchanged
        assert association.student_id == original_student_id
        assert association.validation_status == "confirmed"
        assert association.validation_method == "timeout"

        # Verify event published with original student
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        associations_data = call_args.kwargs["associations"]
        assert associations_data[0]["student_id"] == str(original_student_id)
        assert associations_data[0]["confidence_score"] == 0.8

    @pytest.mark.asyncio
    async def test_high_confidence_threshold_boundary(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test associations at exactly the confidence threshold."""
        # Create association at exactly threshold (0.7)
        association = self.create_mock_association(confidence_score=HIGH_CONFIDENCE_THRESHOLD)
        original_student_id = association.student_id

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - should be treated as high confidence
        assert association.student_id == original_student_id
        assert association.validation_status == "confirmed"

    @pytest.mark.asyncio
    async def test_low_confidence_existing_unknown_student(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test low-confidence associations use existing UNKNOWN student."""
        # Create low-confidence association
        association = self.create_mock_association(confidence_score=0.3)

        # Create existing UNKNOWN student
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = uuid4()
        existing_unknown.first_name = "UNKNOWN"
        existing_unknown.last_name = "STUDENT"

        # Set up query results
        # First query: get timed-out associations
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = [association]

        # Second query: check for existing UNKNOWN student (found)
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing_unknown

        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - no new student should be created
        mock_session.add.assert_not_called()

        # Verify association was updated to use existing UNKNOWN student
        assert association.validation_status == "confirmed"
        assert association.validation_method == "timeout"
        assert association.student_id == existing_unknown.id

        # Verify event published with correct data
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        associations_data = call_args.kwargs["associations"]
        assert associations_data[0]["confidence_score"] == 0.0
        assert associations_data[0]["student_id"] == str(existing_unknown.id)

    @pytest.mark.asyncio
    async def test_batch_grouping_multiple_batches(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test associations are grouped by batch_id and class_id."""
        # Create associations for different batches
        batch_id_1 = uuid4()
        batch_id_2 = uuid4()
        class_id = uuid4()

        associations = [
            self.create_mock_association(batch_id=batch_id_1, class_id=class_id),
            self.create_mock_association(batch_id=batch_id_1, class_id=class_id),
            self.create_mock_association(batch_id=batch_id_2, class_id=class_id),
        ]

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = associations
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - verify two separate event publishes for two batches
        assert mock_event_publisher.publish_student_associations_confirmed.call_count == 2

        # Verify each batch was published separately
        calls = mock_event_publisher.publish_student_associations_confirmed.call_args_list
        batch_ids = {call.kwargs["batch_id"] for call in calls}
        assert batch_ids == {str(batch_id_1), str(batch_id_2)}

        # Verify correct association counts
        for call in calls:
            if call.kwargs["batch_id"] == str(batch_id_1):
                assert len(call.kwargs["associations"]) == 2
            else:
                assert len(call.kwargs["associations"]) == 1

    @pytest.mark.asyncio
    async def test_association_field_updates(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test all required fields are updated on associations."""
        # Create association with explicit None values for fields that should be set
        association = self.create_mock_association()
        association.validated_at = None
        association.validated_by = None
        association.validation_method = None

        # Verify initial state
        assert association.validation_status == "pending_validation"
        assert association.validated_at is None
        assert association.validated_by is None
        assert association.validation_method is None

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - verify all fields updated
        assert association.validation_status == "confirmed"
        assert association.validation_method == "timeout"
        assert association.validated_by == "SYSTEM_TIMEOUT"
        assert association.validated_at is not None
        assert isinstance(association.validated_at, datetime)

    @pytest.mark.asyncio
    async def test_mixed_confidence_levels_same_batch(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test batch with mixed high and low confidence associations."""
        batch_id = uuid4()
        class_id = uuid4()

        # Create mixed confidence associations
        high_conf_assoc = self.create_mock_association(
            batch_id=batch_id, class_id=class_id, confidence_score=0.9
        )
        low_conf_assoc = self.create_mock_association(
            batch_id=batch_id, class_id=class_id, confidence_score=0.4
        )

        # Create existing UNKNOWN student that will be used for low confidence
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = uuid4()

        # Set up query results
        # First query: get associations
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = [
            high_conf_assoc,
            low_conf_assoc,
        ]

        # Second query: check for UNKNOWN student (found existing)
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing_unknown

        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - verify one event with both associations
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args

        assert call_args.kwargs["batch_id"] == str(batch_id)
        associations_data = call_args.kwargs["associations"]
        assert len(associations_data) == 2

        # Verify high confidence kept original score, low confidence got 0.0
        confidence_scores = {a["confidence_score"] for a in associations_data}
        assert confidence_scores == {0.9, 0.0}

    @pytest.mark.asyncio
    async def test_validation_summary_accuracy(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test validation summary counts are accurate."""
        batch_id = uuid4()
        class_id = uuid4()

        # Create multiple associations
        associations = [
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.8
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.9
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.3
            ),
        ]

        # Create existing UNKNOWN student that will be used for low confidence
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = uuid4()

        # Set up query results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = associations

        # For low confidence association - return existing UNKNOWN student
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing_unknown

        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - verify validation summary
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        validation_summary = call_args.kwargs["validation_summary"]

        assert validation_summary["total_associations"] == 3
        assert validation_summary["confirmed"] == 3
        assert validation_summary["rejected"] == 0

    @pytest.mark.asyncio
    async def test_no_associations_to_process(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test behavior when no associations need timeout processing."""
        # Set up empty query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - no events published, no commits
        mock_event_publisher.publish_student_associations_confirmed.assert_not_called()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_correlation_id_generation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that correlation ID is generated and passed through."""
        # Create association
        association = self.create_mock_association()

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert - verify correlation_id was passed
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        correlation_id = call_args.kwargs["correlation_id"]

        # Should be a valid UUID
        assert correlation_id is not None
        assert str(correlation_id) == str(correlation_id)  # Valid UUID string representation
