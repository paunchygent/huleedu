"""Shared test fixtures for failed comparison pool functionality."""

from __future__ import annotations

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
    CJBatchRepositoryProtocol,
    LLMInteractionProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.unit.test_mocks import MockSessionProvider


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings with failed pool configuration."""

    settings = Settings()
    settings.ENABLE_FAILED_COMPARISON_RETRY = True
    settings.FAILED_COMPARISON_RETRY_THRESHOLD = 5
    settings.MAX_RETRY_ATTEMPTS = 3
    settings.RETRY_BATCH_SIZE = 10
    return settings


@pytest.fixture
def mock_session_provider() -> MockSessionProvider:
    """Create mock session provider."""
    return MockSessionProvider()


@pytest.fixture
def mock_batch_repo() -> MagicMock:
    """Create mock batch repository protocol.

    Uses MagicMock with specific AsyncMock methods to avoid
    'coroutine never awaited' warnings during introspection.
    """
    repo = MagicMock(spec=CJBatchRepositoryProtocol)
    repo.get_batch_state = AsyncMock()
    repo.get_batch_state_for_update = AsyncMock()
    repo.get_cj_batch_upload = AsyncMock()
    repo.get_stuck_batches = AsyncMock()
    repo.get_batches_ready_for_completion = AsyncMock()
    repo.update_batch_state = AsyncMock()
    return repo


@pytest.fixture
def mock_database(
    mock_session_provider: MockSessionProvider, mock_batch_repo: MagicMock
) -> AsyncMock:
    """Create mock database protocol for backward compatibility.

    This fixture provides backward compatibility for tests not yet migrated
    to per-aggregate repositories. Creates an AsyncMock wrapper that shares
    the session provider with batch_pool_manager but allows test configuration.

    Note: Tests using this fixture should be migrated to use mock_session_provider
    and specific repository mocks (e.g., mock_batch_repo) directly.
    """
    # Create a wrapper with a configurable session mock
    wrapper = AsyncMock()

    # Create a session mock that tests can configure
    # but that delegates to the real session provider when called
    wrapper.session = AsyncMock(side_effect=mock_session_provider.session)

    # Wire batch repository methods for tests that need them
    wrapper.get_batch_state_for_update = mock_batch_repo.get_batch_state_for_update
    wrapper.get_cj_batch_upload = mock_batch_repo.get_cj_batch_upload
    wrapper.get_batch_state = mock_batch_repo.get_batch_state

    return wrapper


@pytest.fixture
def mock_llm_interaction() -> MagicMock:
    """Create mock LLM interaction protocol.

    Uses MagicMock container to avoid introspection warnings.
    """
    interaction = MagicMock(spec=LLMInteractionProtocol)
    interaction.submit_comparison_request = AsyncMock()
    interaction.submit_comparison_request_batch = AsyncMock()
    return interaction


@pytest.fixture
def batch_processor(
    mock_session_provider: SessionProviderProtocol,
    mock_batch_repo: MagicMock,
    mock_llm_interaction: LLMInteractionProtocol,
    mock_settings: Settings,
) -> BatchProcessor:
    """Create BatchProcessor instance with mocks."""
    return BatchProcessor(
        session_provider=mock_session_provider,
        llm_interaction=mock_llm_interaction,
        settings=mock_settings,
        batch_repository=mock_batch_repo,
    )


@pytest.fixture
def batch_pool_manager(
    mock_session_provider: SessionProviderProtocol,
    mock_batch_repo: MagicMock,
    mock_settings: Settings,
) -> BatchPoolManager:
    """Create BatchPoolManager instance with mocks."""
    return BatchPoolManager(
        session_provider=mock_session_provider,
        batch_repository=mock_batch_repo,
        settings=mock_settings,
    )


@pytest.fixture
def mock_batch_submitter() -> MagicMock:
    """Create mock batch submitter protocol.

    Uses MagicMock with AsyncMock method to be safe against introspection.
    """
    submitter = MagicMock(spec=BatchProcessorProtocol)
    submitter.submit_comparison_batch = AsyncMock()
    return submitter


@pytest.fixture
def batch_retry_processor(
    mock_session_provider: SessionProviderProtocol,
    mock_llm_interaction: LLMInteractionProtocol,
    mock_settings: Settings,
    batch_pool_manager: BatchPoolManager,
    mock_batch_submitter: AsyncMock,
) -> BatchRetryProcessor:
    """Create BatchRetryProcessor instance with mocks."""
    return BatchRetryProcessor(
        session_provider=mock_session_provider,
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
