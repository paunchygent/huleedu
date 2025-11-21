"""Tests ensuring completion logic ignores error callbacks and respects budgets."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum

from services.cj_assessment_service.cj_core_logic.batch_completion_checker import (
    BatchCompletionChecker,
)
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload
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


def test_completion_denominator_uses_small_batch_nc2_cap() -> None:
    batch_state = _build_batch_state()
    batch_state.total_budget = 350
    batch_state.total_comparisons = 6
    batch_state.batch_upload = CJBatchUpload(
        bos_batch_id="bos-test",
        event_correlation_id="00000000-0000-0000-0000-000000000000",
        language="en",
        course_code="eng5",
        expected_essay_count=4,
        status=CJBatchStatusEnum.PENDING,
    )

    assert batch_state.completion_denominator() == 6
