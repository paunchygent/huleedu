"""
Unit tests for AssociationTimeoutMonitor lifecycle management.

Tests the core start/stop/restart functionality and error recovery behavior
using dependency injection and behavior verification instead of mocking internals.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.class_management_service.implementations.association_timeout_monitor import (
    CHECK_INTERVAL_MINUTES,
    AssociationTimeoutMonitor,
)
from services.class_management_service.models_db import EssayStudentAssociation
from services.class_management_service.protocols import ClassEventPublisherProtocol


class TestTimeoutMonitorLifecycle:
    """Test suite for timeout monitor lifecycle management using dependency injection."""

    @pytest.fixture
    def mock_session(self) -> AsyncMock:
        """Create mock database session."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Set up proper async mock chain for session.execute()
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        return mock_session

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
    def mock_sleep(self) -> AsyncMock:
        """Mock asyncio.sleep to eliminate timing in tests."""
        return AsyncMock()

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

    @pytest.mark.asyncio
    async def test_start_monitor_success(self, timeout_monitor: AssociationTimeoutMonitor) -> None:
        """Test that monitor starts successfully and creates background task."""
        # Verify initial state
        assert not timeout_monitor._running
        assert timeout_monitor._monitor_task is None

        # Act
        await timeout_monitor.start()

        # Assert - verify state changes and task creation
        assert timeout_monitor._running is True
        assert timeout_monitor._monitor_task is not None
        assert isinstance(timeout_monitor._monitor_task, asyncio.Task)
        assert not timeout_monitor._monitor_task.done()

        # Clean up
        await timeout_monitor.stop()

    @pytest.mark.asyncio
    async def test_start_monitor_already_running(
        self, timeout_monitor: AssociationTimeoutMonitor
    ) -> None:
        """Test that starting already running monitor is idempotent."""
        # Start monitor first time
        await timeout_monitor.start()
        original_task = timeout_monitor._monitor_task

        # Try to start again
        await timeout_monitor.start()

        # Assert - should be same task, no new task created
        assert timeout_monitor._monitor_task is original_task
        assert timeout_monitor._running is True

        # Clean up
        await timeout_monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_monitor_success(self, timeout_monitor: AssociationTimeoutMonitor) -> None:
        """Test that monitor stops cleanly."""
        # Start monitor
        await timeout_monitor.start()
        assert timeout_monitor._running is True

        # Stop monitor
        await timeout_monitor.stop()

        # Assert - verify state changes and task completion
        assert timeout_monitor._running is False
        if timeout_monitor._monitor_task:
            assert timeout_monitor._monitor_task.done()

    @pytest.mark.asyncio
    async def test_stop_monitor_when_not_running(
        self, timeout_monitor: AssociationTimeoutMonitor
    ) -> None:
        """Test that stopping non-running monitor handles gracefully."""
        # Verify initial state
        assert not timeout_monitor._running
        assert timeout_monitor._monitor_task is None

        # Should not raise exception
        await timeout_monitor.stop()

        # State should remain unchanged
        assert not timeout_monitor._running
        assert timeout_monitor._monitor_task is None

    @pytest.mark.asyncio
    async def test_restart_monitor_after_stop(
        self, timeout_monitor: AssociationTimeoutMonitor
    ) -> None:
        """Test that monitor can be restarted after being stopped."""
        # Start, stop, then restart
        await timeout_monitor.start()
        first_task = timeout_monitor._monitor_task

        await timeout_monitor.stop()
        assert timeout_monitor._running is False

        await timeout_monitor.start()
        second_task = timeout_monitor._monitor_task

        # Assert restart worked with new task
        assert timeout_monitor._running is True
        assert second_task is not first_task
        assert isinstance(second_task, asyncio.Task)

        # Clean up
        await timeout_monitor.stop()

    @pytest.mark.asyncio
    async def test_monitor_processes_database_queries(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_session_factory: MagicMock,
        mock_sleep: AsyncMock,
    ) -> None:
        """Test that monitor makes expected database queries during operation."""
        # Set up session to return no pending associations (already configured in fixture)

        # Configure mock sleep to stop monitor after first call
        async def stop_after_sleep(*args: object) -> None:
            timeout_monitor._running = False

        mock_sleep.side_effect = stop_after_sleep

        # Start monitor with mocked sleep
        with patch(
            "services.class_management_service.implementations.association_timeout_monitor.asyncio.sleep",
            mock_sleep,
        ):
            await timeout_monitor.start()

            # Wait for monitor task to complete
            if timeout_monitor._monitor_task:
                await timeout_monitor._monitor_task

        # Verify database session was used
        mock_session_factory.assert_called()
        mock_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_handles_database_errors(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_sleep: AsyncMock,
    ) -> None:
        """Test that monitor continues operating when database errors occur."""
        # Make database operations fail
        mock_session.execute.side_effect = RuntimeError("Database connection failed")

        # Configure mock sleep to stop monitor after second call (allowing for error recovery)
        call_count = 0

        async def stop_after_two_sleeps(*args: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                timeout_monitor._running = False

        mock_sleep.side_effect = stop_after_two_sleeps

        # Start monitor with mocked sleep
        with patch(
            "services.class_management_service.implementations.association_timeout_monitor.asyncio.sleep",
            mock_sleep,
        ):
            await timeout_monitor.start()

            # Wait for monitor task to complete
            if timeout_monitor._monitor_task:
                await timeout_monitor._monitor_task

        # Verify sleep was called multiple times (showing error recovery)
        assert mock_sleep.call_count >= 2

    @pytest.mark.asyncio
    async def test_monitor_processes_timed_out_associations(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_sleep: AsyncMock,
    ) -> None:
        """Test that monitor processes associations that have timed out."""
        # Create mock timed-out association
        association = MagicMock(spec=EssayStudentAssociation)
        association.batch_id = uuid4()
        association.class_id = uuid4()
        association.essay_id = uuid4()
        association.student_id = uuid4()
        association.confidence_score = 0.8  # High confidence
        association.validation_status = "pending_validation"
        association.created_at = datetime.now(UTC) - timedelta(hours=25)  # Timed out

        # Mock user_class and course for event publishing
        mock_course = MagicMock()
        mock_course.course_code = "ENG5"
        mock_user_class = MagicMock()
        mock_user_class.course = mock_course
        association.user_class = mock_user_class

        # Set up session to return the timed-out association
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Configure mock sleep to stop monitor after first call
        async def stop_after_sleep(*args: object) -> None:
            timeout_monitor._running = False

        mock_sleep.side_effect = stop_after_sleep

        # Start monitor with mocked sleep
        with patch(
            "services.class_management_service.implementations.association_timeout_monitor.asyncio.sleep",
            mock_sleep,
        ):
            await timeout_monitor.start()

            # Wait for monitor task to complete
            if timeout_monitor._monitor_task:
                await timeout_monitor._monitor_task

        # Verify event was published for confirmed association
        mock_event_publisher.publish_student_associations_confirmed.assert_called()

        # Verify association was updated to confirmed status
        assert association.validation_status == "confirmed"
        assert association.validation_method == "timeout"

    @pytest.mark.asyncio
    async def test_monitor_creates_unknown_student_for_low_confidence(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_sleep: AsyncMock,
    ) -> None:
        """Test that monitor creates UNKNOWN student for low confidence associations."""
        # Create mock low-confidence association
        association = MagicMock(spec=EssayStudentAssociation)
        association.batch_id = uuid4()
        association.class_id = uuid4()
        association.essay_id = uuid4()
        association.student_id = uuid4()
        association.confidence_score = 0.5  # Low confidence
        association.validation_status = "pending_validation"
        association.created_at = datetime.now(UTC) - timedelta(hours=25)

        # Mock user_class and course
        mock_course = MagicMock()
        mock_course.course_code = "ENG5"
        mock_user_class = MagicMock()
        mock_user_class.course = mock_course
        association.user_class = mock_user_class

        # Mock queries for UNKNOWN student creation
        mock_result_1 = MagicMock()
        mock_result_1.unique.return_value.scalars.return_value.all.return_value = [association]

        mock_result_2 = MagicMock()
        mock_result_2.scalar_one_or_none.return_value = None  # No existing UNKNOWN student

        mock_result_3 = MagicMock()
        mock_result_3.scalar_one_or_none.return_value = mock_user_class  # UserClass for adding

        mock_session.execute.side_effect = [mock_result_1, mock_result_2, mock_result_3]

        # Mock new UNKNOWN student
        mock_unknown_student = MagicMock()
        mock_unknown_student.id = uuid4()
        mock_session.add.return_value = None
        mock_session.flush.return_value = None

        # Configure mock sleep to stop monitor after first call
        async def stop_after_sleep(*args: object) -> None:
            timeout_monitor._running = False

        mock_sleep.side_effect = stop_after_sleep

        # Start monitor with mocked sleep
        with patch(
            "services.class_management_service.implementations.association_timeout_monitor.asyncio.sleep",
            mock_sleep,
        ):
            await timeout_monitor.start()

            # Wait for monitor task to complete
            if timeout_monitor._monitor_task:
                await timeout_monitor._monitor_task

        # Verify UNKNOWN student creation was attempted
        mock_session.add.assert_called()
        mock_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_respects_check_interval(
        self, timeout_monitor: AssociationTimeoutMonitor, mock_sleep: AsyncMock
    ) -> None:
        """Test that monitor calls sleep with correct interval."""

        # Configure mock sleep to stop monitor after first call
        async def stop_after_sleep(seconds: float) -> None:
            # Verify the correct sleep interval is used
            assert seconds == CHECK_INTERVAL_MINUTES * 60
            timeout_monitor._running = False

        mock_sleep.side_effect = stop_after_sleep

        # Start monitor with mocked sleep
        with patch(
            "services.class_management_service.implementations.association_timeout_monitor.asyncio.sleep",
            mock_sleep,
        ):
            await timeout_monitor.start()

            # Wait for monitor task to complete
            if timeout_monitor._monitor_task:
                await timeout_monitor._monitor_task

        # Verify sleep was called with correct interval
        mock_sleep.assert_called_once_with(CHECK_INTERVAL_MINUTES * 60)

    @pytest.mark.asyncio
    async def test_monitor_publishes_events_with_correct_data(
        self,
        timeout_monitor: AssociationTimeoutMonitor,
        mock_session: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_sleep: AsyncMock,
    ) -> None:
        """Test that published events contain correct data structure."""
        # Create mock association with all required fields
        batch_id = uuid4()
        class_id = uuid4()
        association = MagicMock(spec=EssayStudentAssociation)
        association.batch_id = batch_id
        association.class_id = class_id
        association.essay_id = uuid4()
        association.student_id = uuid4()
        association.confidence_score = 0.9
        association.validation_status = "pending_validation"
        association.created_at = datetime.now(UTC) - timedelta(hours=25)

        # Mock course info
        mock_course = MagicMock()
        mock_course.course_code = "ENG5"
        mock_user_class = MagicMock()
        mock_user_class.course = mock_course
        association.user_class = mock_user_class

        # Set up session to return the association
        mock_result = MagicMock()
        mock_result.unique.return_value.scalars.return_value.all.return_value = [association]
        mock_session.execute.return_value = mock_result

        # Configure mock sleep to stop monitor after first call
        async def stop_after_sleep(*args: object) -> None:
            timeout_monitor._running = False

        mock_sleep.side_effect = stop_after_sleep

        # Start monitor with mocked sleep
        with patch(
            "services.class_management_service.implementations.association_timeout_monitor.asyncio.sleep",
            mock_sleep,
        ):
            await timeout_monitor.start()

            # Wait for monitor task to complete
            if timeout_monitor._monitor_task:
                await timeout_monitor._monitor_task

        # Verify event published with correct parameters
        mock_event_publisher.publish_student_associations_confirmed.assert_called_once()
        call_args = mock_event_publisher.publish_student_associations_confirmed.call_args

        assert call_args.kwargs["batch_id"] == str(batch_id)
        assert call_args.kwargs["class_id"] == str(class_id)
        assert call_args.kwargs["course_code"] == "ENG5"
        assert call_args.kwargs["timeout_triggered"] is True
        assert len(call_args.kwargs["associations"]) == 1
