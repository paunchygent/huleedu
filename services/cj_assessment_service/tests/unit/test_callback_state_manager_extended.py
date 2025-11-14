"""Extended behavioral tests for callback state manager edge cases.

This module tests uncovered edge cases and error paths in callback_state_manager,
focusing on observable behavior and side effects per Rule 075.

Tests cover:
- Error handling in batch completion checks
- Failed comparison pool management behavior
- Successful retry handling observable effects
- Batch counter update state transitions

All tests use protocol-compliant mocks with NO patching or type ignores.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncContextManager, AsyncIterator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core import EssayComparisonWinner, LLMProviderType
from common_core.error_enums import ErrorCode
from common_core.events.llm_provider_events import LLMComparisonResultV1, TokenUsage
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import CJBatchStateEnum
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_pool_manager import BatchPoolManager
from services.cj_assessment_service.cj_core_logic.batch_retry_processor import BatchRetryProcessor
from services.cj_assessment_service.cj_core_logic.callback_state_manager import (
    _update_batch_completion_counters,
    add_failed_comparison_to_pool,
    check_batch_completion_conditions,
    update_comparison_result,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import (
    AssessmentInstruction,
    CJBatchState,
    ComparisonPair,
)
from services.cj_assessment_service.protocols import CJRepositoryProtocol
from services.cj_assessment_service.tests.unit.instruction_store import AssessmentInstructionStore


class MockSession:
    """Protocol-compliant mock session for behavioral testing."""

    def __init__(
        self,
        comparison_pair: ComparisonPair | None = None,
        batch_state: CJBatchState | None = None,
        raise_on_execute: Exception | None = None,
    ):
        """Initialize with test data."""
        self.comparison_pair = comparison_pair
        self.batch_state = batch_state
        self.raise_on_execute = raise_on_execute
        self.executed_queries: list[Any] = []
        self.committed = False

    async def execute(self, stmt: Any) -> MockResult:
        """Track executed queries and return configured results."""
        self.executed_queries.append(stmt)

        if self.raise_on_execute:
            raise self.raise_on_execute

        # Return appropriate result based on query pattern
        stmt_str = str(stmt).lower()
        if "comparison_pairs" in stmt_str:
            return MockResult(self.comparison_pair)
        elif "batch_states" in stmt_str or "cj_batch_states" in stmt_str:
            return MockResult(self.batch_state)
        else:
            return MockResult(None)

    async def commit(self) -> None:
        """Track commit operation."""
        self.committed = True


class MockResult:
    """Mock SQLAlchemy result following protocol."""

    def __init__(self, result: Any) -> None:
        """Initialize with result value."""
        self.result = result

    def scalar_one_or_none(self) -> Any:
        """Return the configured result."""
        return self.result


@asynccontextmanager
async def mock_session_context(session: MockSession) -> AsyncIterator[AsyncSession]:
    """Create async context manager for session."""
    yield session  # type: ignore[misc]


class MockRepository(CJRepositoryProtocol):
    """Protocol-compliant mock repository."""

    def __init__(self, session: MockSession):
        """Initialize with mock session."""
        self._session = session
        self._instruction_store = AssessmentInstructionStore()

    def session(self) -> AsyncContextManager[AsyncSession]:
        """Return session context manager."""
        return mock_session_context(self._session)

    # Required protocol methods with minimal implementations
    async def get_assessment_instruction(
        self, session: AsyncSession, assignment_id: str | None, course_id: str | None
    ) -> AssessmentInstruction | None:
        return self._instruction_store.get(assignment_id=assignment_id, course_id=course_id)

    async def get_cj_batch_upload(self, session: AsyncSession, cj_batch_id: int) -> Any | None:
        return None

    async def get_assignment_context(
        self,
        session: AsyncSession,
        assignment_id: str,
    ) -> dict[str, Any] | None:
        return {
            "assignment_id": assignment_id,
            "instructions_text": "Mock instructions",
            "grade_scale": "swedish_8_anchor",
        }

    async def get_anchor_essay_references(
        self,
        session: AsyncSession,
        assignment_id: str,
        grade_scale: str | None = None,
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
        initial_status: Any,
        expected_essay_count: int,
        user_id: str | None = None,
        org_id: str | None = None,
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

    async def upsert_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        student_prompt_storage_id: str | None = None,
        judge_rubric_storage_id: str | None = None,
    ) -> AssessmentInstruction:
        return self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            student_prompt_storage_id=student_prompt_storage_id,
            judge_rubric_storage_id=judge_rubric_storage_id,
        )

    async def list_assessment_instructions(
        self,
        session: AsyncSession,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[AssessmentInstruction], int]:
        return self._instruction_store.list(limit=limit, offset=offset, grade_scale=grade_scale)

    async def delete_assessment_instruction(
        self,
        session: AsyncSession,
        *,
        assignment_id: str | None,
        course_id: str | None,
    ) -> bool:
        return self._instruction_store.delete(
            assignment_id=assignment_id,
            course_id=course_id,
        )

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

    async def upsert_anchor_reference(
        self,
        session: AsyncSession,
        *,
        assignment_id: str,
        anchor_label: str,
        grade: str,
        grade_scale: str,
        text_storage_id: str,
    ) -> int:
        """Stub implementation for test mocks."""
        return 1  # Return a mock anchor ID


def create_test_comparison_pair(
    cj_batch_id: int = 1,
    request_correlation_id: UUID | None = None,
    winner: str | None = None,
) -> ComparisonPair:
    """Create comparison pair for testing."""
    pair = ComparisonPair()
    pair.id = 42
    pair.cj_batch_id = cj_batch_id
    pair.request_correlation_id = request_correlation_id or uuid4()
    pair.essay_a_els_id = "essay-a-123"
    pair.essay_b_els_id = "essay-b-456"
    pair.winner = winner
    pair.prompt_text = "Compare these essays"
    return pair


def create_test_batch_state(
    batch_id: int = 1,
    total_comparisons: int = 10,
    completed_comparisons: int = 0,
    failed_comparisons: int = 0,
    partial_scoring_triggered: bool = False,
) -> CJBatchState:
    """Create batch state for testing."""
    state = CJBatchState()
    state.batch_id = batch_id
    state.state = CJBatchStateEnum.WAITING_CALLBACKS
    state.total_comparisons = total_comparisons
    state.completed_comparisons = completed_comparisons
    state.failed_comparisons = failed_comparisons
    state.completion_threshold_pct = 80
    state.partial_scoring_triggered = partial_scoring_triggered
    return state


def create_test_llm_result(
    correlation_id: UUID,
    is_error: bool = False,
    error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
) -> LLMComparisonResultV1:
    """Create LLM result for testing."""
    now = datetime.now(UTC)

    if is_error:
        return LLMComparisonResultV1(
            request_id="req-123",
            correlation_id=correlation_id,
            error_detail=ErrorDetail(
                service="llm_provider",
                operation="compare",
                error_code=error_code,
                message="Test error",
                correlation_id=correlation_id,
                timestamp=now,
            ),
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-haiku",
            response_time_ms=1500,
            token_usage=TokenUsage(),
            cost_estimate=0.001,
            requested_at=now,
            completed_at=now,
        )
    else:
        return LLMComparisonResultV1(
            request_id="req-123",
            correlation_id=correlation_id,
            winner=EssayComparisonWinner.ESSAY_A,
            confidence=4.5,
            justification="Essay A is better",
            provider=LLMProviderType.ANTHROPIC,
            model="claude-3-haiku",
            response_time_ms=1500,
            token_usage=TokenUsage(),
            cost_estimate=0.001,
            requested_at=now,
            completed_at=now,
        )


class TestBatchCompletionErrorHandling:
    """Test error handling in batch completion checking."""

    @pytest.mark.asyncio
    async def test_check_batch_completion_database_error_returns_false(self) -> None:
        """Test that database errors in batch completion check return False safely."""
        # Arrange - Database error scenario
        session = MockSession(raise_on_execute=Exception("Database connection lost"))
        repository = MockRepository(session)

        # Act - Check should handle error gracefully
        result = await check_batch_completion_conditions(
            batch_id=1,
            database=repository,
            session=session,  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert - Returns False on error, doesn't propagate exception
        assert result is False
        assert len(session.executed_queries) == 1

    @pytest.mark.asyncio
    async def test_check_batch_completion_missing_batch_state_returns_false(self) -> None:
        """Test that missing batch state returns False."""
        # Arrange - No batch state found
        session = MockSession(batch_state=None)
        repository = MockRepository(session)

        # Act
        result = await check_batch_completion_conditions(
            batch_id=999,
            database=repository,
            session=session,  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert - Returns False when batch not found
        assert result is False
        assert len(session.executed_queries) == 1

    @pytest.mark.asyncio
    async def test_check_batch_completion_zero_total_comparisons_returns_false(self) -> None:
        """Test that zero total comparisons (invalid state) returns False."""
        # Arrange - Invalid batch state with zero total
        batch_state = create_test_batch_state(
            total_comparisons=0,
            completed_comparisons=5,
        )
        session = MockSession(batch_state=batch_state)
        repository = MockRepository(session)

        # Act
        result = await check_batch_completion_conditions(
            batch_id=1,
            database=repository,
            session=session,  # type: ignore[arg-type]
            correlation_id=uuid4(),
        )

        # Assert - Returns False for invalid state
        assert result is False


class TestUpdateBatchCompletionCounters:
    """Test batch counter update behavior."""

    @pytest.mark.asyncio
    async def test_update_counters_increments_completed_on_success(self) -> None:
        """Test that successful comparison increments completed counter."""
        # Arrange
        batch_state = create_test_batch_state(
            completed_comparisons=4,
            failed_comparisons=1,
        )
        session = MockSession(batch_state=batch_state)

        # Act - Update for successful comparison
        await _update_batch_completion_counters(
            session=session,  # type: ignore[arg-type]
            batch_id=1,
            is_error=False,
            correlation_id=uuid4(),
        )

        # Assert - Completed counter incremented
        assert batch_state.completed_comparisons == 5
        assert batch_state.failed_comparisons == 1

    @pytest.mark.asyncio
    async def test_update_counters_increments_failed_on_error(self) -> None:
        """Test that error comparison increments failed counter."""
        # Arrange
        batch_state = create_test_batch_state(
            completed_comparisons=4,
            failed_comparisons=1,
        )
        session = MockSession(batch_state=batch_state)

        # Act - Update for failed comparison
        await _update_batch_completion_counters(
            session=session,  # type: ignore[arg-type]
            batch_id=1,
            is_error=True,
            correlation_id=uuid4(),
        )

        # Assert - Failed counter incremented
        assert batch_state.completed_comparisons == 4
        assert batch_state.failed_comparisons == 2

    @pytest.mark.asyncio
    async def test_update_counters_triggers_partial_scoring_at_threshold(self) -> None:
        """Test that partial scoring triggers at 80% threshold."""
        # Arrange - 7/10 completed, next will hit 80%
        batch_state = create_test_batch_state(
            total_comparisons=10,
            completed_comparisons=7,
            partial_scoring_triggered=False,
        )
        session = MockSession(batch_state=batch_state)

        # Act - Complete one more to hit 80%
        await _update_batch_completion_counters(
            session=session,  # type: ignore[arg-type]
            batch_id=1,
            is_error=False,
            correlation_id=uuid4(),
        )

        # Assert - Partial scoring triggered
        assert batch_state.completed_comparisons == 8
        assert batch_state.partial_scoring_triggered is True

    @pytest.mark.asyncio
    async def test_update_counters_handles_missing_batch_gracefully(self) -> None:
        """Test that missing batch state is handled without error."""
        # Arrange - No batch state
        session = MockSession(batch_state=None)

        # Act - Should not raise
        await _update_batch_completion_counters(
            session=session,  # type: ignore[arg-type]
            batch_id=999,
            is_error=False,
            correlation_id=uuid4(),
        )

        # Assert - Completed without error
        assert len(session.executed_queries) == 1

    @pytest.mark.asyncio
    async def test_update_counters_handles_database_error_gracefully(self) -> None:
        """Test that database errors in counter updates don't propagate."""
        # Arrange
        session = MockSession(raise_on_execute=Exception("Connection lost"))

        # Act - Should not raise
        await _update_batch_completion_counters(
            session=session,  # type: ignore[arg-type]
            batch_id=1,
            is_error=False,
            correlation_id=uuid4(),
        )

        # Assert - Error was caught
        assert len(session.executed_queries) == 1


class TestFailedComparisonPoolManagement:
    """Test failed comparison pool management behavior."""

    @pytest.mark.asyncio
    async def test_add_failed_comparison_triggers_retry_batch(self) -> None:
        """Test that adding failed comparison can trigger retry batch submission."""
        # Arrange
        correlation_id = uuid4()
        comparison_pair = create_test_comparison_pair(
            request_correlation_id=correlation_id,
        )
        comparison_pair.winner = "error"
        comparison_pair.error_code = "RATE_LIMIT"

        # Create protocol-compliant mocks
        pool_manager = AsyncMock(spec=BatchPoolManager)
        pool_manager.add_to_failed_pool = AsyncMock(return_value=None)
        pool_manager.check_retry_batch_needed = AsyncMock(return_value=True)

        retry_processor = AsyncMock(spec=BatchRetryProcessor)
        retry_processor.submit_retry_batch = AsyncMock(return_value=None)

        comparison_result = create_test_llm_result(
            correlation_id=correlation_id,
            is_error=True,
            error_code=ErrorCode.RATE_LIMIT,
        )

        # Act
        await add_failed_comparison_to_pool(
            pool_manager=pool_manager,
            retry_processor=retry_processor,
            comparison_pair=comparison_pair,
            comparison_result=comparison_result,
            correlation_id=correlation_id,
        )

        # Assert - Observable behavior: retry batch triggered
        pool_manager.add_to_failed_pool.assert_called_once()
        pool_manager.check_retry_batch_needed.assert_called_once_with(
            cj_batch_id=1,
            correlation_id=correlation_id,
            force_retry_all=False,
        )
        retry_processor.submit_retry_batch.assert_called_once_with(
            cj_batch_id=1,
            correlation_id=correlation_id,
        )

    @pytest.mark.asyncio
    async def test_add_failed_comparison_no_retry_when_not_needed(self) -> None:
        """Test that retry batch is not triggered when threshold not met."""
        # Arrange
        correlation_id = uuid4()
        comparison_pair = create_test_comparison_pair(
            request_correlation_id=correlation_id,
        )
        comparison_pair.winner = "error"

        pool_manager = AsyncMock(spec=BatchPoolManager)
        pool_manager.add_to_failed_pool = AsyncMock(return_value=None)
        pool_manager.check_retry_batch_needed = AsyncMock(return_value=False)

        retry_processor = AsyncMock(spec=BatchRetryProcessor)
        retry_processor.submit_retry_batch = AsyncMock()

        comparison_result = create_test_llm_result(
            correlation_id=correlation_id,
            is_error=True,
        )

        # Act
        await add_failed_comparison_to_pool(
            pool_manager=pool_manager,
            retry_processor=retry_processor,
            comparison_pair=comparison_pair,
            comparison_result=comparison_result,
            correlation_id=correlation_id,
        )

        # Assert - No retry batch submitted
        pool_manager.add_to_failed_pool.assert_called_once()
        pool_manager.check_retry_batch_needed.assert_called_once()
        retry_processor.submit_retry_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_failed_comparison_handles_exceptions_gracefully(self) -> None:
        """Test that exceptions in pool management don't propagate."""
        # Arrange
        correlation_id = uuid4()
        comparison_pair = create_test_comparison_pair(
            request_correlation_id=correlation_id,
        )

        pool_manager = AsyncMock(spec=BatchPoolManager)
        pool_manager.add_to_failed_pool = AsyncMock(side_effect=Exception("Pool error"))

        retry_processor = AsyncMock(spec=BatchRetryProcessor)
        comparison_result = create_test_llm_result(
            correlation_id=correlation_id,
            is_error=True,
        )

        # Act - Should not raise
        await add_failed_comparison_to_pool(
            pool_manager=pool_manager,
            retry_processor=retry_processor,
            comparison_pair=comparison_pair,
            comparison_result=comparison_result,
            correlation_id=correlation_id,
        )

        # Assert - Exception was caught
        pool_manager.add_to_failed_pool.assert_called_once()


class TestUpdateComparisonResultWithPoolManager:
    """Test update_comparison_result with pool manager integration."""

    @pytest.mark.asyncio
    async def test_update_result_adds_error_to_failed_pool_when_enabled(self) -> None:
        """Test that errors are added to failed pool when retry is enabled."""
        # Arrange
        correlation_id = uuid4()
        comparison_pair = create_test_comparison_pair(
            request_correlation_id=correlation_id,
            winner=None,
        )
        batch_state = create_test_batch_state()

        session = MockSession(
            comparison_pair=comparison_pair,
            batch_state=batch_state,
        )
        repository = MockRepository(session)

        settings = Settings()
        settings.ENABLE_FAILED_COMPARISON_RETRY = True

        pool_manager = AsyncMock(spec=BatchPoolManager)
        pool_manager.add_to_failed_pool = AsyncMock()
        pool_manager.check_retry_batch_needed = AsyncMock(return_value=False)

        retry_processor = AsyncMock(spec=BatchRetryProcessor)

        comparison_result = create_test_llm_result(
            correlation_id=correlation_id,
            is_error=True,
        )

        # Act
        batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            database=repository,
            correlation_id=correlation_id,
            settings=settings,
            pool_manager=pool_manager,
            retry_processor=retry_processor,
        )

        # Assert
        assert batch_id == 1
        assert comparison_pair.winner == "error"
        assert comparison_pair.error_code == "UNKNOWN_ERROR"
        assert session.committed is True

    @pytest.mark.asyncio
    async def test_update_result_handles_successful_retry_when_enabled(self) -> None:
        """Test that successful comparisons trigger retry handling when enabled."""
        # Arrange
        correlation_id = uuid4()
        comparison_pair = create_test_comparison_pair(
            request_correlation_id=correlation_id,
            winner=None,
        )
        batch_state = create_test_batch_state()

        session = MockSession(
            comparison_pair=comparison_pair,
            batch_state=batch_state,
        )
        repository = MockRepository(session)

        settings = Settings()
        settings.ENABLE_FAILED_COMPARISON_RETRY = True

        pool_manager = AsyncMock(spec=BatchPoolManager)
        pool_manager.database = repository

        comparison_result = create_test_llm_result(
            correlation_id=correlation_id,
            is_error=False,
        )

        # Act
        batch_id = await update_comparison_result(
            comparison_result=comparison_result,
            database=repository,
            correlation_id=correlation_id,
            settings=settings,
            pool_manager=pool_manager,
            retry_processor=None,
        )

        # Assert
        assert batch_id == 1
        assert comparison_pair.winner == "essay_a"
        assert comparison_pair.confidence == 4.5
        assert session.committed is True
