"""
Unit tests for AssociationTimeoutMonitor event publishing functionality.

Tests the event publishing logic including event structure validation, data accuracy,
timeout-specific fields, correlation ID handling, and multiple event scenarios.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.status_enums import AssociationValidationMethod
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.class_management_service.implementations.association_timeout_monitor import (
    AssociationTimeoutMonitor,
)
from services.class_management_service.models_db import EssayStudentAssociation, Student, UserClass
from services.class_management_service.protocols import ClassEventPublisherProtocol


class TestTimeoutMonitorEventPublishing:
    """Test suite for timeout monitor's event publishing functionality."""

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
        essay_id: Any | None = None,
        student_id: Any | None = None,
        confidence_score: float = 0.8,
        hours_old: int = 25,
        course_code: CourseCode = CourseCode.ENG5,
    ) -> MagicMock:
        """Helper to create mock association with default values."""
        association = MagicMock(spec=EssayStudentAssociation)
        association.batch_id = batch_id or uuid4()
        association.class_id = class_id or uuid4()
        association.essay_id = essay_id or uuid4()
        association.student_id = student_id or uuid4()
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
    async def test_event_published_for_single_high_confidence_association(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test event is published for single high confidence association."""
        batch_id = uuid4()
        class_id = uuid4()
        essay_id = uuid4()
        student_id = uuid4()

        # Create high confidence association
        association = self.create_mock_association(
            batch_id=batch_id,
            class_id=class_id,
            essay_id=essay_id,
            student_id=student_id,
            confidence_score=0.9,
            course_code=CourseCode.ENG5,
        )

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert event was published
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args

        # Verify call arguments
        assert call_args.kwargs["batch_id"] == str(batch_id)
        assert call_args.kwargs["class_id"] == str(class_id)
        assert call_args.kwargs["course_code"] == CourseCode.ENG5
        assert call_args.kwargs["timeout_triggered"] is True
        assert isinstance(call_args.kwargs["correlation_id"], type(uuid4()))

        # Verify associations data structure
        associations = call_args.kwargs["associations"]
        assert len(associations) == 1
        assert associations[0]["essay_id"] == str(essay_id)
        assert associations[0]["student_id"] == str(student_id)
        assert associations[0]["confidence_score"] == 0.9
        assert associations[0]["validation_method"] == AssociationValidationMethod.TIMEOUT.value
        assert associations[0]["validated_by"] == "SYSTEM_TIMEOUT"
        assert isinstance(associations[0]["validated_at"], datetime)

        # Verify validation summary
        validation_summary = call_args.kwargs["validation_summary"]
        assert validation_summary["total_associations"] == 1
        assert validation_summary["confirmed"] == 1
        assert validation_summary["rejected"] == 0

    @pytest.mark.asyncio
    async def test_event_published_for_single_low_confidence_association(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test event is published for single low confidence association with UNKNOWN student."""
        batch_id = uuid4()
        class_id = uuid4()
        essay_id = uuid4()
        original_student_id = uuid4()
        unknown_student_id = uuid4()

        # Create low confidence association
        association = self.create_mock_association(
            batch_id=batch_id,
            class_id=class_id,
            essay_id=essay_id,
            student_id=original_student_id,
            confidence_score=0.4,
            course_code=CourseCode.SV1,
        )

        # Mock existing UNKNOWN student
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = unknown_student_id

        # Set up query results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = [association]

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing_unknown

        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert event was published
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args

        # Verify basic event data
        assert call_args.kwargs["batch_id"] == str(batch_id)
        assert call_args.kwargs["class_id"] == str(class_id)
        assert call_args.kwargs["course_code"] == CourseCode.SV1
        assert call_args.kwargs["timeout_triggered"] is True

        # Verify association uses UNKNOWN student and has 0.0 confidence
        associations = call_args.kwargs["associations"]
        assert len(associations) == 1
        assert associations[0]["essay_id"] == str(essay_id)
        assert associations[0]["student_id"] == str(unknown_student_id)
        assert associations[0]["confidence_score"] == 0.0  # Reset for UNKNOWN
        assert associations[0]["validation_method"] == AssociationValidationMethod.TIMEOUT.value

    @pytest.mark.asyncio
    async def test_event_data_structure_for_multiple_associations(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test event data structure for batch with multiple associations."""
        batch_id = uuid4()
        class_id = uuid4()

        # Create multiple associations with different confidence levels
        high_conf_association = self.create_mock_association(
            batch_id=batch_id, class_id=class_id, confidence_score=0.85
        )
        medium_conf_association = self.create_mock_association(
            batch_id=batch_id, class_id=class_id, confidence_score=0.75
        )
        low_conf_association = self.create_mock_association(
            batch_id=batch_id, class_id=class_id, confidence_score=0.5
        )

        associations = [high_conf_association, medium_conf_association, low_conf_association]

        # Mock existing UNKNOWN student for low confidence
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = uuid4()

        # Set up query results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = associations

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing_unknown

        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert event was published
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        associations_data = call_args.kwargs["associations"]

        # Verify all associations are included
        assert len(associations_data) == 3

        # Verify confidence scores - high and medium keep original, low gets 0.0
        confidence_scores = {a["confidence_score"] for a in associations_data}
        assert 0.85 in confidence_scores  # High confidence preserved
        assert 0.75 in confidence_scores  # Medium confidence preserved
        assert 0.0 in confidence_scores  # Low confidence reset to 0.0 for UNKNOWN

        # Verify all have timeout validation
        for assoc_data in associations_data:
            assert assoc_data["validation_method"] == AssociationValidationMethod.TIMEOUT.value
            assert assoc_data["validated_by"] == "SYSTEM_TIMEOUT"
            assert isinstance(assoc_data["validated_at"], datetime)

        # Verify validation summary
        validation_summary = call_args.kwargs["validation_summary"]
        assert validation_summary["total_associations"] == 3
        assert validation_summary["confirmed"] == 3
        assert validation_summary["rejected"] == 0

    @pytest.mark.asyncio
    async def test_separate_events_for_different_batches(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that separate events are published for different batch/class combinations."""
        batch_id_1 = uuid4()
        batch_id_2 = uuid4()
        class_id = uuid4()

        # Create associations for different batches
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

        # Assert two separate events published
        assert mock_event_publisher.publish_student_associations_confirmed.call_count == 2

        # Verify each batch gets its own event
        calls = mock_event_publisher.publish_student_associations_confirmed.call_args_list
        batch_ids = {call.kwargs["batch_id"] for call in calls}
        assert batch_ids == {str(batch_id_1), str(batch_id_2)}

        # Verify association counts per batch
        for call in calls:
            if call.kwargs["batch_id"] == str(batch_id_1):
                assert len(call.kwargs["associations"]) == 2
            else:
                assert len(call.kwargs["associations"]) == 1

    @pytest.mark.asyncio
    async def test_course_code_propagation_in_events(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that course codes are correctly propagated to events."""
        # Test different course codes
        test_cases = [
            (CourseCode.ENG5, "English 5"),
            (CourseCode.ENG6, "English 6"),
            (CourseCode.SV1, "Svenska 1"),
            (CourseCode.SV2, "Svenska 2"),
        ]

        for course_code, _ in test_cases:
            # Reset mock
            mock_event_publisher.reset_mock()

            # Create association with specific course code
            association = self.create_mock_association(course_code=course_code)

            # Set up query result
            mock_result = MagicMock()
            mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
            mock_session.execute.return_value = mock_result

            # Act
            await timeout_monitor._check_and_process_timeouts()

            # Assert correct course code in event
            call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
            assert call_args.kwargs["course_code"] == course_code

    @pytest.mark.asyncio
    async def test_correlation_id_generation_and_propagation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that correlation IDs are generated per monitoring cycle and propagated."""
        # Create association
        association = self.create_mock_association()

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act - call twice to verify different correlation IDs
        await timeout_monitor._check_and_process_timeouts()
        first_correlation_id = (
            mock_event_publisher.publish_student_associations_confirmed.call_args.kwargs[
                "correlation_id"
            ]
        )

        # Reset and call again
        mock_event_publisher.reset_mock()
        await timeout_monitor._check_and_process_timeouts()
        second_correlation_id = (
            mock_event_publisher.publish_student_associations_confirmed.call_args.kwargs[
                "correlation_id"
            ]
        )

        # Assert different correlation IDs generated
        assert first_correlation_id != second_correlation_id
        assert isinstance(first_correlation_id, type(uuid4()))
        assert isinstance(second_correlation_id, type(uuid4()))

    @pytest.mark.asyncio
    async def test_no_event_published_when_no_associations(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that no event is published when no associations need processing."""
        # Set up empty query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert no event published
        mock_event_publisher.publish_student_associations_confirmed.assert_not_called()

    @pytest.mark.asyncio
    async def test_timeout_triggered_flag_always_true(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that timeout_triggered flag is always True for timeout monitor events."""
        # Create associations with different confidence levels
        associations = [
            self.create_mock_association(confidence_score=0.9),  # High confidence
            self.create_mock_association(confidence_score=0.3),  # Low confidence
        ]

        # Mock UNKNOWN student for low confidence
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = uuid4()

        # Set up query results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = associations

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = existing_unknown

        mock_session.execute.side_effect = [mock_result_1, mock_result_2]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert timeout_triggered is always True
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        assert call_args.kwargs["timeout_triggered"] is True

    @pytest.mark.asyncio
    async def test_validation_summary_structure_and_values(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test validation summary structure and correct count values."""
        batch_id = uuid4()
        class_id = uuid4()

        # Create batch with 5 associations - 2 high confidence, 3 low confidence
        associations = [
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.9
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.8
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.5
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.3
            ),
            self.create_mock_association(
                batch_id=batch_id, class_id=class_id, confidence_score=0.1
            ),
        ]

        # Mock UNKNOWN student for low confidence associations
        existing_unknown = MagicMock(spec=Student)
        existing_unknown.id = uuid4()

        # Set up query results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = associations

        # For low confidence associations, need to mock UNKNOWN student query
        # (called once per low-confidence association)
        # There are 3 low confidence associations, so 3 calls to check for UNKNOWN student
        mock_result_unknown = MagicMock()
        mock_result_unknown.scalar_one_or_none.return_value = existing_unknown

        mock_session.execute.side_effect = [
            mock_result_1,  # Get timed-out associations
            mock_result_unknown,  # Check for UNKNOWN student (1st low-confidence association)
            mock_result_unknown,  # Check for UNKNOWN student (2nd low-confidence association)
            mock_result_unknown,  # Check for UNKNOWN student (3rd low-confidence association)
        ]

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert event was published
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        validation_summary = call_args.kwargs["validation_summary"]

        # Verify structure
        assert isinstance(validation_summary, dict)
        assert "total_associations" in validation_summary
        assert "confirmed" in validation_summary
        assert "rejected" in validation_summary

        # Verify values (timeout monitor confirms all, rejects none)
        assert validation_summary["total_associations"] == 5
        assert validation_summary["confirmed"] == 5
        assert validation_summary["rejected"] == 0

    @pytest.mark.asyncio
    async def test_association_field_types_and_formats(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that association fields in events have correct types and formats."""
        essay_id = uuid4()
        student_id = uuid4()
        association = self.create_mock_association(essay_id=essay_id, student_id=student_id)

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert field types and formats
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        association_data = call_args.kwargs["associations"][0]

        # Verify field types
        assert isinstance(association_data["essay_id"], str)
        assert isinstance(association_data["student_id"], str)
        assert isinstance(association_data["confidence_score"], float)
        assert isinstance(association_data["validation_method"], str)
        assert isinstance(association_data["validated_by"], str)
        assert isinstance(association_data["validated_at"], datetime)

        # Verify field values
        assert association_data["essay_id"] == str(essay_id)
        assert association_data["student_id"] == str(student_id)
        assert association_data["validation_method"] == AssociationValidationMethod.TIMEOUT.value
        assert association_data["validated_by"] == "SYSTEM_TIMEOUT"

    @pytest.mark.asyncio
    async def test_batch_and_class_id_string_conversion(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that batch_id and class_id are properly converted to strings in events."""
        batch_id = uuid4()
        class_id = uuid4()

        association = self.create_mock_association(batch_id=batch_id, class_id=class_id)

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Assert string conversion
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args
        assert call_args.kwargs["batch_id"] == str(batch_id)
        assert call_args.kwargs["class_id"] == str(class_id)
        assert isinstance(call_args.kwargs["batch_id"], str)
        assert isinstance(call_args.kwargs["class_id"], str)

    @pytest.mark.asyncio
    async def test_event_publisher_error_handling(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test behavior when event publisher raises an exception."""
        association = self.create_mock_association()

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Make event publisher raise exception
        mock_event_publisher.publish_student_associations_confirmed.side_effect = RuntimeError(
            "Event publishing failed"
        )

        # Act - should handle error gracefully and continue
        await timeout_monitor._check_and_process_timeouts()

        # Verify event publisher was called (and failed)
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()

        # Verify database rollback was called due to error
        mock_session.rollback.assert_called_once()
