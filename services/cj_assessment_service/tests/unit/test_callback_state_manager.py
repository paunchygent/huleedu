"""Unit tests for callback state manager functionality.

Tests behavioral outcomes of callback state management:
- State transitions during callback processing
- Idempotency checks for duplicate callbacks
- Batch completion condition evaluation
- Callback correlation and task reconstruction
- Error handling and recovery paths

Follows Rule 075: Focus on observable behavior, not implementation details.
Uses minimal protocol-compliant mocks without patching or shortcuts.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncContextManager, AsyncGenerator, AsyncIterator, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import CJBatchStateEnum
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.callback_state_manager import (
    _update_batch_completion_counters,
    check_batch_completion_conditions,
    reconstruct_comparison_task,
    update_comparison_result,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import ComparisonTask
from services.cj_assessment_service.models_db import (
    CJBatchState,
    ComparisonPair,
)
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    SessionProviderProtocol,
)


class MockSession:
    """Minimal mock session for behavioral testing."""

    def __init__(
        self, comparison_pair: ComparisonPair | None = None, batch_state: CJBatchState | None = None
    ):
        """Initialize with test data."""
        self.comparison_pair = comparison_pair
        self.batch_state = batch_state
        self.executed_queries: list[Any] = []
        self.execute = AsyncMock(side_effect=self._execute)
        self.committed = False
        self.commit = AsyncMock(side_effect=self._mark_committed)

    async def _execute(self, stmt: Any) -> "MockResult":
        """Track executed queries and return configured results."""
        self.executed_queries.append(stmt)

        if "comparison_pairs" in str(stmt).lower():
            return MockResult(self.comparison_pair)
        if "batch_states" in str(stmt).lower():
            return MockResult(self.batch_state)
        return MockResult(None)

    async def _mark_committed(self) -> None:
        """Track commit calls."""
        self.committed = True


class MockResult:
    """Mock SQLAlchemy result."""

    def __init__(self, result: Any) -> None:
        """Initialize with result value."""
        self.result = result

    def scalar_one_or_none(self) -> Any:
        """Return the configured result."""
        return self.result


@asynccontextmanager
async def mock_session_context(session: MockSession) -> AsyncIterator[AsyncSession]:
    """Create session context manager."""
    yield session  # type: ignore[misc]


class LocalMockSessionProvider(SessionProviderProtocol):
    """Local mock session provider that wraps test MockSession."""

    def __init__(self, session: MockSession):
        """Initialize with mock session."""
        self._session = session

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Return session context manager."""
        return mock_session_context(self._session)


class LocalMockBatchRepository(CJBatchRepositoryProtocol):
    """Local mock batch repository that reads from test MockSession."""

    def __init__(self, session: MockSession):
        """Initialize with mock session."""
        self._session = session

    async def get_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> CJBatchState | None:
        """Get batch state from mock session."""
        state = cast(CJBatchState | None, getattr(self._session, "batch_state", None))
        if state and getattr(state, "batch_id", None) == batch_id:
            return state
        return None

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str,
        language: str,
        course_code: str,
        initial_status: Any,
        expected_essay_count: int,
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> Any:
        """Stub implementation."""
        return None

    async def get_cj_batch_upload(
        self,
        session: AsyncSession,
        cj_batch_id: int,
    ) -> Any | None:
        """Stub implementation."""
        return None

    async def update_cj_batch_status(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        """Stub implementation."""
        pass

    async def update_batch_state(
        self,
        session: AsyncSession,
        batch_id: int,
        state: CJBatchStateEnum,
    ) -> None:
        """Stub implementation."""
        pass

    async def get_batch_state_for_update(
        self,
        session: AsyncSession,
        batch_id: int,
        for_update: bool = False,
    ) -> CJBatchState | None:
        """Stub implementation."""
        return None

    async def update_essay_scores_in_batch(
        self,
        _session: AsyncSession,
        _cj_batch_id: int,
        _scores: dict[str, float],
    ) -> None:
        """Stub implementation."""
        pass

    async def get_stuck_batches(
        self,
        session: AsyncSession,
        states: list[CJBatchStateEnum],
        stuck_threshold: datetime,
    ) -> list[CJBatchState]:
        """Stub implementation."""
        return []

    async def get_batches_ready_for_completion(
        self,
        session: AsyncSession,
    ) -> list[CJBatchState]:
        """Stub implementation."""
        return []


class LocalMockComparisonRepository(CJComparisonRepositoryProtocol):
    """Local mock comparison repository that reads from test MockSession."""

    def __init__(self, session: MockSession):
        """Initialize with mock session."""
        self._session = session

    async def get_comparison_pair_by_correlation_id(
        self,
        session: AsyncSession,
        correlation_id: UUID,
    ) -> ComparisonPair | None:
        """Get comparison pair from mock session."""
        pair = cast(ComparisonPair | None, getattr(self._session, "comparison_pair", None))
        if pair and pair.request_correlation_id == correlation_id:
            return pair
        return None

    async def get_comparison_pair_by_essays(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        essay_a_els_id: str,
        essay_b_els_id: str,
    ) -> ComparisonPair | None:
        """Stub implementation."""
        return None

    async def store_comparison_results(
        self,
        session: AsyncSession,
        results: list[Any],
        cj_batch_id: int,
    ) -> None:
        """Stub implementation."""
        pass

    async def get_comparison_pairs_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[tuple[str, str]]:
        """Stub implementation."""
        return []

    async def get_valid_comparisons_for_batch(
        self,
        session: AsyncSession,
        batch_id: int,
    ) -> list[ComparisonPair]:
        """Stub implementation."""
        return []


def create_comparison_pair(
    cj_batch_id: int = 1,
    request_correlation_id: UUID | None = None,
    essay_a_els_id: str = "essay-a-123",
    essay_b_els_id: str = "essay-b-456",
    winner: str | None = None,
    completed_at: datetime | None = None,
    prompt_text: str = "Compare these essays",
) -> ComparisonPair:
    """Create test comparison pair."""
    pair = ComparisonPair()
    pair.id = 42
    pair.cj_batch_id = cj_batch_id
    pair.request_correlation_id = request_correlation_id or uuid4()
    pair.essay_a_els_id = essay_a_els_id
    pair.essay_b_els_id = essay_b_els_id
    pair.winner = winner
    pair.completed_at = completed_at
    pair.prompt_text = prompt_text
    pair.confidence = None
    pair.justification = None
    pair.raw_llm_response = None
    pair.processing_metadata = {}
    return pair


def create_batch_state(
    batch_id: int = 1,
    state: CJBatchStateEnum = CJBatchStateEnum.WAITING_CALLBACKS,
    total_comparisons: int = 10,
    completed_comparisons: int = 0,
    failed_comparisons: int = 0,
    completion_threshold_pct: int = 80,
) -> CJBatchState:
    """Create test batch state."""
    batch_state = CJBatchState()
    batch_state.batch_id = batch_id
    batch_state.state = state
    batch_state.total_comparisons = total_comparisons
    batch_state.completed_comparisons = completed_comparisons
    batch_state.failed_comparisons = failed_comparisons
    batch_state.completion_threshold_pct = completion_threshold_pct
    batch_state.partial_scoring_triggered = False
    return batch_state


def create_llm_comparison_result(
    request_id: str = "req-123",
    correlation_id: UUID | None = None,
    is_error: bool = False,
    winner: EssayComparisonWinner | None = EssayComparisonWinner.ESSAY_A,
    justification: str = "Essay A has better structure",
    confidence: float = 4.5,
    error_detail: ErrorDetail | None = None,
) -> LLMComparisonResultV1:
    """Create test LLM comparison result."""
    if correlation_id is None:
        correlation_id = uuid4()

    now = datetime.now(UTC)

    if is_error and error_detail is None:
        error_detail = ErrorDetail(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="LLM provider failed",
            correlation_id=uuid4(),
            timestamp=now,
            service="llm_provider_service",
            operation="generate_comparison",
        )

    return LLMComparisonResultV1(
        request_id=request_id,
        correlation_id=correlation_id,
        winner=winner if not is_error else None,
        justification=justification if not is_error else None,
        confidence=confidence if not is_error else None,
        provider=LLMProviderType.ANTHROPIC,
        model="claude-3-haiku",
        response_time_ms=1500,
        cost_estimate=0.001,
        requested_at=now,
        completed_at=now,
        trace_id=None,
        error_detail=error_detail if is_error else None,
    )


class TestUpdateComparisonResult:
    """Test update_comparison_result behavioral outcomes."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        settings = AsyncMock(spec=Settings)
        settings.ENABLE_FAILED_COMPARISON_RETRY = False
        return settings

    @pytest.mark.asyncio
    async def test_update_comparison_result_success_behavior(self, settings: Settings) -> None:
        """Test successful callback processing updates comparison pair correctly."""
        # Arrange - Create comparison pair ready for update
        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(
            request_correlation_id=correlation_id,
            winner=None,  # No existing result
        )

        session = MockSession(comparison_pair=comparison_pair)
        session_provider = LocalMockSessionProvider(session)
        comparison_repository = LocalMockComparisonRepository(session)
        batch_repository = LocalMockBatchRepository(session)

        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_B,
            justification="Essay B shows superior analysis",
            confidence=4.2,
        )

        # Act - Process callback
        result_batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            session_provider=session_provider,
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
        )

        # Assert - Verify observable behavior
        assert result_batch_id == comparison_pair.cj_batch_id
        assert comparison_pair.winner == "essay_b"  # Converted to database format
        assert comparison_pair.confidence == 4.2
        assert comparison_pair.justification == "Essay B shows superior analysis"
        assert comparison_pair.completed_at is not None
        assert comparison_pair.processing_metadata is not None

    @pytest.mark.asyncio
    async def test_update_comparison_result_idempotency_behavior(self, settings: Settings) -> None:
        """Test idempotency - duplicate callbacks don't overwrite results."""
        # Arrange - Comparison pair already has result
        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(
            request_correlation_id=correlation_id,
            winner="essay_a",  # Already processed
            completed_at=datetime.now(UTC),
        )

        session = MockSession(comparison_pair=comparison_pair)
        session_provider = LocalMockSessionProvider(session)
        comparison_repository = LocalMockComparisonRepository(session)
        batch_repository = LocalMockBatchRepository(session)

        # Different result from callback (should be ignored)
        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_B,
        )

        # Act - Process duplicate callback
        result_batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            session_provider=session_provider,
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
        )

        # Assert - Original result preserved (idempotency)
        assert result_batch_id == comparison_pair.cj_batch_id
        assert comparison_pair.winner == "essay_a"  # Original value unchanged

    @pytest.mark.asyncio
    async def test_update_comparison_result_correlation_not_found_error(
        self, settings: Settings
    ) -> None:
        """Test error when correlation ID not found."""
        # Arrange - No matching comparison pair
        correlation_id = uuid4()
        session = MockSession(comparison_pair=None)  # No match
        session_provider = LocalMockSessionProvider(session)
        comparison_repository = LocalMockComparisonRepository(session)
        batch_repository = LocalMockBatchRepository(session)

        comparison_result = create_llm_comparison_result(correlation_id=correlation_id)

        # Act & Assert - Should raise correlation error
        with pytest.raises(HuleEduError) as exc_info:
            await update_comparison_result(
                comparison_result=comparison_result,
                session_provider=session_provider,
                comparison_repository=comparison_repository,
                batch_repository=batch_repository,
                correlation_id=correlation_id,
                settings=settings,
            )

        assert "Cannot find comparison pair" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_comparison_result_error_callback_behavior(
        self, settings: Settings
    ) -> None:
        """Test error callback processing marks comparison as failed."""
        # Arrange
        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(
            request_correlation_id=correlation_id,
            winner=None,
        )

        session = MockSession(comparison_pair=comparison_pair)
        session_provider = LocalMockSessionProvider(session)
        comparison_repository = LocalMockComparisonRepository(session)
        batch_repository = LocalMockBatchRepository(session)

        error_detail = ErrorDetail(
            error_code=ErrorCode.RATE_LIMIT,
            message="Rate limit exceeded",
            correlation_id=uuid4(),
            timestamp=datetime.now(UTC),
            service="llm_provider_service",
            operation="generate_comparison",
        )

        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id,
            is_error=True,
            error_detail=error_detail,
        )

        # Act
        result_batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            session_provider=session_provider,
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
        )

        # Assert - Error fields populated correctly
        assert result_batch_id == comparison_pair.cj_batch_id
        assert comparison_pair.winner == "error"
        assert comparison_pair.error_code == "RATE_LIMIT"
        assert comparison_pair.completed_at is not None

    @pytest.mark.asyncio
    async def test_retryable_error_routed_to_failed_pool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Retryable errors should enter failed pool and only increment failed counters."""

        settings = Settings()
        settings.ENABLE_FAILED_COMPARISON_RETRY = True

        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(
            request_correlation_id=correlation_id,
            winner=None,
        )

        session = MockSession(comparison_pair=comparison_pair)
        session_provider = LocalMockSessionProvider(session)
        comparison_repository = LocalMockComparisonRepository(session)
        batch_repository = LocalMockBatchRepository(session)

        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id,
            is_error=True,
        )

        mock_add_failed = AsyncMock()
        monkeypatch.setattr(
            "services.cj_assessment_service.cj_core_logic.callback_state_manager._retry_coordinator.add_failed_comparison_to_pool",
            mock_add_failed,
        )
        mock_update_counters = AsyncMock()
        monkeypatch.setattr(
            "services.cj_assessment_service.cj_core_logic.callback_state_manager._completion_policy.update_batch_completion_counters",
            mock_update_counters,
        )

        pool_manager = AsyncMock()
        retry_processor = AsyncMock()

        await update_comparison_result(
            comparison_result=comparison_result,
            session_provider=session_provider,
            comparison_repository=comparison_repository,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
            settings=settings,
            pool_manager=pool_manager,
            retry_processor=retry_processor,
        )

        mock_add_failed.assert_awaited_once()
        mock_update_counters.assert_awaited_once()
        assert mock_update_counters.await_args is not None
        assert mock_update_counters.await_args.kwargs["is_error"] is True


@pytest.mark.asyncio
async def test_update_batch_completion_counters_error_only_increments_failed() -> None:
    """Error callbacks should never bump completed counters."""

    batch_state = create_batch_state(
        total_comparisons=50,
        completed_comparisons=10,
        failed_comparisons=2,
    )

    session = AsyncMock(spec=AsyncSession)
    batch_repository = AsyncMock(spec=CJBatchRepositoryProtocol)
    batch_repository.get_batch_state.return_value = batch_state

    await _update_batch_completion_counters(
        session=session,
        batch_repository=batch_repository,
        batch_id=batch_state.batch_id,
        is_error=True,
        correlation_id=uuid4(),
    )

    batch_repository.get_batch_state.assert_awaited_once_with(
        session=session, batch_id=batch_state.batch_id
    )
    assert batch_state.failed_comparisons == 3
    assert batch_state.completed_comparisons == 10


def _bind_session_provider(session_provider: AsyncMock, session: AsyncSession) -> None:
    """Bind a concrete AsyncSession instance to the provider helper."""

    @asynccontextmanager
    async def session_cm() -> AsyncGenerator[AsyncSession, None]:
        yield session

    session_provider.session = session_cm


class TestBatchCompletionConditions:
    """Test batch completion condition evaluation behavior."""

    @pytest.mark.asyncio
    async def test_batch_completion_above_threshold_returns_true(
        self,
        mock_session_provider: AsyncMock,
    ) -> None:
        """Test batch completion detection when above 80% threshold."""
        # Arrange
        batch_id = 1
        correlation_id = uuid4()
        batch_state = create_batch_state(
            batch_id=batch_id,
            total_comparisons=10,
            completed_comparisons=9,  # 90% completion
        )

        session = AsyncMock(spec=AsyncSession)
        batch_repository = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repository.get_batch_state.return_value = batch_state

        _bind_session_provider(mock_session_provider, session)

        is_complete = await check_batch_completion_conditions(
            batch_id=batch_id,
            session_provider=mock_session_provider,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
        )

        # Assert - Should detect completion
        assert is_complete is True
        batch_repository.get_batch_state.assert_awaited_once_with(
            session=session, batch_id=batch_id
        )

    @pytest.mark.asyncio
    async def test_batch_completion_below_threshold_returns_false(
        self,
        mock_session_provider: AsyncMock,
    ) -> None:
        """Test batch completion when below 80% threshold."""
        # Arrange
        batch_id = 1
        correlation_id = uuid4()
        batch_state = create_batch_state(
            batch_id=batch_id,
            total_comparisons=10,
            completed_comparisons=5,  # 50% completion
        )

        session = AsyncMock(spec=AsyncSession)
        batch_repository = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repository.get_batch_state.return_value = batch_state

        _bind_session_provider(mock_session_provider, session)

        is_complete = await check_batch_completion_conditions(
            batch_id=batch_id,
            session_provider=mock_session_provider,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
        )

        # Assert - Should not detect completion
        assert is_complete is False
        batch_repository.get_batch_state.assert_awaited_once_with(
            session=session, batch_id=batch_id
        )

    @pytest.mark.asyncio
    async def test_batch_completion_batch_not_found_returns_false(
        self,
        mock_session_provider: AsyncMock,
    ) -> None:
        """Test batch completion when batch state not found."""
        # Arrange
        batch_id = 999
        correlation_id = uuid4()
        session = AsyncMock(spec=AsyncSession)
        batch_repository = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repository.get_batch_state.return_value = None

        _bind_session_provider(mock_session_provider, session)

        is_complete = await check_batch_completion_conditions(
            batch_id=batch_id,
            session_provider=mock_session_provider,
            batch_repository=batch_repository,
            correlation_id=correlation_id,
        )

        # Assert - Should handle gracefully
        assert is_complete is False
        batch_repository.get_batch_state.assert_awaited_once_with(
            session=session, batch_id=batch_id
        )


class TestReconstructComparisonTask:
    """Test comparison task reconstruction behavior."""

    @pytest.mark.asyncio
    async def test_reconstruct_comparison_task_success(self) -> None:
        """Test successful task reconstruction from comparison pair."""
        # Arrange
        correlation_id = uuid4()
        comparison_pair = create_comparison_pair(
            essay_a_els_id="essay-alpha",
            essay_b_els_id="essay-beta",
            prompt_text="Compare these two essays carefully",
        )

        # Act
        task = await reconstruct_comparison_task(
            comparison_pair=comparison_pair,
            correlation_id=correlation_id,
        )

        # Assert - Verify task structure
        assert task is not None
        assert isinstance(task, ComparisonTask)
        assert task.essay_a.id == "essay-alpha"
        assert task.essay_b.id == "essay-beta"
        assert task.prompt == "Compare these two essays carefully"
        assert "[Essay content would be fetched from database]" in task.essay_a.text_content
        assert "[Essay content would be fetched from database]" in task.essay_b.text_content

    @pytest.mark.asyncio
    async def test_reconstruct_comparison_task_handles_errors_gracefully(self) -> None:
        """Test task reconstruction handles errors by returning None."""
        # Arrange - Create invalid comparison pair that will cause error
        correlation_id = uuid4()

        class FailingComparisonPair:
            def __init__(self) -> None:
                self.id = 999  # Add id for error logging

            @property
            def essay_a_els_id(self) -> str:
                raise ValueError("Database corruption detected")

        failing_pair = FailingComparisonPair()

        # Act
        task = await reconstruct_comparison_task(
            comparison_pair=failing_pair,  # type: ignore[arg-type]
            correlation_id=correlation_id,
        )

        # Assert - Should handle error gracefully
        assert task is None
