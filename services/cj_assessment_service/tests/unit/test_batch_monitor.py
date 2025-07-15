"""Unit tests for the CJ Assessment batch monitor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from common_core.status_enums import CJBatchStateEnum
from services.cj_assessment_service.batch_monitor import BatchMonitor
from services.cj_assessment_service.models_db import CJBatchState


@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    repo = AsyncMock()
    repo.session = MagicMock()
    return repo


@pytest.fixture
def mock_event_publisher():
    """Create a mock event publisher."""
    return AsyncMock()


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.BATCH_TIMEOUT_HOURS = 4
    settings.BATCH_MONITOR_INTERVAL_MINUTES = 5
    return settings


@pytest.fixture
def batch_monitor(mock_repository, mock_event_publisher, mock_settings):
    """Create a BatchMonitor instance."""
    return BatchMonitor(mock_repository, mock_event_publisher, mock_settings)


class TestBatchMonitor:
    """Test cases for BatchMonitor."""

    async def test_init(self, batch_monitor):
        """Test BatchMonitor initialization."""
        assert batch_monitor.timeout_hours == 4
        assert batch_monitor.monitor_interval_minutes == 5
        assert batch_monitor._running is True

    async def test_handle_stuck_batch_high_progress(self, batch_monitor, mock_repository):
        """Test handling stuck batch with >= 80% progress forces to SCORING."""
        # Create mock batch state with 85% progress
        mock_batch_state = MagicMock(spec=CJBatchState)
        mock_batch_state.batch_id = 123
        mock_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        mock_batch_state.total_comparisons = 100
        mock_batch_state.completed_comparisons = 85
        mock_batch_state.last_activity_at = datetime.now(UTC) - timedelta(hours=5)

        # Mock database operations
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_batch_state
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_repository.session.return_value = mock_session

        # Execute
        await batch_monitor._handle_stuck_batch(mock_batch_state)

        # Verify state was changed to SCORING
        assert mock_batch_state.state == CJBatchStateEnum.SCORING
        assert mock_session.commit.called

    async def test_handle_stuck_batch_low_progress(self, batch_monitor, mock_repository):
        """Test handling stuck batch with < 80% progress marks as FAILED."""
        # Create mock batch state with 50% progress
        mock_batch_state = MagicMock(spec=CJBatchState)
        mock_batch_state.batch_id = 456
        mock_batch_state.state = CJBatchStateEnum.GENERATING_PAIRS
        mock_batch_state.total_comparisons = 100
        mock_batch_state.completed_comparisons = 50
        mock_batch_state.last_activity_at = datetime.now(UTC) - timedelta(hours=5)

        # Mock database operations
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_batch_state
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_repository.session.return_value = mock_session

        # Execute
        await batch_monitor._handle_stuck_batch(mock_batch_state)

        # Verify state was changed to FAILED
        assert mock_batch_state.state == CJBatchStateEnum.FAILED
        assert mock_session.commit.called

    async def test_stop(self, batch_monitor):
        """Test graceful shutdown."""
        assert batch_monitor._running is True
        await batch_monitor.stop()
        assert batch_monitor._running is False
