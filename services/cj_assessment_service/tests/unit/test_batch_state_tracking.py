"""Tests for CJ batch state aggregation and iteration tracking."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum

from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import CJRepositoryProtocol, LLMInteractionProtocol


@pytest.fixture
def mock_database() -> AsyncMock:
    """Return a mock repository with a pre-configured session context manager."""

    mock_db = AsyncMock(spec=CJRepositoryProtocol)
    mock_session = AsyncMock()
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_db.session.return_value.__aenter__.return_value = mock_session
    mock_db.session.return_value.__aexit__.return_value = None
    return mock_db


@pytest.fixture
def batch_processor(mock_database: AsyncMock) -> BatchProcessor:
    """Instantiate the batch processor under test."""

    return BatchProcessor(
        database=mock_database,
        llm_interaction=AsyncMock(spec=LLMInteractionProtocol),
        settings=Settings(DEFAULT_BATCH_SIZE=10),
    )


def _build_mock_state() -> CJBatchState:
    state = CJBatchState()
    state.batch_id = 1
    state.state = CJBatchStateEnum.WAITING_CALLBACKS
    state.total_budget = None
    state.total_comparisons = 0
    state.submitted_comparisons = 0
    state.completed_comparisons = 0
    state.failed_comparisons = 0
    state.current_iteration = 0
    state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 100, "source": "service_default"}
    }
    return state


@pytest.mark.asyncio
async def test_first_submission_sets_budget_and_totals(
    batch_processor: BatchProcessor, mock_database: AsyncMock
) -> None:
    """The first submission should capture total budget and initialize counters."""

    batch_state = _build_mock_state()
    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = batch_state

    session = mock_database.session.return_value.__aenter__.return_value
    session.execute = AsyncMock(return_value=mock_result)

    await batch_processor._update_batch_state_with_totals(
        cj_batch_id=batch_state.batch_id,
        state=CJBatchStateEnum.WAITING_CALLBACKS,
        iteration_comparisons=25,
        correlation_id=uuid4(),
    )

    assert batch_state.total_budget == 100
    assert batch_state.total_comparisons == 25
    assert batch_state.submitted_comparisons == 25
    assert batch_state.current_iteration == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_subsequent_submission_accumulates_counters(
    batch_processor: BatchProcessor, mock_database: AsyncMock
) -> None:
    """Later submissions should increment totals instead of overwriting them."""

    batch_state = _build_mock_state()
    batch_state.total_budget = 100
    batch_state.total_comparisons = 40
    batch_state.submitted_comparisons = 40
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {}

    mock_result = Mock()
    mock_result.scalar_one_or_none.return_value = batch_state

    session = mock_database.session.return_value.__aenter__.return_value
    session.execute = AsyncMock(return_value=mock_result)

    await batch_processor._update_batch_state_with_totals(
        cj_batch_id=batch_state.batch_id,
        state=CJBatchStateEnum.WAITING_CALLBACKS,
        iteration_comparisons=15,
        correlation_id=uuid4(),
    )

    assert batch_state.total_budget == 100
    assert batch_state.total_comparisons == 55
    assert batch_state.submitted_comparisons == 55
    assert batch_state.current_iteration == 2
    session.commit.assert_awaited_once()
