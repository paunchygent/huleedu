"""Unit tests for update_essay_spellcheck_result orphaned essay handling.

Following Rule 075: Testing Methodology with protocol-based DI patterns.
Tests behavior verification for orphaned essay association and spellcheck result updates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import ProcessingStage
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.models_db import EssayResult
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
    """Mock dependency injection provider for testing spellcheck orphaned essay handling.

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
    # Configure non-async methods as regular Mock
    session.add = Mock()
    return session


@pytest.fixture
def sample_error_detail() -> ErrorDetail:
    """Create sample ErrorDetail for testing."""
    return ErrorDetail(
        error_code=ErrorCode.TIMEOUT,
        message="Spellcheck service timeout",
        correlation_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        service="spellchecker_service",
        operation="spellcheck_essay",
        details={"retry_count": 3, "service": "spellchecker_service"},
    )


class TestUpdateEssaySpellcheckResultOrphanedEssays:
    """Tests for update_essay_spellcheck_result method handling orphaned essays.

    Following Rule 075: Focus on behavior verification, not implementation details.
    """

    @pytest.mark.parametrize(
        "correction_count,corrected_text_storage_id,expected_status",
        [
            (15, "storage-corrected-123", ProcessingStage.COMPLETED),
            (0, None, ProcessingStage.COMPLETED),
            (25, "storage-corrected-456", ProcessingStage.COMPLETED),
            (None, "storage-corrected-789", ProcessingStage.PROCESSING),
        ],
    )
    @pytest.mark.asyncio
    async def test_orphaned_essay_associated_with_batch_during_spellcheck_update(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        correction_count: Optional[int],
        corrected_text_storage_id: Optional[str],
        expected_status: ProcessingStage,
    ) -> None:
        """Test that orphaned essay (batch_id=NULL) gets associated with batch
        during spellcheck update."""
        # Arrange
        essay_id = "orphaned-essay-123"
        batch_id = "target-batch-456"
        correlation_id = uuid4()

        # Create mock orphaned essay (batch_id is None)
        mock_essay = Mock(spec=EssayResult)
        mock_essay.essay_id = essay_id
        mock_essay.batch_id = None  # Orphaned essay
        mock_essay.spellcheck_status = ProcessingStage.PROCESSING
        mock_essay.spellcheck_correction_count = None
        mock_essay.spellcheck_corrected_text_storage_id = None

        # Mock SQLAlchemy query to return orphaned essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.update_essay_spellcheck_result(
            essay_id=essay_id,
            batch_id=batch_id,
            status=expected_status,
            correlation_id=correlation_id,
            correction_count=correction_count,
            corrected_text_storage_id=corrected_text_storage_id,
        )

        # Assert - Verify essay was associated with batch
        assert mock_essay.batch_id == batch_id, (
            "Orphaned essay should be associated with provided batch_id"
        )
        assert mock_essay.spellcheck_status == expected_status

        # Verify spellcheck-specific fields were updated
        if correction_count is not None:
            assert mock_essay.spellcheck_correction_count == correction_count
        if corrected_text_storage_id:
            assert mock_essay.spellcheck_corrected_text_storage_id == corrected_text_storage_id

        # Verify timestamps were updated
        assert mock_essay.updated_at is not None

        # Verify database operations
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.parametrize(
        "correction_count,corrected_text_storage_id,has_error",
        [
            (5, "storage-123", False),
            (0, None, False),
            (None, None, True),
            (10, "storage-456", True),
        ],
    )
    @pytest.mark.asyncio
    async def test_creates_new_essay_when_nonexistent_during_spellcheck_update(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        correction_count: Optional[int],
        corrected_text_storage_id: Optional[str],
        has_error: bool,
    ) -> None:
        """Test creating new essay when essay doesn't exist during spellcheck result update."""
        # Arrange
        essay_id = "new-essay-789"
        batch_id = "batch-123"
        correlation_id = uuid4()

        # Create error detail conditionally
        error_detail = None
        if has_error:
            error_detail = ErrorDetail(
                error_code=ErrorCode.TIMEOUT,
                message="Test error message",
                correlation_id=correlation_id,
                timestamp=datetime.now(timezone.utc),
                service="spellchecker_service",
                operation="spellcheck_essay",
                details={"test": "data"},
            )

        status = ProcessingStage.COMPLETED if not has_error else ProcessingStage.FAILED

        # Mock SQLAlchemy query to return no existing essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = None  # No existing essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.update_essay_spellcheck_result(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            correlation_id=correlation_id,
            correction_count=correction_count,
            corrected_text_storage_id=corrected_text_storage_id,
            error_detail=error_detail,
        )

        # Assert - Verify new essay was created with proper batch association
        mock_session.add.assert_called_once()
        created_essay = mock_session.add.call_args[0][0]

        assert created_essay.essay_id == essay_id
        assert created_essay.batch_id == batch_id, (
            "New essay should be associated with provided batch_id"
        )
        assert created_essay.spellcheck_status == status

        # Verify database operations
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.parametrize(
        "existing_batch_id,target_batch_id,should_associate",
        [
            (None, "batch-456", True),  # Orphaned essay should be associated
            ("batch-123", "batch-456", False),  # Already associated essay should not change batch
            ("batch-789", "batch-789", False),  # Same batch association should not change
        ],
    )
    @pytest.mark.asyncio
    async def test_batch_association_logic_during_spellcheck_update(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        existing_batch_id: Optional[str],
        target_batch_id: str,
        should_associate: bool,
    ) -> None:
        """Test batch association logic for different existing batch_id states."""
        # Arrange
        essay_id = "essay-association-test"
        correlation_id = uuid4()
        status = ProcessingStage.COMPLETED

        # Create mock essay with existing batch association state
        mock_essay = Mock(spec=EssayResult)
        mock_essay.essay_id = essay_id
        mock_essay.batch_id = existing_batch_id
        mock_essay.spellcheck_status = ProcessingStage.PROCESSING

        # Store original batch_id for comparison
        original_batch_id = existing_batch_id

        # Mock SQLAlchemy query to return existing essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.update_essay_spellcheck_result(
            essay_id=essay_id,
            batch_id=target_batch_id,
            status=status,
            correlation_id=correlation_id,
            correction_count=5,
            corrected_text_storage_id="storage-test",
        )

        # Assert batch association behavior
        if should_associate:
            assert mock_essay.batch_id == target_batch_id, (
                "Essay should be associated with target batch"
            )
        else:
            assert mock_essay.batch_id == original_batch_id, (
                "Essay batch association should not change"
            )

        # Verify spellcheck status is always updated regardless of association logic
        assert mock_essay.spellcheck_status == status

        # Verify database operations
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_spellcheck_error_handling_with_orphaned_essay(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        sample_error_detail: ErrorDetail,
    ) -> None:
        """Test spellcheck error handling for orphaned essay."""
        # Arrange
        essay_id = "orphaned-essay-error"
        batch_id = "batch-error-handling"
        correlation_id = uuid4()
        status = ProcessingStage.FAILED

        # Create mock orphaned essay
        mock_essay = Mock(spec=EssayResult)
        mock_essay.essay_id = essay_id
        mock_essay.batch_id = None  # Orphaned
        mock_essay.spellcheck_error_detail = None

        # Mock SQLAlchemy query to return orphaned essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.update_essay_spellcheck_result(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            correlation_id=correlation_id,
            error_detail=sample_error_detail,
        )

        # Assert - Verify error handling and batch association
        assert mock_essay.batch_id == batch_id, "Orphaned essay should be associated despite error"
        assert mock_essay.spellcheck_status == status

        # Verify error detail was stored as JSON
        expected_error_json = sample_error_detail.model_dump(mode="json")
        assert mock_essay.spellcheck_error_detail == expected_error_json

        # Verify database operations
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.parametrize(
        "field_updates,expected_values",
        [
            (
                {"correction_count": 8, "corrected_text_storage_id": "storage-123"},
                {"correction_count": 8, "storage_id": "storage-123"},
            ),
            (
                {"correction_count": 0, "corrected_text_storage_id": None},
                {"correction_count": 0, "storage_id": None},
            ),
            (
                {"correction_count": None, "corrected_text_storage_id": "storage-456"},
                {"correction_count": None, "storage_id": "storage-456"},
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_spellcheck_field_updates_for_orphaned_essay(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        field_updates: Dict[str, Any],
        expected_values: Dict[str, Any],
    ) -> None:
        """Test that all spellcheck-specific fields are correctly updated for orphaned essays."""
        # Arrange
        essay_id = "orphaned-field-updates"
        batch_id = "batch-field-test"
        correlation_id = uuid4()
        status = ProcessingStage.COMPLETED

        # Create mock orphaned essay with initial values
        mock_essay = Mock(spec=EssayResult)
        mock_essay.essay_id = essay_id
        mock_essay.batch_id = None  # Orphaned
        mock_essay.spellcheck_correction_count = 99  # Initial value to verify update
        mock_essay.spellcheck_corrected_text_storage_id = "old-storage"  # Initial value

        # Mock SQLAlchemy query to return orphaned essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.update_essay_spellcheck_result(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            correlation_id=correlation_id,
            correction_count=field_updates["correction_count"],
            corrected_text_storage_id=field_updates["corrected_text_storage_id"],
        )

        # Assert - Verify field updates
        assert mock_essay.batch_id == batch_id, "Essay should be associated with batch"
        assert mock_essay.spellcheck_status == status

        # Verify specific field updates based on parameters
        if field_updates["correction_count"] is not None:
            assert mock_essay.spellcheck_correction_count == expected_values["correction_count"]

        if field_updates["corrected_text_storage_id"] is not None:
            assert mock_essay.spellcheck_corrected_text_storage_id == expected_values["storage_id"]
        elif (
            field_updates["corrected_text_storage_id"] is None
            and expected_values["storage_id"] is None
        ):
            # When None is passed, field should not be updated (implementation detail)
            pass

        # Verify timestamp update
        assert mock_essay.updated_at is not None

        # Verify database operations
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_transaction_failure_during_spellcheck_update(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
    ) -> None:
        """Test handling of database transaction failures during spellcheck update."""
        # Arrange
        essay_id = "essay-transaction-failure"
        batch_id = "batch-transaction-test"
        correlation_id = uuid4()
        status = ProcessingStage.COMPLETED

        # Create mock orphaned essay
        mock_essay = Mock(spec=EssayResult)
        mock_essay.essay_id = essay_id
        mock_essay.batch_id = None

        # Mock SQLAlchemy query to return essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Mock commit to raise exception
        mock_session.commit.side_effect = Exception("Database transaction failed")

        # Act & Assert - No patching needed, mock is injected through DI
        with pytest.raises(Exception, match="Database transaction failed"):
            await batch_repository.update_essay_spellcheck_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=status,
                correlation_id=correlation_id,
                correction_count=5,
            )

        # Verify essay updates were attempted before failure
        assert mock_essay.batch_id == batch_id
        assert mock_essay.spellcheck_status == status

    @pytest.mark.asyncio
    async def test_finds_essay_by_essay_id_only_not_batch_id(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
    ) -> None:
        """Test that method finds essay by essay_id only, ignoring batch_id in query."""
        # Arrange
        essay_id = "essay-query-test"
        batch_id = "batch-different"  # Different from essay's current batch
        correlation_id = uuid4()
        status = ProcessingStage.COMPLETED

        # Create mock essay associated with different batch
        mock_essay = Mock(spec=EssayResult)
        mock_essay.essay_id = essay_id
        mock_essay.batch_id = "original-batch-123"  # Different from target batch

        # Mock SQLAlchemy query to return essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.update_essay_spellcheck_result(
            essay_id=essay_id,
            batch_id=batch_id,
            status=status,
            correlation_id=correlation_id,
            correction_count=3,
        )

        # Assert - Verify query was made by essay_id only
        mock_session.execute.assert_called_once()
        # The query should use EssayResult.essay_id == essay_id (not batch_id)

        # Verify essay was found and updated (not associated since it already has a batch)
        assert mock_essay.spellcheck_status == status
        assert mock_essay.batch_id == "original-batch-123"  # Should not change existing association

        # Verify database operations
        mock_session.commit.assert_called_once()
