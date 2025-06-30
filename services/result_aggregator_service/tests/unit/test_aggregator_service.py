"""Unit tests for AggregatorServiceImpl."""

from __future__ import annotations

from typing import List, Optional
from unittest.mock import AsyncMock

import pytest

from common_core.status_enums import BatchStatus, ProcessingStage
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.aggregator_service_impl import (
    AggregatorServiceImpl,
)
from services.result_aggregator_service.models_db import BatchResult, EssayResult
from services.result_aggregator_service.protocols import (
    BatchRepositoryProtocol,
    CacheManagerProtocol,
)


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        SERVICE_NAME="test_aggregator",
        REDIS_URL="redis://localhost:6379",
        DATABASE_URL="postgresql://test:test@localhost/test",
        INTERNAL_API_KEY="test-key",
        ALLOWED_SERVICE_IDS=["test-service"],
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_CONSUMER_GROUP_ID="test-group",
    )


@pytest.fixture
def mock_batch_repository() -> AsyncMock:
    """Create a mock batch repository."""
    return AsyncMock(spec=BatchRepositoryProtocol)


@pytest.fixture
def mock_cache_manager() -> AsyncMock:
    """Create a mock cache manager."""
    return AsyncMock(spec=CacheManagerProtocol)


@pytest.fixture
def aggregator_service(
    mock_batch_repository: AsyncMock,
    mock_cache_manager: AsyncMock,
    settings: Settings,
) -> AggregatorServiceImpl:
    """Create an aggregator service instance with mocked dependencies."""
    return AggregatorServiceImpl(
        batch_repository=mock_batch_repository,
        cache_manager=mock_cache_manager,
        settings=settings,
    )


def create_mock_batch_result(
    batch_id: str,
    user_id: str,
    overall_status: BatchStatus,
    essay_count: int,
    essays: List[AsyncMock],
    error_message: Optional[str] = None,
) -> AsyncMock:
    """Create a mock BatchResult object."""
    mock_batch: AsyncMock = AsyncMock(spec=BatchResult)
    mock_batch.batch_id = batch_id
    mock_batch.user_id = user_id
    mock_batch.overall_status = overall_status
    mock_batch.essay_count = essay_count
    mock_batch.essays = essays
    mock_batch.last_error = error_message
    mock_batch.completed_essay_count = len(
        [e for e in essays if e.spellcheck_status == ProcessingStage.COMPLETED.value]
    )
    mock_batch.failed_essay_count = len(
        [e for e in essays if e.spellcheck_status == ProcessingStage.FAILED.value]
    )
    return mock_batch


def create_mock_essay_result(
    essay_id: str,
    batch_id: str,
    spellcheck_status: Optional[ProcessingStage] = None,
    spellcheck_correction_count: Optional[int] = None,
    spellcheck_error: Optional[str] = None,
    cj_assessment_status: Optional[ProcessingStage] = None,
    cj_rank: Optional[int] = None,
    cj_score: Optional[float] = None,
) -> AsyncMock:
    """Create a mock EssayResult object."""
    mock_essay: AsyncMock = AsyncMock(spec=EssayResult)
    mock_essay.essay_id = essay_id
    mock_essay.batch_id = batch_id
    mock_essay.spellcheck_status = spellcheck_status.value if spellcheck_status else None
    mock_essay.spellcheck_correction_count = spellcheck_correction_count
    mock_essay.spellcheck_error = spellcheck_error
    mock_essay.cj_assessment_status = cj_assessment_status.value if cj_assessment_status else None
    mock_essay.cj_rank = cj_rank
    mock_essay.cj_score = cj_score
    return mock_essay


class TestAggregatorServiceImpl:
    """Test cases for AggregatorServiceImpl."""

    async def test_get_batch_status_success(
        self,
        aggregator_service: AggregatorServiceImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test successful retrieval of batch status."""
        # Arrange
        batch_id: str = "batch-123"

        essays: List[AsyncMock] = [
            create_mock_essay_result(
                essay_id="essay-1",
                batch_id=batch_id,
                spellcheck_status=ProcessingStage.COMPLETED,
                spellcheck_correction_count=5,
                cj_assessment_status=ProcessingStage.COMPLETED,
                cj_rank=1,
                cj_score=0.95,
            ),
            create_mock_essay_result(
                essay_id="essay-2",
                batch_id=batch_id,
                spellcheck_status=ProcessingStage.COMPLETED,
                spellcheck_correction_count=2,
                cj_assessment_status=ProcessingStage.COMPLETED,
                cj_rank=2,
                cj_score=0.85,
            ),
            create_mock_essay_result(
                essay_id="essay-3",
                batch_id=batch_id,
                spellcheck_status=ProcessingStage.FAILED,
                spellcheck_error="Timeout error",
                cj_assessment_status=ProcessingStage.PENDING,
            ),
        ]

        batch_result: AsyncMock = create_mock_batch_result(
            batch_id=batch_id,
            user_id="user-456",
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            essay_count=3,
            essays=essays,
        )

        mock_batch_repository.get_batch.return_value = batch_result

        # Act
        result: Optional[BatchResult] = await aggregator_service.get_batch_status(batch_id)

        # Assert
        assert result is not None
        assert result.batch_id == batch_id
        assert result.user_id == "user-456"
        assert result.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
        assert len(result.essays) == 3

        # Verify first essay
        first_essay = result.essays[0]
        assert first_essay.essay_id == "essay-1"
        assert first_essay.spellcheck_status == ProcessingStage.COMPLETED.value
        assert first_essay.spellcheck_correction_count == 5
        assert first_essay.cj_assessment_status == ProcessingStage.COMPLETED.value
        assert first_essay.cj_rank == 1
        assert first_essay.cj_score == 0.95

        mock_batch_repository.get_batch.assert_called_once_with(batch_id)
        # Note: Cache manager is not used in this implementation (caching happens at API layer)
        mock_cache_manager.get_batch_status_json.assert_not_called()

    async def test_get_batch_status_not_found(
        self,
        aggregator_service: AggregatorServiceImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test get_batch_status when batch is not found."""
        # Arrange
        batch_id: str = "non-existent-batch"
        mock_batch_repository.get_batch.return_value = None

        # Act
        result: Optional[BatchResult] = await aggregator_service.get_batch_status(batch_id)

        # Assert
        assert result is None
        mock_batch_repository.get_batch.assert_called_once_with(batch_id)

    async def test_get_batch_status_repository_error(
        self,
        aggregator_service: AggregatorServiceImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test get_batch_status when repository raises an error."""
        # Arrange
        batch_id: str = "batch-123"
        error_message: str = "Database connection error"
        mock_batch_repository.get_batch.side_effect = Exception(error_message)

        # Act & Assert
        with pytest.raises(Exception, match=error_message):
            await aggregator_service.get_batch_status(batch_id)

        mock_batch_repository.get_batch.assert_called_once_with(batch_id)

    async def test_get_user_batches_success(
        self,
        aggregator_service: AggregatorServiceImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test successful retrieval of user batches."""
        # Arrange
        user_id: str = "user-456"
        status: Optional[str] = BatchStatus.COMPLETED_SUCCESSFULLY.value
        limit: int = 10
        offset: int = 0

        batch_results: List[AsyncMock] = [
            create_mock_batch_result(
                batch_id="batch-1",
                user_id=user_id,
                overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
                essay_count=2,
                essays=[],
            ),
            create_mock_batch_result(
                batch_id="batch-2",
                user_id=user_id,
                overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
                essay_count=3,
                essays=[],
            ),
        ]

        mock_batch_repository.get_user_batches.return_value = batch_results

        # Act
        result: List[BatchResult] = await aggregator_service.get_user_batches(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
        )

        # Assert
        assert len(result) == 2
        assert result[0].batch_id == "batch-1"
        assert result[1].batch_id == "batch-2"
        assert all(batch.user_id == user_id for batch in result)
        assert all(batch.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY for batch in result)

        mock_batch_repository.get_user_batches.assert_called_once_with(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def test_get_user_batches_empty_result(
        self,
        aggregator_service: AggregatorServiceImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test get_user_batches when no batches exist for user."""
        # Arrange
        user_id: str = "user-no-batches"
        empty_result: List[BatchResult] = []
        mock_batch_repository.get_user_batches.return_value = empty_result

        # Act
        result: List[BatchResult] = await aggregator_service.get_user_batches(
            user_id=user_id,
            status=None,
            limit=20,
            offset=0,
        )

        # Assert
        assert result == []
        assert isinstance(result, list)
        mock_batch_repository.get_user_batches.assert_called_once_with(
            user_id=user_id,
            status=None,
            limit=20,
            offset=0,
        )

    async def test_get_user_batches_with_pagination(
        self,
        aggregator_service: AggregatorServiceImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test get_user_batches with pagination parameters."""
        # Arrange
        user_id: str = "user-456"
        limit: int = 5
        offset: int = 10

        batch_results: List[AsyncMock] = [
            create_mock_batch_result(
                batch_id=f"batch-{i}",
                user_id=user_id,
                overall_status=BatchStatus.PROCESSING_PIPELINES,
                essay_count=1,
                essays=[],
            )
            for i in range(11, 16)  # Simulating offset
        ]

        mock_batch_repository.get_user_batches.return_value = batch_results

        # Act
        result: List[BatchResult] = await aggregator_service.get_user_batches(
            user_id=user_id,
            status=None,
            limit=limit,
            offset=offset,
        )

        # Assert
        assert len(result) == 5
        assert result[0].batch_id == "batch-11"
        assert result[4].batch_id == "batch-15"

        mock_batch_repository.get_user_batches.assert_called_once_with(
            user_id=user_id,
            status=None,
            limit=limit,
            offset=offset,
        )

    async def test_get_user_batches_repository_error(
        self,
        aggregator_service: AggregatorServiceImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test get_user_batches when repository raises an error."""
        # Arrange
        user_id: str = "user-456"
        error_message: str = "Database query timeout"
        mock_batch_repository.get_user_batches.side_effect = Exception(error_message)

        # Act & Assert
        with pytest.raises(Exception, match=error_message):
            await aggregator_service.get_user_batches(
                user_id=user_id,
                status=None,
                limit=20,
                offset=0,
            )

        mock_batch_repository.get_user_batches.assert_called_once()

    async def test_get_user_batches_filter_by_status(
        self,
        aggregator_service: AggregatorServiceImpl,
        mock_batch_repository: AsyncMock,
        mock_cache_manager: AsyncMock,
    ) -> None:
        """Test get_user_batches filtering by specific status."""
        # Arrange
        user_id: str = "user-456"
        status: str = BatchStatus.FAILED_CRITICALLY.value

        batch_results: List[AsyncMock] = [
            create_mock_batch_result(
                batch_id="batch-failed-1",
                user_id=user_id,
                overall_status=BatchStatus.FAILED_CRITICALLY,
                essay_count=2,
                essays=[],
                error_message="Critical processing error",
            ),
        ]

        mock_batch_repository.get_user_batches.return_value = batch_results

        # Act
        result: List[BatchResult] = await aggregator_service.get_user_batches(
            user_id=user_id,
            status=status,
            limit=20,
            offset=0,
        )

        # Assert
        assert len(result) == 1
        assert result[0].overall_status == BatchStatus.FAILED_CRITICALLY
        assert result[0].last_error == "Critical processing error"

        mock_batch_repository.get_user_batches.assert_called_once_with(
            user_id=user_id,
            status=status,
            limit=20,
            offset=0,
        )
