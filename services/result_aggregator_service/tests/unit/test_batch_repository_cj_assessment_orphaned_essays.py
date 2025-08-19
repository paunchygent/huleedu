"""Unit tests for update_essay_cj_assessment_result orphaned essay handling.

Following Rule 075: Testing Methodology with protocol-based DI patterns.
Tests behavior verification for CJ assessment result updates with orphaned essays.
"""

from __future__ import annotations

from datetime import datetime
from typing import AsyncGenerator, Optional
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from common_core.error_enums import CJAssessmentErrorCode
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import ProcessingStage
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.models_db import EssayResult
from services.result_aggregator_service.protocols import BatchRepositoryProtocol


class MockDIProvider(Provider):
    """Mock dependency injection provider for testing BatchRepositoryPostgresImpl.

    Following Rule 075 pattern of protocol-based DI testing.
    """

    def __init__(self) -> None:
        super().__init__()
        # Create mock settings with proper PostgreSQL test URL
        self.mock_settings = Mock(spec=Settings)
        self.mock_settings.DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/test"
        self.mock_settings.DATABASE_POOL_SIZE = 5
        self.mock_settings.DATABASE_MAX_OVERFLOW = 10

        # Store reference to repository for later patching
        self.repository_instance: BatchRepositoryPostgresImpl | None = None

    @provide(scope=Scope.REQUEST)
    def provide_settings(self) -> Settings:
        """Provide mock settings for testing."""
        return self.mock_settings

    @provide(scope=Scope.REQUEST)
    def provide_batch_repository(
        self,
        settings: Settings,
    ) -> BatchRepositoryProtocol:
        """Provide BatchRepositoryPostgresImpl with mocked settings.

        Note: We'll patch the internal session management for unit testing.
        """
        # Mock the engine to avoid actual database connection
        mock_engine = AsyncMock()
        mock_session_maker = AsyncMock()

        repository = BatchRepositoryPostgresImpl(settings=settings, engine=mock_engine)
        # Override the session maker to prevent real database calls
        repository.async_session_maker = mock_session_maker
        self.repository_instance = repository
        return repository


@pytest.fixture
def test_provider() -> MockDIProvider:
    """Provide test provider instance."""
    return MockDIProvider()


@pytest.fixture
async def di_container(test_provider: MockDIProvider) -> AsyncGenerator[AsyncContainer, None]:
    """Provide a Dishka container with mocked dependencies for testing."""
    container = make_async_container(test_provider)
    yield container
    await container.close()


@pytest.fixture
async def batch_repository(
    di_container: AsyncContainer, test_provider: MockDIProvider
) -> AsyncGenerator[BatchRepositoryProtocol, None]:
    """Provide batch repository from DI container."""
    async with di_container(scope=Scope.REQUEST) as request_container:
        repository = await request_container.get(BatchRepositoryProtocol)
        # Store reference for access in tests
        test_provider.repository_instance = repository
        yield repository


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session for testing."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    # SQLAlchemy AsyncSession.add is a synchronous method; keep it non-awaitable in tests
    session.add = Mock()
    return session


def create_mock_essay_result(
    essay_id: str,
    batch_id: Optional[str] = None,
    cj_rank: Optional[int] = None,
    cj_score: Optional[float] = None,
    cj_comparison_count: Optional[int] = None,
) -> Mock:
    """Create a mock EssayResult for testing."""
    essay_result = Mock(spec=EssayResult)
    essay_result.essay_id = essay_id
    essay_result.batch_id = batch_id
    essay_result.cj_rank = cj_rank
    essay_result.cj_score = cj_score
    essay_result.cj_comparison_count = cj_comparison_count
    essay_result.cj_assessment_status = None
    essay_result.cj_assessment_error_detail = None
    essay_result.updated_at = None
    return essay_result


class TestUpdateEssayCjAssessmentResultOrphanedEssays:
    """Tests for update_essay_cj_assessment_result method focusing on orphaned essay handling.

    Following Rule 075: Focus on behavior verification, not implementation details.
    """

    @pytest.mark.parametrize(
        "rank,score,comparison_count,status",
        [
            (1, 95.5, 15, ProcessingStage.COMPLETED),
            (3, 78.2, 12, ProcessingStage.COMPLETED),
            (None, None, None, ProcessingStage.FAILED),
            (5, 88.0, 20, ProcessingStage.PROCESSING),
        ],
    )
    @pytest.mark.asyncio
    async def test_orphaned_essay_association_with_batch(
        self,
        batch_repository: BatchRepositoryProtocol,
        test_provider: MockDIProvider,
        mock_session: AsyncMock,
        rank: Optional[int],
        score: Optional[float],
        comparison_count: Optional[int],
        status: ProcessingStage,
    ) -> None:
        """Test that orphaned essays (batch_id=NULL) get associated with provided batch_id."""
        # Arrange
        essay_id = "orphaned-essay-123"
        batch_id = "target-batch-456"
        correlation_id = uuid4()

        # Create orphaned essay (batch_id=None)
        orphaned_essay = create_mock_essay_result(essay_id=essay_id, batch_id=None)

        # Mock SQLAlchemy query result to return orphaned essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = orphaned_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Patch the internal session management
        with patch.object(test_provider.repository_instance, "_get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_session.return_value.__aexit__.return_value = None

            # Act
            await batch_repository.update_essay_cj_assessment_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=status,
                correlation_id=correlation_id,
                rank=rank,
                score=score,
                comparison_count=comparison_count,
            )

        # Assert - Verify orphaned essay was associated with batch
        assert orphaned_essay.batch_id == batch_id
        assert orphaned_essay.cj_assessment_status == status

        # Verify CJ assessment fields were updated correctly
        if rank is not None:
            assert orphaned_essay.cj_rank == rank
        if score is not None:
            assert orphaned_essay.cj_score == score
        if comparison_count is not None:
            assert orphaned_essay.cj_comparison_count == comparison_count

        # Verify timestamp was updated
        assert orphaned_essay.updated_at is not None

        # Verify database operations were called
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.parametrize(
        "rank,score,comparison_count,error_message",
        [
            (2, 85.3, 18, None),
            (None, None, None, "CJ assessment processing failed"),
            (7, 92.1, 25, None),
            (None, None, None, "Timeout during comparison phase"),
        ],
    )
    @pytest.mark.asyncio
    async def test_nonexistent_essay_creation(
        self,
        batch_repository: BatchRepositoryProtocol,
        test_provider: MockDIProvider,
        mock_session: AsyncMock,
        rank: Optional[int],
        score: Optional[float],
        comparison_count: Optional[int],
        error_message: Optional[str],
    ) -> None:
        """Test that new essays are created when they don't exist."""
        # Arrange
        essay_id = "new-essay-789"
        batch_id = "batch-789"
        correlation_id = uuid4()
        status = ProcessingStage.FAILED if error_message else ProcessingStage.COMPLETED
        error_detail = (
            ErrorDetail(
                error_code=CJAssessmentErrorCode.CJ_COMPARISON_IMBALANCE,
                message=error_message,
                correlation_id=correlation_id,
                timestamp=datetime.utcnow(),
                service="result_aggregator_service",
                operation="update_essay_cj_assessment_result",
            )
            if error_message
            else None
        )

        # Mock SQLAlchemy query result to return None (essay doesn't exist)
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Patch the internal session management
        with patch.object(test_provider.repository_instance, "_get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_session.return_value.__aexit__.return_value = None

            # Act
            await batch_repository.update_essay_cj_assessment_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=status,
                correlation_id=correlation_id,
                rank=rank,
                score=score,
                comparison_count=comparison_count,
                error_detail=error_detail,
            )

        # Assert - Verify new essay was created and added to session
        # The method should create an EssayResult object and add it to the session
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify database was queried to check if essay exists
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_essay_with_batch_id_preserved(
        self,
        batch_repository: BatchRepositoryProtocol,
        test_provider: MockDIProvider,
        mock_session: AsyncMock,
    ) -> None:
        """Test that existing essays with batch_id keep their association."""
        # Arrange
        essay_id = "existing-essay-456"
        original_batch_id = "original-batch-123"
        new_batch_id = "new-batch-456"
        correlation_id = uuid4()

        # Create existing essay already associated with a batch
        existing_essay = create_mock_essay_result(
            essay_id=essay_id,
            batch_id=original_batch_id,
            cj_rank=3,
            cj_score=82.5,
        )

        # Mock SQLAlchemy query result to return existing essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = existing_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Patch the internal session management
        with patch.object(test_provider.repository_instance, "_get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_session.return_value.__aexit__.return_value = None

            # Act
            await batch_repository.update_essay_cj_assessment_result(
                essay_id=essay_id,
                batch_id=new_batch_id,
                status=ProcessingStage.COMPLETED,
                correlation_id=correlation_id,
                rank=1,
                score=95.0,
                comparison_count=20,
            )

        # Assert - Verify existing batch association is preserved
        assert existing_essay.batch_id == original_batch_id  # Should NOT change
        assert existing_essay.cj_assessment_status == ProcessingStage.COMPLETED
        assert existing_essay.cj_rank == 1
        assert existing_essay.cj_score == 95.0
        assert existing_essay.cj_comparison_count == 20

        # Verify database operations were called
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
        # Should not add new essay since it already exists
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_essay_search_by_essay_id_only(
        self,
        batch_repository: BatchRepositoryProtocol,
        test_provider: MockDIProvider,
        mock_session: AsyncMock,
    ) -> None:
        """Test that essay lookup uses essay_id only, not batch_id for orphaned essay handling."""
        # Arrange
        essay_id = "search-test-essay"
        batch_id = "search-test-batch"
        correlation_id = uuid4()

        existing_essay = create_mock_essay_result(essay_id=essay_id, batch_id=None)

        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = existing_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Patch the internal session management
        with patch.object(test_provider.repository_instance, "_get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_session.return_value.__aexit__.return_value = None

            # Act
            await batch_repository.update_essay_cj_assessment_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=ProcessingStage.COMPLETED,
                correlation_id=correlation_id,
                rank=2,
                score=88.5,
            )

        # Assert - Verify SQLAlchemy query was constructed correctly
        # The execute call should contain a select statement filtering by essay_id only
        mock_session.execute.assert_called_once()

        # We can't easily inspect the SQLAlchemy select object, but we know it was called
        # The behavior verification is that it found the essay and updated it
        assert existing_essay.batch_id == batch_id
        assert existing_essay.cj_assessment_status == ProcessingStage.COMPLETED

    @pytest.mark.parametrize(
        "has_error_detail,error_message",
        [
            (True, "CJ comparison failed"),
            (True, "Timeout during assessment"),
            (False, None),
        ],
    )
    @pytest.mark.asyncio
    async def test_error_detail_handling(
        self,
        batch_repository: BatchRepositoryProtocol,
        test_provider: MockDIProvider,
        mock_session: AsyncMock,
        has_error_detail: bool,
        error_message: Optional[str],
    ) -> None:
        """Test proper handling of error details in CJ assessment updates."""
        # Arrange
        essay_id = "error-test-essay"
        batch_id = "error-test-batch"
        correlation_id = uuid4()

        orphaned_essay = create_mock_essay_result(essay_id=essay_id, batch_id=None)
        error_detail = None
        if has_error_detail:
            error_detail = ErrorDetail(
                error_code=CJAssessmentErrorCode.CJ_INSUFFICIENT_COMPARISONS,
                message=error_message,
                correlation_id=correlation_id,
                timestamp=datetime.utcnow(),
                service="result_aggregator_service",
                operation="update_essay_cj_assessment_result",
            )

        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = orphaned_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Patch the internal session management
        with patch.object(test_provider.repository_instance, "_get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_session.return_value.__aexit__.return_value = None

            # Act
            await batch_repository.update_essay_cj_assessment_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=ProcessingStage.FAILED if has_error_detail else ProcessingStage.COMPLETED,
                correlation_id=correlation_id,
                error_detail=error_detail,
            )

        # Assert
        if has_error_detail:
            # Verify error detail was processed (method calls model_dump(mode="json"))
            assert orphaned_essay.cj_assessment_error_detail is not None
        else:
            # Verify no error detail when none provided
            assert orphaned_essay.cj_assessment_error_detail is None

        # Verify essay was associated with batch
        assert orphaned_essay.batch_id == batch_id

    @pytest.mark.asyncio
    async def test_optional_fields_partial_update(
        self,
        batch_repository: BatchRepositoryProtocol,
        test_provider: MockDIProvider,
        mock_session: AsyncMock,
    ) -> None:
        """Test that only provided optional fields are updated."""
        # Arrange
        essay_id = "partial-update-essay"
        batch_id = "partial-update-batch"
        correlation_id = uuid4()

        # Create essay with existing values
        existing_essay = create_mock_essay_result(
            essay_id=essay_id,
            batch_id=None,
            cj_rank=5,
            cj_score=75.0,
            cj_comparison_count=10,
        )

        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = existing_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Patch the internal session management
        with patch.object(test_provider.repository_instance, "_get_session") as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session
            mock_get_session.return_value.__aexit__.return_value = None

            # Act - Update only rank and score, not comparison_count
            await batch_repository.update_essay_cj_assessment_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=ProcessingStage.COMPLETED,
                correlation_id=correlation_id,
                rank=1,
                score=92.5,
                # comparison_count not provided - should preserve existing value
            )

        # Assert
        assert existing_essay.batch_id == batch_id
        assert existing_essay.cj_rank == 1  # Updated
        assert existing_essay.cj_score == 92.5  # Updated
        assert existing_essay.cj_comparison_count == 10  # Preserved existing value
        assert existing_essay.cj_assessment_status == ProcessingStage.COMPLETED
