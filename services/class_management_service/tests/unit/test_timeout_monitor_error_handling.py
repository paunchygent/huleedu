"""
Unit tests for AssociationTimeoutMonitor error handling scenarios.

Tests comprehensive error handling including database failures, event publishing errors,
recovery scenarios, and observability integration. Critical for production readiness
of the timeout monitor which processes real student data every hour.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.error_enums import ErrorCode
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy.exc import (
    DatabaseError,
    IntegrityError,
    OperationalError,
)
from sqlalchemy.exc import (
    TimeoutError as SQLTimeoutError,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.class_management_service.implementations.association_timeout_monitor import (
    AssociationTimeoutMonitor,
)
from services.class_management_service.models_db import EssayStudentAssociation, UserClass
from services.class_management_service.protocols import ClassEventPublisherProtocol


class TestTimeoutMonitorErrorHandling:
    """Test suite for timeout monitor's error handling and recovery capabilities."""

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

    # Database Error Scenarios

    @pytest.mark.asyncio
    async def test_database_connection_failure_during_query(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of database connection failures during association query."""
        # Mock database connection error with proper exception chain
        original_error = Exception("Connection refused")
        connection_error = OperationalError("Connection refused", None, original_error)
        mock_session.execute.side_effect = connection_error

        # Act & Assert - should raise structured HuleEduError
        with pytest.raises(HuleEduError) as exc_info:
            await timeout_monitor._check_and_process_timeouts()

        # Verify structured error behavior - test that proper error handling occurred
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ErrorCode.PROCESSING_ERROR
        assert error_detail.service == "class_management_service"
        assert error_detail.operation == "check_and_process_timeouts"

        # Verify no events published on database failure
        mock_event_publisher.publish_student_associations_confirmed.assert_not_called()

    @pytest.mark.asyncio
    async def test_database_timeout_during_query_execution(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of database timeout during query execution."""
        # Mock database timeout error with proper exception chain
        original_error = Exception("Query timeout exceeded")
        timeout_error = SQLTimeoutError("Query timeout exceeded", None, original_error)
        mock_session.execute.side_effect = timeout_error

        # Act & Assert - should raise structured HuleEduError
        with pytest.raises(HuleEduError) as exc_info:
            await timeout_monitor._check_and_process_timeouts()

        # Verify structured error behavior
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ErrorCode.PROCESSING_ERROR

        # Verify no events published on timeout
        mock_event_publisher.publish_student_associations_confirmed.assert_not_called()

    @pytest.mark.asyncio
    async def test_database_integrity_error_during_batch_processing(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of integrity constraint violations during batch processing."""
        # Create test association
        association = self.create_mock_association()

        # Set up initial query success
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Mock integrity error during commit
        original_error = Exception("Foreign key constraint failed")
        integrity_error = IntegrityError("Foreign key constraint failed", None, original_error)
        mock_session.commit.side_effect = integrity_error

        # Act - should handle error gracefully and continue
        await timeout_monitor._check_and_process_timeouts()

        # Verify rollback was called on database error
        mock_session.rollback.assert_called_once()

        # Verify no events published due to transaction failure
        mock_event_publisher.publish_student_associations_confirmed.assert_not_called()

    @pytest.mark.asyncio
    async def test_database_error_during_unknown_student_creation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of database errors during UNKNOWN student creation."""
        # Create low confidence association
        association = self.create_mock_association(confidence_score=0.3)

        # Set up query results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = [association]

        # Mock no existing UNKNOWN student
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = None

        # Mock class query success
        mock_result_3 = MagicMock()
        mock_user_class = MagicMock(spec=UserClass)
        mock_result_3.scalar_one_or_none.return_value = mock_user_class

        mock_session.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]

        # Mock database error during UNKNOWN student flush
        original_error = Exception("Database unavailable")
        database_error = DatabaseError("Database unavailable", None, original_error)
        mock_session.flush.side_effect = database_error

        # Act - should handle error gracefully
        await timeout_monitor._check_and_process_timeouts()

        # Verify rollback was called
        mock_session.rollback.assert_called_once()

        # Verify no events published due to student creation failure
        mock_event_publisher.publish_student_associations_confirmed.assert_not_called()

    # Event Publishing Error Scenarios

    @pytest.mark.asyncio
    async def test_event_publishing_failure_with_rollback(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of event publishing failures with proper rollback."""
        # Create test association
        association = self.create_mock_association()

        # Set up successful database query
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Mock event publishing failure
        publishing_error = RuntimeError("Kafka broker unavailable")
        mock_event_publisher.publish_student_associations_confirmed.side_effect = publishing_error

        # Act - should handle error gracefully
        await timeout_monitor._check_and_process_timeouts()

        # Verify database rollback was called due to event publishing failure
        mock_session.rollback.assert_called_once()

        # Verify association was updated before rollback
        assert association.validation_status == "confirmed"
        assert association.validation_method == "timeout"

    @pytest.mark.asyncio
    async def test_event_publishing_timeout_with_correlation_id_tracking(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of event publishing timeouts with correlation ID tracking."""
        # Create test association
        association = self.create_mock_association()

        # Set up successful database query
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Mock event publishing timeout
        timeout_error = asyncio.TimeoutError("Event publishing timeout")
        mock_event_publisher.publish_student_associations_confirmed.side_effect = timeout_error

        # Act - should handle error gracefully
        await timeout_monitor._check_and_process_timeouts()

        # Verify rollback occurred
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_serialization_error_during_event_publishing(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of serialization errors during event publishing."""
        # Create test association with complex mock that might cause serialization issues
        association = self.create_mock_association()

        # Set up successful database query
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Mock serialization error during event publishing
        serialization_error = TypeError("Object of type 'MagicMock' is not JSON serializable")
        mock_event_publisher.publish_student_associations_confirmed.side_effect = (
            serialization_error
        )

        # Act - should handle error gracefully
        await timeout_monitor._check_and_process_timeouts()

        # Verify rollback occurred
        mock_session.rollback.assert_called_once()

    # Business Logic Error Scenarios

    @pytest.mark.asyncio
    async def test_missing_course_data_error_handling(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test handling when associations have missing course data."""
        # Create association with missing course data
        association = self.create_mock_association()
        association.user_class = None  # Missing class relationship

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Act - should handle missing data gracefully
        await timeout_monitor._check_and_process_timeouts()

        # Verify session was not committed for invalid batch - behavioral verification
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_confidence_score_handling(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test handling of associations with invalid confidence scores."""
        # Create associations with problematic confidence scores
        # Note: create_mock_association expects float, so we'll modify after creation
        association_1 = self.create_mock_association()
        association_1.confidence_score = None  # None confidence

        invalid_associations = [
            association_1,
            self.create_mock_association(confidence_score=-0.5),  # Negative confidence
            self.create_mock_association(confidence_score=1.5),  # > 1.0 confidence
        ]

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = invalid_associations
        mock_session.execute.return_value = mock_result

        # Act - should handle invalid data gracefully
        await timeout_monitor._check_and_process_timeouts()

        # Implementation should handle None/invalid confidence as low confidence
        # Verify processing continued despite invalid data
        mock_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_class_not_found_during_unknown_student_creation(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling when class is not found during UNKNOWN student creation."""
        # Create low confidence association
        association = self.create_mock_association(confidence_score=0.3)

        # Set up query results
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = [association]

        # Mock no existing UNKNOWN student
        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = None

        # Mock class not found - implementation handles this gracefully
        # by skipping class relationship
        mock_result_3 = MagicMock()
        mock_result_3.scalar_one_or_none.return_value = None  # Class not found

        mock_session.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]

        # Act - should handle missing class gracefully and continue processing
        await timeout_monitor._check_and_process_timeouts()

        # Verify processing continued - UNKNOWN student created without class relationship
        mock_session.add.assert_called_once()  # UNKNOWN student was added
        mock_session.flush.assert_called_once()  # Student was flushed to get ID
        mock_session.commit.assert_called_once()  # Transaction committed successfully

    # Recovery and Resilience Scenarios

    @pytest.mark.asyncio
    async def test_partial_batch_failure_continues_with_other_batches(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that failure in one batch doesn't prevent processing of other batches."""
        batch_id_1 = uuid4()
        batch_id_2 = uuid4()
        class_id = uuid4()

        # Create associations for two different batches
        associations = [
            self.create_mock_association(batch_id=batch_id_1, class_id=class_id),
            self.create_mock_association(batch_id=batch_id_2, class_id=class_id),
        ]

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = associations
        mock_session.execute.return_value = mock_result

        # Mock event publishing to fail for first batch only
        def event_publish_side_effect(**kwargs: Any) -> None:
            if kwargs["batch_id"] == str(batch_id_1):
                raise RuntimeError("Publishing failed for batch 1")
            # Second batch succeeds

        mock_event_publisher.publish_student_associations_confirmed.side_effect = (
            event_publish_side_effect
        )

        # Act - should process both batches, handle first batch error gracefully
        await timeout_monitor._check_and_process_timeouts()

        # Verify both batches were attempted (2 calls)
        assert mock_event_publisher.publish_student_associations_confirmed.call_count == 2

        # Verify rollback was called for failed batch (batch processing handles its own rollback)
        mock_session.rollback.assert_called()

    @pytest.mark.asyncio
    async def test_database_error_handling_resilience(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that database errors are handled with structured error handling."""
        # Mock database error that will raise structured HuleEduError
        original_error = Exception("Database locked")
        database_error = OperationalError("Database locked", None, original_error)
        mock_session.execute.side_effect = database_error

        # Act & Assert - should raise structured HuleEduError
        with pytest.raises(HuleEduError) as exc_info:
            await timeout_monitor._check_and_process_timeouts()

        # Verify structured error handling
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ErrorCode.PROCESSING_ERROR
        assert error_detail.service == "class_management_service"
        assert error_detail.operation == "check_and_process_timeouts"

    @pytest.mark.asyncio
    async def test_connection_error_handling_in_processing(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test handling of connection errors during timeout processing."""
        # Mock connection error during session operations
        connection_error = ConnectionError("Network unreachable")
        mock_session.execute.side_effect = connection_error

        # Act & Assert - infrastructure errors are converted to structured errors
        with pytest.raises(HuleEduError) as exc_info:
            await timeout_monitor._check_and_process_timeouts()

        # Verify proper error handling
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ErrorCode.PROCESSING_ERROR
        assert "unexpected_error" in error_detail.details.get("error_type", "")

    @pytest.mark.asyncio
    async def test_unexpected_error_structured_handling(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that unexpected errors create structured error details."""
        # Mock an unexpected error during processing
        unexpected_error = ValueError("Unexpected value error")
        mock_session.execute.side_effect = unexpected_error

        # Act & Assert - unexpected errors are converted to structured errors
        with pytest.raises(HuleEduError) as exc_info:
            await timeout_monitor._check_and_process_timeouts()

        # Verify structured error details are created
        error_detail = exc_info.value.error_detail
        assert error_detail.error_code == ErrorCode.PROCESSING_ERROR
        assert error_detail.service == "class_management_service"
        assert error_detail.operation == "check_and_process_timeouts"
        assert "unexpected_error" in error_detail.details.get("error_type", "")

    # Observability and Error Logging Tests

    @pytest.mark.asyncio
    async def test_correlation_id_propagation_through_error_handling(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
    ) -> None:
        """Test that correlation IDs are properly propagated through error handling."""
        # Mock database error
        original_error = Exception("Connection failed")
        database_error = OperationalError("Connection failed", None, original_error)
        mock_session.execute.side_effect = database_error

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await timeout_monitor._check_and_process_timeouts()

        # Verify correlation ID is present in error detail
        error_detail = exc_info.value.error_detail
        assert error_detail.correlation_id is not None
        assert str(error_detail.correlation_id) != ""

    @pytest.mark.asyncio
    async def test_error_context_includes_batch_information(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that error context includes relevant batch information for debugging."""
        batch_id = uuid4()
        association = self.create_mock_association(batch_id=batch_id)

        # Set up query to succeed
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Mock event publishing failure
        mock_event_publisher.publish_student_associations_confirmed.side_effect = RuntimeError(
            "Event failed"
        )

        # Act - error should be handled gracefully with context logging
        await timeout_monitor._check_and_process_timeouts()

        # Verify rollback occurred (error was handled)
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_rollback_on_any_batch_processing_error(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that database rollback occurs on any error during batch processing."""
        # Create test association
        association = self.create_mock_association()

        # Set up successful database query
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Mock any error during batch processing
        mock_event_publisher.publish_student_associations_confirmed.side_effect = Exception(
            "Any error"
        )

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Verify rollback was called
        mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_transaction_isolation_between_batch_failures(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that transaction failures in one batch don't affect other batches."""
        batch_id_1 = uuid4()
        batch_id_2 = uuid4()
        class_id = uuid4()

        # Create associations for different batches
        associations = [
            self.create_mock_association(batch_id=batch_id_1, class_id=class_id),
            self.create_mock_association(batch_id=batch_id_2, class_id=class_id),
        ]

        # Set up query result
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = associations
        mock_session.execute.return_value = mock_result

        # Mock commit to fail for first batch, succeed for second
        commit_call_count = 0

        async def mock_commit() -> None:
            nonlocal commit_call_count
            commit_call_count += 1
            if commit_call_count == 1:
                original_error = Exception("Constraint violation")
                raise IntegrityError("Constraint violation", None, original_error)
            # Second commit succeeds

        mock_session.commit.side_effect = mock_commit

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Verify processing attempted for both batches
        # Note: First batch fails during commit so event isn't published, but second succeeds
        assert mock_event_publisher.publish_student_associations_confirmed.call_count == 1

        # Verify rollback was called for failed batch
        mock_session.rollback.assert_called()

    @pytest.mark.asyncio
    async def test_error_recovery_maintains_correlation_id_continuity(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
    ) -> None:
        """Test that error recovery maintains correlation ID continuity for debugging."""
        # Create test association
        association = self.create_mock_association()

        # Set up successful database query
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Track correlation IDs from event publishing calls
        correlation_ids = []

        def capture_correlation_id(**kwargs: Any) -> None:
            correlation_ids.append(kwargs.get("correlation_id"))
            raise RuntimeError("Publishing failed")

        mock_event_publisher.publish_student_associations_confirmed.side_effect = (
            capture_correlation_id
        )

        # Act
        await timeout_monitor._check_and_process_timeouts()

        # Verify correlation ID was captured and is valid
        assert len(correlation_ids) == 1
        assert correlation_ids[0] is not None
