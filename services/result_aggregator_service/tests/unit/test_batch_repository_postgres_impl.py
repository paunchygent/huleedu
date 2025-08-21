"""Unit tests for BatchRepositoryPostgresImpl.mark_batch_completed method.

Following Rule 075: Testing Methodology with protocol-based DI patterns.
Tests behavior verification for batch completion marking functionality.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from common_core.status_enums import BatchStatus
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.models_db import BatchResult
from services.result_aggregator_service.protocols import BatchRepositoryProtocol


def create_mock_session_factory(mock_session: AsyncMock) -> MagicMock:
    """Create a mock session factory that returns an async context manager.

    Following proper DI pattern from Rule 042.
    """
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__.return_value = mock_session
    mock_context_manager.__aexit__.return_value = None

    mock_factory = MagicMock()
    mock_factory.return_value = mock_context_manager
    return mock_factory


class MockDIProvider(Provider):
    """Mock dependency injection provider for testing BatchRepositoryPostgresImpl.

    Following Rule 075 pattern of protocol-based DI testing.
    """

    def __init__(self, mock_session: AsyncMock) -> None:
        super().__init__()
        # Create mock settings with proper PostgreSQL test URL
        self.mock_settings = Mock(spec=Settings)
        self.mock_settings.DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/test"
        self.mock_settings.DATABASE_POOL_SIZE = 5
        self.mock_settings.DATABASE_MAX_OVERFLOW = 10

        # Store the mock session for injection
        self.mock_session = mock_session

    @provide(scope=Scope.REQUEST)
    def provide_settings(self) -> Settings:
        """Provide mock settings for testing."""
        return self.mock_settings

    @provide(scope=Scope.REQUEST)
    def provide_batch_repository(
        self,
        settings: Settings,
    ) -> BatchRepositoryProtocol:
        """Provide BatchRepositoryPostgresImpl with properly mocked session factory.

        Following Rule 042: Inject mocks through constructor, not patching.
        """
        # Create a proper mock session factory that returns async context manager
        mock_session_factory = create_mock_session_factory(self.mock_session)

        repository = BatchRepositoryPostgresImpl(session_factory=mock_session_factory, metrics=None)
        return repository


@pytest.fixture
def test_provider(mock_session: AsyncMock) -> MockDIProvider:
    """Provide test provider instance with mock session."""
    return MockDIProvider(mock_session)


@pytest.fixture
async def di_container(test_provider: MockDIProvider) -> AsyncGenerator[AsyncContainer, None]:
    """Provide a Dishka container with mocked dependencies for testing."""
    container = make_async_container(test_provider)
    yield container
    await container.close()


@pytest.fixture
async def batch_repository(
    di_container: AsyncContainer,
) -> AsyncGenerator[BatchRepositoryProtocol, None]:
    """Provide batch repository from DI container."""
    async with di_container(scope=Scope.REQUEST) as request_container:
        repository = await request_container.get(BatchRepositoryProtocol)
        yield repository


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session for testing."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    return session


@pytest.fixture
def mock_batch_result() -> Mock:
    """Create mock BatchResult for testing."""
    batch_result = Mock(spec=BatchResult)
    batch_result.batch_metadata = {"existing": "data"}
    return batch_result


class TestMarkBatchCompleted:
    """Tests for mark_batch_completed method.

    Following Rule 075: Focus on behavior verification, not implementation details.
    """

    @pytest.mark.parametrize(
        "final_status,successful_essays,failed_essays,expected_status",
        [
            ("completed_successfully", 25, 0, BatchStatus.COMPLETED_SUCCESSFULLY),
            ("completed_with_failures", 22, 3, BatchStatus.COMPLETED_WITH_FAILURES),
            ("completed_successfully", 1, 0, BatchStatus.COMPLETED_SUCCESSFULLY),
            ("completed_with_failures", 0, 5, BatchStatus.COMPLETED_WITH_FAILURES),
        ],
    )
    @pytest.mark.asyncio
    async def test_mark_batch_completed_success_scenarios(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        mock_batch_result: Mock,
        final_status: str,
        successful_essays: int,
        failed_essays: int,
        expected_status: BatchStatus,
    ) -> None:
        """Test successful batch completion marking with various scenarios."""
        # Arrange
        batch_id = "test-batch-success"
        completion_stats = {
            "successful_essays": successful_essays,
            "failed_essays": failed_essays,
            "duration_seconds": 45.2,
            "completed_phases": ["spellcheck", "cj_assessment"],
        }

        mock_batch_result.batch_id = batch_id

        # Mock SQLAlchemy query result
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_batch_result
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.mark_batch_completed(
            batch_id=batch_id, final_status=final_status, completion_stats=completion_stats
        )

        # Assert - Verify business logic behavior
        assert mock_batch_result.overall_status == expected_status
        assert mock_batch_result.completed_essay_count == successful_essays
        assert mock_batch_result.failed_essay_count == failed_essays

        # Verify timestamps were set
        assert mock_batch_result.processing_completed_at is not None
        assert mock_batch_result.updated_at is not None

        # Verify metadata was updated with completion stats
        assert "completion_stats" in mock_batch_result.batch_metadata
        assert mock_batch_result.batch_metadata["completion_stats"] == completion_stats
        assert "completed_at" in mock_batch_result.batch_metadata

        # Verify database operations were called
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.parametrize(
        "existing_metadata,expected_preserved_fields",
        [
            ({"existing_field": "value1", "another_field": 123}, 2),
            ({"complex_data": {"nested": "structure"}}, 1),
            ({}, 0),
            (None, 0),
        ],
    )
    @pytest.mark.asyncio
    async def test_mark_batch_completed_metadata_handling(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        existing_metadata: dict[str, Any] | None,
        expected_preserved_fields: int,
    ) -> None:
        """Test proper handling of existing metadata during completion."""
        # Arrange
        batch_id = "test-batch-metadata"
        final_status = "completed_successfully"
        completion_stats = {
            "successful_essays": 18,
            "failed_essays": 2,
            "duration_seconds": 55.7,
            "completed_phases": ["spellcheck", "cj_assessment"],
        }

        mock_batch_result = Mock(spec=BatchResult)
        mock_batch_result.batch_id = batch_id
        mock_batch_result.batch_metadata = existing_metadata

        # Mock SQLAlchemy query result
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_batch_result
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.mark_batch_completed(
            batch_id=batch_id, final_status=final_status, completion_stats=completion_stats
        )

        # Assert
        # Verify metadata is a dict and contains completion data
        assert isinstance(mock_batch_result.batch_metadata, dict)
        assert "completion_stats" in mock_batch_result.batch_metadata
        assert "completed_at" in mock_batch_result.batch_metadata
        assert mock_batch_result.batch_metadata["completion_stats"] == completion_stats

        # Verify existing metadata was preserved if it existed
        if existing_metadata:
            for key, value in existing_metadata.items():
                assert mock_batch_result.batch_metadata[key] == value

        # Verify correct number of preserved fields plus new completion fields
        expected_total_fields = expected_preserved_fields + 2  # completion_stats + completed_at
        assert len(mock_batch_result.batch_metadata) == expected_total_fields

    @pytest.mark.asyncio
    async def test_mark_batch_completed_batch_not_found(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
    ) -> None:
        """Test graceful handling when batch is not found."""
        # Arrange
        batch_id = "nonexistent-batch"
        final_status = "completed_successfully"
        completion_stats = {
            "successful_essays": 10,
            "failed_essays": 0,
            "duration_seconds": 30.0,
            "completed_phases": ["spellcheck"],
        }

        # Mock database to return None (batch not found)
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - should not raise exception
        await batch_repository.mark_batch_completed(
            batch_id=batch_id, final_status=final_status, completion_stats=completion_stats
        )

        # Assert
        # Verify database was queried
        mock_session.execute.assert_called_once()
        # Verify no commit was attempted since batch wasn't found
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_batch_completed_database_transaction_failure(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        mock_batch_result: Mock,
    ) -> None:
        """Test handling of database transaction failures."""
        # Arrange
        batch_id = "test-batch-error"
        final_status = "completed_successfully"
        completion_stats = {
            "successful_essays": 15,
            "failed_essays": 0,
            "duration_seconds": 35.0,
            "completed_phases": ["spellcheck"],
        }

        mock_batch_result.batch_id = batch_id
        mock_batch_result.batch_metadata = {}

        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_batch_result
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock commit to raise exception
        mock_session.commit.side_effect = Exception("Database connection failed")

        # Act & Assert - No patching needed, mock is injected through DI
        with pytest.raises(Exception, match="Database connection failed"):
            await batch_repository.mark_batch_completed(
                batch_id=batch_id, final_status=final_status, completion_stats=completion_stats
            )

        # Verify batch updates were attempted before failure
        assert mock_batch_result.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY

    @pytest.mark.asyncio
    async def test_mark_batch_completed_field_updates(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        mock_batch_result: Mock,
    ) -> None:
        """Test that all required fields are properly updated."""
        # Arrange
        batch_id = "test-batch-fields"
        final_status = "completed_successfully"
        completion_stats = {
            "successful_essays": 20,
            "failed_essays": 1,
            "duration_seconds": 50.0,
            "completed_phases": ["spellcheck", "cj_assessment"],
        }

        mock_batch_result.batch_id = batch_id
        mock_batch_result.batch_metadata = {"existing": "data"}

        # Store original values to verify they changed
        original_completed_at = mock_batch_result.processing_completed_at
        original_updated_at = mock_batch_result.updated_at

        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_batch_result
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.mark_batch_completed(
            batch_id=batch_id, final_status=final_status, completion_stats=completion_stats
        )

        # Assert all field updates
        assert mock_batch_result.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
        assert mock_batch_result.completed_essay_count == 20
        assert mock_batch_result.failed_essay_count == 1

        # Verify timestamp fields were updated
        assert mock_batch_result.processing_completed_at != original_completed_at
        assert mock_batch_result.updated_at != original_updated_at
        assert mock_batch_result.processing_completed_at is not None
        assert mock_batch_result.updated_at is not None

        # Verify metadata updates
        assert "completion_stats" in mock_batch_result.batch_metadata
        assert "completed_at" in mock_batch_result.batch_metadata
        assert mock_batch_result.batch_metadata["completion_stats"] == completion_stats

        # Verify completed_at is ISO format string
        completed_at = mock_batch_result.batch_metadata["completed_at"]
        assert isinstance(completed_at, str)
        # Verify it can be parsed as datetime
        datetime.fromisoformat(completed_at.replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_mark_batch_completed_enum_conversion(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        mock_batch_result: Mock,
    ) -> None:
        """Test proper conversion of string status to BatchStatus enum."""
        # Arrange
        batch_id = "test-batch-enum"
        final_status = "completed_with_failures"  # String input
        completion_stats = {
            "successful_essays": 15,
            "failed_essays": 5,
            "duration_seconds": 60.0,
            "completed_phases": ["spellcheck"],
        }

        mock_batch_result.batch_id = batch_id
        mock_batch_result.batch_metadata = None

        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_batch_result
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.mark_batch_completed(
            batch_id=batch_id, final_status=final_status, completion_stats=completion_stats
        )

        # Assert
        # Verify string was converted to enum correctly
        assert mock_batch_result.overall_status == BatchStatus.COMPLETED_WITH_FAILURES
        assert isinstance(mock_batch_result.overall_status, BatchStatus)

        # Verify metadata was initialized from None
        assert mock_batch_result.batch_metadata is not None
        assert isinstance(mock_batch_result.batch_metadata, dict)
        assert mock_batch_result.batch_metadata["completion_stats"] == completion_stats
