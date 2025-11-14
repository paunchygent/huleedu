"""Shared test fixtures for failed comparison pool functionality."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.batch_pool_manager import BatchPoolManager
    from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
    from services.cj_assessment_service.cj_core_logic.batch_retry_processor import (
        BatchRetryProcessor,
    )
    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.models_api import (
        ComparisonTask,
        FailedComparisonPool,
    )
    from services.cj_assessment_service.models_db import CJBatchState
    from services.cj_assessment_service.protocols import (
        BatchProcessorProtocol,
        CJRepositoryProtocol,
        LLMInteractionProtocol,
    )

from services.cj_assessment_service.cj_core_logic.batch_pool_manager import BatchPoolManager
from services.cj_assessment_service.cj_core_logic.batch_processor import BatchProcessor
from services.cj_assessment_service.cj_core_logic.batch_retry_processor import BatchRetryProcessor
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    EssayForComparison,
    FailedComparisonPool,
    FailedComparisonPoolStatistics,
)
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import (
    BatchProcessorProtocol,
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)


@pytest.fixture(autouse=True)
def mock_get_batch_state(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Patch get_batch_state to avoid hitting the database.

    This fixture is autouse=True so it applies to all tests that use batch_retry_processor.
    Tests can override the return_value if they need custom metadata.
    """
    mock = AsyncMock()
    mock.return_value = SimpleNamespace(processing_metadata=None)
    monkeypatch.setattr(
        "services.cj_assessment_service.cj_core_logic.batch_submission.get_batch_state",
        mock,
    )
    return mock


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings with failed pool configuration."""

    class MockSettings:
        ENABLE_FAILED_COMPARISON_RETRY = True
        FAILED_COMPARISON_RETRY_THRESHOLD = 5
        MAX_RETRY_ATTEMPTS = 3
        RETRY_BATCH_SIZE = 10

    return MockSettings()  # type: ignore


@pytest.fixture
def mock_database() -> AsyncMock:
    """Create mock database protocol."""
    return AsyncMock(spec=CJRepositoryProtocol)


@pytest.fixture
def mock_llm_interaction() -> LLMInteractionProtocol:
    """Create mock LLM interaction protocol."""
    return AsyncMock(spec=LLMInteractionProtocol)


@pytest.fixture
def batch_processor(
    mock_database: CJRepositoryProtocol,
    mock_llm_interaction: LLMInteractionProtocol,
    mock_settings: Settings,
) -> BatchProcessor:
    """Create BatchProcessor instance with mocks."""
    return BatchProcessor(
        database=mock_database,
        llm_interaction=mock_llm_interaction,
        settings=mock_settings,
    )


@pytest.fixture
def batch_pool_manager(
    mock_database: CJRepositoryProtocol,
    mock_settings: Settings,
) -> BatchPoolManager:
    """Create BatchPoolManager instance with mocks."""
    return BatchPoolManager(
        database=mock_database,
        settings=mock_settings,
    )


@pytest.fixture
def mock_batch_submitter() -> AsyncMock:
    """Create mock batch submitter protocol."""
    return AsyncMock(spec=BatchProcessorProtocol)


@pytest.fixture
def batch_retry_processor(
    mock_database: CJRepositoryProtocol,
    mock_llm_interaction: LLMInteractionProtocol,
    mock_settings: Settings,
    batch_pool_manager: BatchPoolManager,
    mock_batch_submitter: AsyncMock,
) -> BatchRetryProcessor:
    """Create BatchRetryProcessor instance with mocks."""
    return BatchRetryProcessor(
        database=mock_database,
        llm_interaction=mock_llm_interaction,
        settings=mock_settings,
        pool_manager=batch_pool_manager,
        batch_submitter=mock_batch_submitter,
    )


@pytest.fixture
def sample_comparison_task() -> ComparisonTask:
    """Create sample comparison task."""
    essay_a = EssayForComparison(
        id="essay_a_123",
        text_content="This is essay A content",
        current_bt_score=0.5,
    )
    essay_b = EssayForComparison(
        id="essay_b_456",
        text_content="This is essay B content",
        current_bt_score=0.3,
    )
    return ComparisonTask(
        essay_a=essay_a,
        essay_b=essay_b,
        prompt="Compare these essays",
    )


@pytest.fixture
def empty_failed_pool() -> FailedComparisonPool:
    """Create empty failed comparison pool."""
    return FailedComparisonPool(
        failed_comparison_pool=[],
        pool_statistics=FailedComparisonPoolStatistics(),
    )


@pytest.fixture
def sample_batch_state(empty_failed_pool: FailedComparisonPool) -> CJBatchState:
    """Create sample batch state with empty failed pool."""
    batch_state = MagicMock(spec=CJBatchState)
    batch_state.batch_id = 123
    batch_state.processing_metadata = empty_failed_pool.model_dump()
    return batch_state
