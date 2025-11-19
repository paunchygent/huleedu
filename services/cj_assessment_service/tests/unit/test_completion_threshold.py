"""Tests ensuring completion logic ignores error callbacks and respects budgets."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum

from services.cj_assessment_service.cj_core_logic import workflow_continuation as wc
from services.cj_assessment_service.cj_core_logic.batch_completion_checker import (
    BatchCompletionChecker,
)
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import CJRepositoryProtocol


@pytest.fixture
def mock_database() -> AsyncMock:
    mock_db = AsyncMock(spec=CJRepositoryProtocol)
    mock_session = AsyncMock()
    mock_db.session.return_value.__aenter__.return_value = mock_session
    mock_db.session.return_value.__aexit__.return_value = None
    return mock_db


def _build_batch_state(threshold: int = 95) -> CJBatchState:
    state = CJBatchState()
    state.batch_id = 1
    state.state = CJBatchStateEnum.WAITING_CALLBACKS
    state.total_budget = 100
    state.total_comparisons = 10
    state.completed_comparisons = 34
    state.completion_threshold_pct = threshold
    state.current_iteration = 1
    state.processing_metadata = {"comparison_budget": {"max_pairs_requested": 100}}
    return state


@pytest.mark.asyncio
async def test_completion_checker_uses_total_budget_denominator(mock_database: AsyncMock) -> None:
    """Completion checks should divide by total_budget, not the last iteration size."""

    completion_checker = BatchCompletionChecker(database=mock_database)
    batch_state = _build_batch_state()

    with patch(
        "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
        new_callable=AsyncMock,
    ) as mock_get_state:
        mock_get_state.return_value = batch_state

        result = await completion_checker.check_batch_completion(
            cj_batch_id=batch_state.batch_id,
            correlation_id=uuid4(),
        )

    assert result is False, "34 valid comparisons out of 100 budget should be below 95%"


@pytest.mark.asyncio
async def test_completion_checker_respects_lower_threshold(mock_database: AsyncMock) -> None:
    """Custom lower thresholds should allow early completion with fewer valid pairs."""

    completion_checker = BatchCompletionChecker(database=mock_database)
    batch_state = _build_batch_state(threshold=30)

    with patch(
        "services.cj_assessment_service.cj_core_logic.batch_completion_checker.get_batch_state",
        new_callable=AsyncMock,
    ) as mock_get_state:
        mock_get_state.return_value = batch_state

        result = await completion_checker.check_batch_completion(
            cj_batch_id=batch_state.batch_id,
            correlation_id=uuid4(),
        )

    assert result is True


@pytest.mark.asyncio
async def test_workflow_continuation_counts_only_valid_winners(mock_database: AsyncMock) -> None:
    """Continuation logic should rely on valid winners and ignore error callbacks."""

    session = mock_database.session.return_value.__aenter__.return_value
    completed_result = Mock()
    completed_result.scalar_one.return_value = 34
    session.execute = AsyncMock(return_value=completed_result)

    batch_state = _build_batch_state()

    with patch(
        "services.cj_assessment_service.cj_core_logic.workflow_continuation.get_batch_state",
        new_callable=AsyncMock,
    ) as mock_get_state:
        mock_get_state.return_value = batch_state

        should_continue = await wc.check_workflow_continuation(
            batch_id=batch_state.batch_id,
            database=mock_database,
            correlation_id=uuid4(),
        )

    assert should_continue is False

    captured_stmt = session.execute.await_args[0][0]
    compiled = str(captured_stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "winner" in compiled and "IN" in compiled


@pytest.mark.asyncio
async def test_workflow_continuation_honors_completion_threshold_override(
    mock_database: AsyncMock,
) -> None:
    """Threshold overrides should allow continuation when valid completion percentage is met."""

    session = mock_database.session.return_value.__aenter__.return_value
    completed_result = Mock()
    completed_result.scalar_one.return_value = 34
    session.execute = AsyncMock(return_value=completed_result)

    batch_state = _build_batch_state(threshold=30)

    with patch(
        "services.cj_assessment_service.cj_core_logic.workflow_continuation.get_batch_state",
        new_callable=AsyncMock,
    ) as mock_get_state:
        mock_get_state.return_value = batch_state

        should_continue = await wc.check_workflow_continuation(
            batch_id=batch_state.batch_id,
            database=mock_database,
            correlation_id=uuid4(),
        )

    assert should_continue is True
