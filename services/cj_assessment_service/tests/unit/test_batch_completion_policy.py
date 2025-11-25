"""Unit tests for BatchCompletionPolicy thresholds and counter updates."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_completion_policy import (
    BatchCompletionPolicy,
)
from services.cj_assessment_service.protocols import CJBatchRepositoryProtocol
from services.cj_assessment_service.tests.unit.test_callback_state_manager import create_batch_state


@pytest.fixture
def policy() -> BatchCompletionPolicy:
    return BatchCompletionPolicy()


class TestCheckBatchCompletionConditions:
    """Behavioral tests for the 80% completion heuristic."""

    @pytest.mark.parametrize(
        "completed, denominator, expected",
        [
            (0, 10, False),
            (7, 10, False),  # 70%
            (8, 10, True),  # 80%
            (9, 10, True),  # 90%
            (10, 10, True),  # 100%
            (5, 0, False),  # zero denominator
        ],
    )
    @pytest.mark.asyncio
    async def test_threshold_matrix(
        self,
        policy: BatchCompletionPolicy,
        completed: int,
        denominator: int,
        expected: bool,
    ) -> None:
        """Return True only when completed_comparisons reach 80% of denominator."""
        batch_state = create_batch_state(
            total_comparisons=denominator,
            completed_comparisons=completed,
        )
        session = AsyncMock(spec=AsyncSession)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repo.get_batch_state.return_value = batch_state

        result = await policy.check_batch_completion_conditions(
            batch_id=1,
            batch_repo=batch_repo,
            session=session,
            correlation_id=uuid4(),
        )

        batch_repo.get_batch_state.assert_awaited_once_with(session=session, batch_id=1)
        assert result is expected

    @pytest.mark.asyncio
    async def test_missing_batch_returns_false(
        self,
        policy: BatchCompletionPolicy,
    ) -> None:
        """If batch state is absent, completion should evaluate to False without error."""
        session = AsyncMock(spec=AsyncSession)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repo.get_batch_state.return_value = None

        result = await policy.check_batch_completion_conditions(
            batch_id=99,
            batch_repo=batch_repo,
            session=session,
            correlation_id=uuid4(),
        )

        batch_repo.get_batch_state.assert_awaited_once_with(session=session, batch_id=99)
        assert result is False

    @pytest.mark.asyncio
    async def test_defensive_on_execute_exception(
        self,
        policy: BatchCompletionPolicy,
    ) -> None:
        """DB errors should be swallowed and produce False."""
        session = AsyncMock(spec=AsyncSession)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repo.get_batch_state.side_effect = RuntimeError("db failure")

        result = await policy.check_batch_completion_conditions(
            batch_id=1,
            batch_repo=batch_repo,
            session=session,
            correlation_id=uuid4(),
        )

        batch_repo.get_batch_state.assert_awaited_once_with(session=session, batch_id=1)
        assert result is False


class TestUpdateBatchCompletionCounters:
    """Behavioral tests for counter increments and partial scoring."""

    @pytest.mark.asyncio
    async def test_success_callback_increments_completed_and_updates_last_activity(
        self,
        policy: BatchCompletionPolicy,
    ) -> None:
        batch_state = create_batch_state(
            total_comparisons=10,
            completed_comparisons=3,
            failed_comparisons=1,
            completion_threshold_pct=80,
        )
        previous_activity = datetime(2020, 1, 1, tzinfo=UTC)
        batch_state.last_activity_at = previous_activity

        session = AsyncMock(spec=AsyncSession)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repo.get_batch_state.return_value = batch_state

        await policy.update_batch_completion_counters(
            batch_repo=batch_repo,
            session=session,
            batch_id=batch_state.batch_id,
            is_error=False,
            correlation_id=uuid4(),
        )

        batch_repo.get_batch_state.assert_awaited_once_with(
            session=session, batch_id=batch_state.batch_id
        )
        assert batch_state.completed_comparisons == 4
        assert batch_state.failed_comparisons == 1
        assert batch_state.last_activity_at is not None
        assert batch_state.last_activity_at != previous_activity

    @pytest.mark.asyncio
    async def test_error_callback_increments_failed_only(
        self,
        policy: BatchCompletionPolicy,
    ) -> None:
        batch_state = create_batch_state(
            total_comparisons=10,
            completed_comparisons=4,
            failed_comparisons=2,
            completion_threshold_pct=80,
        )
        session = AsyncMock(spec=AsyncSession)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repo.get_batch_state.return_value = batch_state

        await policy.update_batch_completion_counters(
            batch_repo=batch_repo,
            session=session,
            batch_id=batch_state.batch_id,
            is_error=True,
            correlation_id=uuid4(),
        )

        assert batch_state.completed_comparisons == 4
        assert batch_state.failed_comparisons == 3

    @pytest.mark.parametrize(
        "completed_before, expected_flag",
        [
            (6, False),  # still below threshold after increment (7/10)
            (7, True),  # crosses threshold after increment (8/10)
            (8, True),  # above threshold (flag should stay True)
        ],
    )
    @pytest.mark.asyncio
    async def test_partial_scoring_trigger_boundary(
        self,
        policy: BatchCompletionPolicy,
        completed_before: int,
        expected_flag: bool,
    ) -> None:
        batch_state = create_batch_state(
            total_comparisons=10,
            completed_comparisons=completed_before,
            completion_threshold_pct=80,
        )
        session = AsyncMock(spec=AsyncSession)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repo.get_batch_state.return_value = batch_state

        await policy.update_batch_completion_counters(
            batch_repo=batch_repo,
            session=session,
            batch_id=batch_state.batch_id,
            is_error=False,
            correlation_id=uuid4(),
        )

        assert batch_state.partial_scoring_triggered is expected_flag

    @pytest.mark.asyncio
    async def test_partial_scoring_once_only(
        self,
        policy: BatchCompletionPolicy,
    ) -> None:
        """Flag stays True after being triggered once."""
        batch_state = create_batch_state(
            total_comparisons=10,
            completed_comparisons=8,
            completion_threshold_pct=80,
        )
        batch_state.partial_scoring_triggered = True

        session = AsyncMock(spec=AsyncSession)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repo.get_batch_state.return_value = batch_state

        await policy.update_batch_completion_counters(
            batch_repo=batch_repo,
            session=session,
            batch_id=batch_state.batch_id,
            is_error=False,
            correlation_id=uuid4(),
        )

        assert batch_state.partial_scoring_triggered is True
        assert batch_state.completed_comparisons == 9

    @pytest.mark.asyncio
    async def test_no_batch_state_is_noop(
        self,
        policy: BatchCompletionPolicy,
    ) -> None:
        session = AsyncMock(spec=AsyncSession)
        batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
        batch_repo.get_batch_state.return_value = None

        await policy.update_batch_completion_counters(
            batch_repo=batch_repo,
            session=session,
            batch_id=123,
            is_error=False,
            correlation_id=uuid4(),
        )

        # Nothing to assert besides absence of exceptions
        assert True
