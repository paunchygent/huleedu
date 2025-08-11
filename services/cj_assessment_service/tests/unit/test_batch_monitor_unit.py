"""Unit tests for BatchMonitor stuck batch detection and recovery strategies.

Tests the core business logic for batch recovery decisions:
- Progress calculation behavior
- Recovery strategy thresholds (80% rule)
- State transition logic
- Event publishing behavior
- Metrics recording
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import CJAssessmentFailedV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, CJBatchStateEnum, ProcessingStage

from services.cj_assessment_service.batch_monitor import BatchMonitor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload


class TestBatchMonitorRecoveryStrategy:
    """Test BatchMonitor recovery strategy behavior."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Create mock repository with database session."""
        from unittest.mock import Mock

        repository = AsyncMock()

        # Create a proper async context manager that actually works
        class MockAsyncContextManager:
            def __init__(self, session_mock: Any) -> None:
                self.session_mock = session_mock

            async def __aenter__(self) -> Any:
                return self.session_mock

            async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                return None

        # Create the session mock
        session_mock = AsyncMock()
        context_manager = MockAsyncContextManager(session_mock)

        # IMPORTANT: session() is NOT async - it returns an async context manager
        # So use regular Mock, not AsyncMock
        repository.session = Mock(return_value=context_manager)

        return repository

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Create mock event publisher."""
        return AsyncMock()

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create mock content client."""
        return AsyncMock()

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings with test values."""
        settings = MagicMock(spec=Settings)
        settings.BATCH_TIMEOUT_HOURS = 2
        settings.BATCH_MONITOR_INTERVAL_MINUTES = 5
        return settings

    @pytest.fixture
    def batch_monitor(
        self,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        mock_content_client: AsyncMock,
        mock_settings: Settings,
    ) -> BatchMonitor:
        """Create BatchMonitor instance with mocked dependencies."""
        return BatchMonitor(
            repository=mock_repository,
            event_publisher=mock_event_publisher,
            content_client=mock_content_client,
            settings=mock_settings,
        )

    @pytest.fixture
    def sample_batch_upload(self) -> CJBatchUpload:
        """Create sample batch upload for testing."""
        return CJBatchUpload(
            id=1,
            bos_batch_id="batch-123",
            event_correlation_id=str(uuid4()),
            language="en",
            course_code="ENG5",
            essay_instructions="Test instructions",
            expected_essay_count=10,
        )

    def create_stuck_batch_state(
        self,
        batch_id: int,
        completed: int,
        total: int,
        state: CJBatchStateEnum = CJBatchStateEnum.WAITING_CALLBACKS,
        batch_upload: CJBatchUpload | None = None,
    ) -> CJBatchState:
        """Create a stuck batch state for testing."""
        return CJBatchState(
            batch_id=batch_id,
            state=state,
            completed_comparisons=completed,
            total_comparisons=total,
            submitted_comparisons=total,
            failed_comparisons=0,
            partial_scoring_triggered=False,
            completion_threshold_pct=80,
            current_iteration=1,
            last_activity_at=datetime.now(UTC)
            - timedelta(hours=3),  # Stuck (older than 2h timeout)
            batch_upload=batch_upload,
        )

    @pytest.mark.asyncio
    async def test_recovery_strategy_high_progress_forces_scoring(
        self,
        batch_monitor: BatchMonitor,
        mock_repository: AsyncMock,
        sample_batch_upload: CJBatchUpload,
    ) -> None:
        """Test that batches >= 80% complete are forced to SCORING state."""
        # Arrange: 85% complete batch (17/20 comparisons)
        batch_state = self.create_stuck_batch_state(
            batch_id=1,
            completed=17,
            total=20,
            batch_upload=sample_batch_upload,
        )

        # Mock database operations - the real code has MULTIPLE execute calls
        session = mock_repository.session.return_value.session_mock
        # Create a separate batch_state_db object that represents what comes from DB
        batch_state_db = self.create_stuck_batch_state(
            batch_id=1, completed=17, total=20, batch_upload=sample_batch_upload
        )
        # Fix: scalar_one should return actual objects, not coroutines
        from unittest.mock import Mock

        execute_result1 = Mock()
        execute_result1.scalar_one.return_value = batch_state_db
        execute_result2 = Mock()
        execute_result2.scalar_one.return_value = batch_state_db  # Same object for update query
        session.execute.side_effect = [execute_result1, execute_result2]

        # Act: Handle the stuck batch
        await batch_monitor._handle_stuck_batch(batch_state)

        # Assert: The database batch state should be forced to SCORING state
        assert batch_state_db.state == CJBatchStateEnum.SCORING
        assert batch_state_db.processing_metadata is not None
        assert "forced_to_scoring" in batch_state_db.processing_metadata
        assert batch_state_db.processing_metadata["forced_to_scoring"]["progress_pct"] == 85.0
        assert batch_state_db.processing_metadata["forced_to_scoring"]["reason"] == "stuck_timeout"

        # Verify database commit was called
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_recovery_strategy_low_progress_marks_failed(
        self,
        batch_monitor: BatchMonitor,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        sample_batch_upload: CJBatchUpload,
    ) -> None:
        """Test that batches < 80% complete are marked as FAILED."""
        # Arrange: 60% complete batch (6/10 comparisons)
        batch_state = self.create_stuck_batch_state(
            batch_id=1,
            completed=6,
            total=10,
            batch_upload=sample_batch_upload,
        )

        # Mock database operations
        session = mock_repository.session.return_value.session_mock
        # Create a separate batch_state_db object that represents what comes from DB
        batch_state_db = self.create_stuck_batch_state(
            batch_id=1, completed=6, total=10, batch_upload=sample_batch_upload
        )
        # Fix: scalar_one should return actual objects, not coroutines
        from unittest.mock import Mock

        execute_result1 = Mock()
        execute_result1.scalar_one.return_value = batch_state_db
        execute_result2 = Mock()
        execute_result2.scalar_one.return_value = batch_state_db  # Same object for update query
        session.execute.side_effect = [execute_result1, execute_result2]
        session.get.return_value = sample_batch_upload

        # Act: Handle the stuck batch
        await batch_monitor._handle_stuck_batch(batch_state)

        # Assert: Database batch state should be marked as FAILED
        assert batch_state_db.state == CJBatchStateEnum.FAILED
        assert batch_state_db.processing_metadata is not None
        assert "failed_reason" in batch_state_db.processing_metadata
        assert batch_state_db.processing_metadata["failed_reason"]["progress_pct"] == 60.0
        assert (
            batch_state_db.processing_metadata["failed_reason"]["reason"]
            == "stuck_timeout_insufficient_progress"
        )

        # Verify failure event was published
        mock_event_publisher.publish_assessment_failed.assert_called_once()
        call_args = mock_event_publisher.publish_assessment_failed.call_args
        failure_data = call_args[1]["failure_data"]

        assert isinstance(failure_data.data, CJAssessmentFailedV1)
        assert failure_data.data.entity_id == "batch-123"
        assert failure_data.data.status == BatchStatus.FAILED_CRITICALLY
        assert failure_data.data.event_name == ProcessingEvent.CJ_ASSESSMENT_FAILED

        # Verify database commit was called
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_progress_calculation_with_zero_total(
        self,
        batch_monitor: BatchMonitor,
        mock_repository: AsyncMock,
        sample_batch_upload: CJBatchUpload,
    ) -> None:
        """Test progress calculation edge case with zero total comparisons."""
        # Arrange: Batch with zero total comparisons
        batch_state = self.create_stuck_batch_state(
            batch_id=1,
            completed=0,
            total=0,
            batch_upload=sample_batch_upload,
        )

        # Mock database operations
        session = mock_repository.session.return_value.session_mock
        # Create a separate batch_state_db object that represents what comes from DB
        batch_state_db = self.create_stuck_batch_state(
            batch_id=1, completed=0, total=0, batch_upload=sample_batch_upload
        )
        # Fix: scalar_one should return actual objects, not coroutines
        from unittest.mock import Mock

        execute_result1 = Mock()
        execute_result1.scalar_one.return_value = batch_state_db
        execute_result2 = Mock()
        execute_result2.scalar_one.return_value = batch_state_db  # Same object for update query
        session.execute.side_effect = [execute_result1, execute_result2]
        session.get.return_value = sample_batch_upload

        # Act: Handle the stuck batch
        await batch_monitor._handle_stuck_batch(batch_state)

        # Assert: Should be marked as FAILED (0% progress)
        assert batch_state_db.state == CJBatchStateEnum.FAILED
        assert batch_state_db.processing_metadata is not None
        assert batch_state_db.processing_metadata["failed_reason"]["progress_pct"] == 0

    @pytest.mark.asyncio
    async def test_progress_calculation_exactly_eighty_percent(
        self,
        batch_monitor: BatchMonitor,
        mock_repository: AsyncMock,
        sample_batch_upload: CJBatchUpload,
    ) -> None:
        """Test boundary condition: exactly 80% progress."""
        # Arrange: Exactly 80% complete batch (8/10 comparisons)
        batch_state = self.create_stuck_batch_state(
            batch_id=1,
            completed=8,
            total=10,
            batch_upload=sample_batch_upload,
        )

        # Mock database operations
        session = mock_repository.session.return_value.session_mock
        # Create a separate batch_state_db object that represents what comes from DB
        batch_state_db = self.create_stuck_batch_state(
            batch_id=1, completed=8, total=10, batch_upload=sample_batch_upload
        )
        # Fix: scalar_one should return actual objects, not coroutines
        from unittest.mock import Mock

        execute_result1 = Mock()
        execute_result1.scalar_one.return_value = batch_state_db
        execute_result2 = Mock()
        execute_result2.scalar_one.return_value = batch_state_db  # Same object for update query
        session.execute.side_effect = [execute_result1, execute_result2]

        # Act: Handle the stuck batch
        await batch_monitor._handle_stuck_batch(batch_state)

        # Assert: Should be forced to SCORING (>= 80% threshold)
        assert batch_state_db.state == CJBatchStateEnum.SCORING
        assert batch_state_db.processing_metadata is not None
        assert batch_state_db.processing_metadata["forced_to_scoring"]["progress_pct"] == 80.0

    @pytest.mark.asyncio
    async def test_system_metadata_generation_for_failure_event(
        self,
        batch_monitor: BatchMonitor,
        mock_repository: AsyncMock,
        mock_event_publisher: AsyncMock,
        sample_batch_upload: CJBatchUpload,
    ) -> None:
        """Test proper SystemProcessingMetadata generation for failure events."""
        # Arrange: Low progress batch
        batch_state = self.create_stuck_batch_state(
            batch_id=1,
            completed=3,
            total=10,
            batch_upload=sample_batch_upload,
        )

        # Mock database operations
        session = mock_repository.session.return_value.session_mock
        # Create a separate batch_state_db object that represents what comes from DB
        batch_state_db = self.create_stuck_batch_state(
            batch_id=1, completed=3, total=10, batch_upload=sample_batch_upload
        )
        # Fix: scalar_one should return actual objects, not coroutines
        from unittest.mock import Mock

        execute_result1 = Mock()
        execute_result1.scalar_one.return_value = batch_state_db
        execute_result2 = Mock()
        execute_result2.scalar_one.return_value = batch_state_db  # Same object for update query
        session.execute.side_effect = [execute_result1, execute_result2]
        session.get.return_value = sample_batch_upload

        # Act: Handle the stuck batch
        await batch_monitor._handle_stuck_batch(batch_state)

        # Assert: Verify SystemProcessingMetadata structure
        mock_event_publisher.publish_assessment_failed.assert_called_once()
        call_args = mock_event_publisher.publish_assessment_failed.call_args
        failure_data = call_args[1]["failure_data"]

        system_metadata = failure_data.data.system_metadata
        assert isinstance(system_metadata, SystemProcessingMetadata)
        assert system_metadata.entity_id == "batch-123"
        assert system_metadata.entity_type == "batch"
        assert system_metadata.processing_stage == ProcessingStage.FAILED
        assert system_metadata.event == ProcessingEvent.CJ_ASSESSMENT_FAILED.value

    @pytest.mark.asyncio
    async def test_batch_state_last_activity_update(
        self,
        batch_monitor: BatchMonitor,
        mock_repository: AsyncMock,
        sample_batch_upload: CJBatchUpload,
    ) -> None:
        """Test that last_activity_at is updated during recovery."""
        # Arrange
        old_timestamp = datetime.now(UTC) - timedelta(hours=5)
        batch_state = self.create_stuck_batch_state(
            batch_id=1,
            completed=9,
            total=10,
            batch_upload=sample_batch_upload,
        )
        batch_state.last_activity_at = old_timestamp

        # Mock database operations
        session = mock_repository.session.return_value.session_mock
        # Create a separate batch_state_db object that represents what comes from DB
        batch_state_db = self.create_stuck_batch_state(
            batch_id=1, completed=9, total=10, batch_upload=sample_batch_upload
        )
        batch_state_db.last_activity_at = old_timestamp  # Set old timestamp on DB object
        # Fix: scalar_one should return actual objects, not coroutines
        from unittest.mock import Mock

        execute_result1 = Mock()
        execute_result1.scalar_one.return_value = batch_state_db
        execute_result2 = Mock()
        execute_result2.scalar_one.return_value = batch_state_db  # Same object for update query
        session.execute.side_effect = [execute_result1, execute_result2]

        # Act: Handle the stuck batch
        await batch_monitor._handle_stuck_batch(batch_state)

        # Assert: last_activity_at should be updated to current time on the DB object
        assert batch_state_db.last_activity_at > old_timestamp
        assert (datetime.now(UTC) - batch_state_db.last_activity_at).total_seconds() < 5
