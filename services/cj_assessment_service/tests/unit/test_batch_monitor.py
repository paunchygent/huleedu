"""Unit tests for the CJ Assessment batch monitor."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import AsyncContextManager
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy.ext.asyncio import AsyncSession

import services.cj_assessment_service.batch_monitor as batch_monitor_module
from services.cj_assessment_service.batch_monitor import BatchMonitor
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)


@pytest.fixture
def mock_session_provider(mock_session: AsyncSession) -> SessionProviderProtocol:
    """Create a mock session provider that yields a real async context manager."""

    class FakeSessionProvider:
        def session(self) -> AsyncContextManager[AsyncSession]:
            @asynccontextmanager
            async def _session() -> AsyncIterator[AsyncSession]:
                yield mock_session

            return _session()

    return FakeSessionProvider()


@pytest.fixture
def mock_session() -> AsyncSession:
    """Create a mock AsyncSession used by session_provider.session()."""
    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def mock_batch_repository() -> AsyncMock:
    """Create a mock batch repository."""
    return AsyncMock(spec=CJBatchRepositoryProtocol)


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Create a mock event publisher."""
    return AsyncMock()


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.BATCH_TIMEOUT_HOURS = 4
    settings.BATCH_MONITOR_INTERVAL_MINUTES = 5
    return settings


@pytest.fixture
def batch_monitor(
    mock_session_provider: SessionProviderProtocol,
    mock_batch_repository: AsyncMock,
    mock_event_publisher: AsyncMock,
    mock_settings: MagicMock,
) -> BatchMonitor:
    """Create a BatchMonitor instance."""
    from services.cj_assessment_service.cj_core_logic.grade_projector import (
        GradeProjector,
    )
    from services.cj_assessment_service.protocols import CJEssayRepositoryProtocol

    mock_content_client = AsyncMock(spec=ContentClientProtocol)
    mock_essay_repository = AsyncMock(spec=CJEssayRepositoryProtocol)
    mock_grade_projector = AsyncMock(spec=GradeProjector)
    return BatchMonitor(
        session_provider=mock_session_provider,
        batch_repository=mock_batch_repository,
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        essay_repository=mock_essay_repository,
        event_publisher=mock_event_publisher,
        content_client=mock_content_client,
        settings=mock_settings,
        grade_projector=mock_grade_projector,
    )


@pytest.fixture(autouse=True)
def patch_batch_finalizer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid deep BatchFinalizer logic in BatchMonitor unit tests."""

    class FakeBatchFinalizer:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def finalize_scoring(self, *_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(batch_monitor_module, "BatchFinalizer", FakeBatchFinalizer)


class TestBatchMonitor:
    """Test cases for BatchMonitor."""

    async def test_init(self, batch_monitor: BatchMonitor) -> None:
        """Test BatchMonitor initialization."""
        assert batch_monitor.timeout_hours == 4
        assert batch_monitor.monitor_interval_minutes == 5
        assert batch_monitor._running is True

    async def test_handle_stuck_batch_high_progress(
        self,
        batch_monitor: BatchMonitor,
        mock_batch_repository: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test handling stuck batch with >= 80% progress forces to SCORING."""
        # Create mock batch state with 85% progress
        mock_batch_state = MagicMock(spec=CJBatchState)
        mock_batch_state.batch_id = 123
        mock_batch_state.state = CJBatchStateEnum.WAITING_CALLBACKS
        mock_batch_state.total_comparisons = 100
        mock_batch_state.completed_comparisons = 85
        mock_batch_state.failed_comparisons = 0
        mock_batch_state.last_activity_at = datetime.now(UTC) - timedelta(hours=5)
        mock_batch_state.correlation_id = UUID("00000000-0000-0000-0000-000000000123")
        mock_batch_state.processing_metadata = None
        mock_batch_state.completion_denominator.return_value = 100
        mock_batch_state.batch_upload = MagicMock(spec=CJBatchUpload)
        mock_batch_state.batch_upload.bos_batch_id = "bos-batch-123"
        mock_batch_state.batch_upload.event_correlation_id = str(
            UUID("00000000-0000-0000-0000-000000000123")
        )
        mock_batch_state.batch_upload.created_at = datetime.now(UTC) - timedelta(hours=6)

        mock_session.get.return_value = mock_batch_state.batch_upload

        # Mock batch repository to return the batch state for FOR UPDATE query
        mock_batch_repository.get_batch_state_for_update.return_value = mock_batch_state

        # Execute
        await batch_monitor._handle_stuck_batch(mock_batch_state)

        # Verify state was changed to SCORING
        assert mock_batch_state.state == CJBatchStateEnum.SCORING
        assert mock_session.commit.called
        mock_batch_repository.get_batch_state_for_update.assert_called_once()

    async def test_handle_stuck_batch_low_progress(
        self,
        batch_monitor: BatchMonitor,
        mock_batch_repository: AsyncMock,
        mock_session: AsyncMock,
    ) -> None:
        """Test handling stuck batch with < 80% progress marks as FAILED."""
        # Create mock batch state with 50% progress
        mock_batch_state = MagicMock(spec=CJBatchState)
        mock_batch_state.batch_id = 456
        mock_batch_state.state = CJBatchStateEnum.GENERATING_PAIRS
        mock_batch_state.total_comparisons = 100
        mock_batch_state.completed_comparisons = 50
        mock_batch_state.failed_comparisons = 0
        mock_batch_state.last_activity_at = datetime.now(UTC) - timedelta(hours=5)
        mock_batch_state.correlation_id = UUID("00000000-0000-0000-0000-000000000456")
        mock_batch_state.processing_metadata = None
        mock_batch_state.completion_denominator.return_value = 100
        mock_batch_state.batch_upload = MagicMock(spec=CJBatchUpload)
        mock_batch_state.batch_upload.bos_batch_id = "bos-batch-456"
        mock_batch_state.batch_upload.event_correlation_id = str(
            UUID("00000000-0000-0000-0000-000000000456")
        )
        mock_batch_state.batch_upload.created_at = datetime.now(UTC) - timedelta(hours=6)

        mock_session.get.return_value = mock_batch_state.batch_upload

        # Mock batch repository to return the batch state for FOR UPDATE query
        mock_batch_repository.get_batch_state_for_update.return_value = mock_batch_state

        # Execute
        await batch_monitor._handle_stuck_batch(mock_batch_state)

        # Verify state was changed to FAILED
        assert mock_batch_state.state == CJBatchStateEnum.FAILED
        assert mock_session.commit.called
        mock_batch_repository.get_batch_state_for_update.assert_called_once()

    async def test_stop(self, batch_monitor: BatchMonitor) -> None:
        """Test graceful shutdown."""
        assert batch_monitor._running is True
        await batch_monitor.stop()
        assert batch_monitor._running is False
