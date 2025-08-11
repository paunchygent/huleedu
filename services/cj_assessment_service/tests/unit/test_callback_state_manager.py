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
from typing import Any, AsyncContextManager, AsyncIterator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core import EssayComparisonWinner, LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import CJBatchStateEnum
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.callback_state_manager import (
    check_batch_completion_conditions,
    reconstruct_comparison_task,
    update_comparison_result,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import ComparisonTask
from services.cj_assessment_service.models_db import CJBatchState, ComparisonPair
from services.cj_assessment_service.protocols import CJRepositoryProtocol


class MockSession:
    """Minimal mock session for behavioral testing."""

    def __init__(
        self, comparison_pair: ComparisonPair | None = None, batch_state: CJBatchState | None = None
    ):
        """Initialize with test data."""
        self.comparison_pair = comparison_pair
        self.batch_state = batch_state
        self.executed_queries: list[Any] = []

    async def execute(self, stmt: Any) -> "MockResult":
        """Track executed queries and return configured results."""
        self.executed_queries.append(stmt)

        # Return appropriate result based on query
        if "comparison_pairs" in str(stmt).lower():
            return MockResult(self.comparison_pair)
        elif "batch_states" in str(stmt).lower():
            return MockResult(self.batch_state)
        else:
            return MockResult(None)

    async def commit(self) -> None:
        """Mock commit operation."""
        pass


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


class MockRepository(CJRepositoryProtocol):
    """Minimal mock repository for behavioral testing."""

    def __init__(self, session: MockSession):
        """Initialize with mock session."""
        self._session = session

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Return session context manager."""
        return mock_session_context(self._session)

    # Minimal implementations for unused methods
    async def get_assessment_instruction(
        self, session: AsyncSession, assignment_id: str | None, course_id: str | None
    ) -> Any | None:
        return None

    async def get_cj_batch_upload(self, session: AsyncSession, cj_batch_id: int) -> Any | None:
        return None

    async def get_anchor_essay_references(
        self, session: AsyncSession, assignment_id: str
    ) -> list[Any]:
        return []

    async def store_grade_projections(self, session: AsyncSession, projections: list[Any]) -> None:
        pass

    async def create_new_cj_batch(
        self,
        session: AsyncSession,
        bos_batch_id: str,
        event_correlation_id: str,
        language: str,
        course_code: str,
        essay_instructions: str,
        initial_status: Any,
        expected_essay_count: int,
    ) -> Any:
        return None

    async def create_or_update_cj_processed_essay(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        els_essay_id: str,
        text_storage_id: str,
        assessment_input_text: str,
        processing_metadata: dict | None = None,
    ) -> Any:
        return None

    async def get_essays_for_cj_batch(self, session: AsyncSession, cj_batch_id: int) -> list[Any]:
        return []

    async def get_comparison_pair_by_essays(
        self, session: AsyncSession, cj_batch_id: int, essay_a_els_id: str, essay_b_els_id: str
    ) -> Any | None:
        return None

    async def store_comparison_results(
        self, session: AsyncSession, results: list[Any], cj_batch_id: int
    ) -> None:
        pass

    async def update_essay_scores_in_batch(
        self, session: AsyncSession, cj_batch_id: int, scores: dict[str, float]
    ) -> None:
        pass

    async def update_cj_batch_status(
        self, session: AsyncSession, cj_batch_id: int, status: Any
    ) -> None:
        pass

    async def get_final_cj_rankings(
        self, session: AsyncSession, cj_batch_id: int
    ) -> list[dict[str, Any]]:
        return []

    async def initialize_db_schema(self) -> None:
        pass


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
        repository = MockRepository(session)

        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_B,
            justification="Essay B shows superior analysis",
            confidence=4.2,
        )

        # Act - Process callback
        result_batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            database=repository,
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
        repository = MockRepository(session)

        # Different result from callback (should be ignored)
        comparison_result = create_llm_comparison_result(
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_B,
        )

        # Act - Process duplicate callback
        result_batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            database=repository,
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
        repository = MockRepository(session)

        comparison_result = create_llm_comparison_result(correlation_id=correlation_id)

        # Act & Assert - Should raise correlation error
        with pytest.raises(HuleEduError) as exc_info:
            await update_comparison_result(
                comparison_result=comparison_result,
                database=repository,
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
        repository = MockRepository(session)

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
            database=repository,
            correlation_id=correlation_id,
            settings=settings,
        )

        # Assert - Error fields populated correctly
        assert result_batch_id == comparison_pair.cj_batch_id
        assert comparison_pair.winner == "error"
        assert comparison_pair.error_code == "RATE_LIMIT"
        assert comparison_pair.completed_at is not None


class TestBatchCompletionConditions:
    """Test batch completion condition evaluation behavior."""

    @pytest.mark.asyncio
    async def test_batch_completion_above_threshold_returns_true(self) -> None:
        """Test batch completion detection when above 80% threshold."""
        # Arrange
        batch_id = 1
        correlation_id = uuid4()
        batch_state = create_batch_state(
            batch_id=batch_id,
            total_comparisons=10,
            completed_comparisons=9,  # 90% completion
        )

        session = MockSession(batch_state=batch_state)
        repository = MockRepository(session)

        # Act
        async with repository.session() as session_ctx:
            is_complete = await check_batch_completion_conditions(
                batch_id=batch_id,
                database=repository,
                session=session_ctx,
                correlation_id=correlation_id,
            )

        # Assert - Should detect completion
        assert is_complete is True

    @pytest.mark.asyncio
    async def test_batch_completion_below_threshold_returns_false(self) -> None:
        """Test batch completion when below 80% threshold."""
        # Arrange
        batch_id = 1
        correlation_id = uuid4()
        batch_state = create_batch_state(
            batch_id=batch_id,
            total_comparisons=10,
            completed_comparisons=5,  # 50% completion
        )

        session = MockSession(batch_state=batch_state)
        repository = MockRepository(session)

        # Act
        async with repository.session() as session_ctx:
            is_complete = await check_batch_completion_conditions(
                batch_id=batch_id,
                database=repository,
                session=session_ctx,
                correlation_id=correlation_id,
            )

        # Assert - Should not detect completion
        assert is_complete is False

    @pytest.mark.asyncio
    async def test_batch_completion_batch_not_found_returns_false(self) -> None:
        """Test batch completion when batch state not found."""
        # Arrange
        batch_id = 999
        correlation_id = uuid4()
        session = MockSession(batch_state=None)  # Batch not found
        repository = MockRepository(session)

        # Act
        async with repository.session() as session_ctx:
            is_complete = await check_batch_completion_conditions(
                batch_id=batch_id,
                database=repository,
                session=session_ctx,
                correlation_id=correlation_id,
            )

        # Assert - Should handle gracefully
        assert is_complete is False


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
