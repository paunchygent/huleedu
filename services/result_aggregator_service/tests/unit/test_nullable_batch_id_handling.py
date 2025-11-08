"""Unit tests for nullable batch_id handling in Result Aggregator Service.

Following Rule 075: Testing Methodology with protocol-based DI patterns.
Tests behavior verification for nullable batch_id fix implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.events import BatchEssaysRegistered, EventEnvelope
from common_core.metadata_models import StorageReferenceMetadata, SystemProcessingMetadata
from common_core.status_enums import ProcessingStage
from dishka import AsyncContainer, Provider, Scope, make_async_container, provide

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.implementations.event_processor_impl import (
    EventProcessorImpl,
)
from services.result_aggregator_service.models_db import EssayResult
from services.result_aggregator_service.protocols import (
    BatchRepositoryProtocol,
    CacheManagerProtocol,
    EventProcessorProtocol,
    EventPublisherProtocol,
    StateStoreProtocol,
)


def make_prompt_ref(label: str) -> StorageReferenceMetadata:
    prompt_ref = StorageReferenceMetadata()
    prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, label)
    return prompt_ref


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
    """Mock dependency injection provider for testing nullable batch_id handling.

    Following Rule 075 pattern of protocol-based DI testing.
    """

    def __init__(self, mock_session: AsyncMock) -> None:
        super().__init__()
        # Create mock settings
        self.mock_settings = Mock(spec=Settings)
        self.mock_settings.DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/test"
        self.mock_settings.DATABASE_POOL_SIZE = 5
        self.mock_settings.DATABASE_MAX_OVERFLOW = 10

        # Store mocks as instance attributes for access in tests
        self.mock_batch_repo = AsyncMock(spec=BatchRepositoryProtocol)
        self.mock_state_store = AsyncMock(spec=StateStoreProtocol)
        self.mock_cache_manager = AsyncMock(spec=CacheManagerProtocol)
        self.mock_event_publisher = AsyncMock(spec=EventPublisherProtocol)

        # Store the mock session for injection
        self.mock_session = mock_session

    @provide(scope=Scope.REQUEST)
    def provide_settings(self) -> Settings:
        """Provide mock settings for testing."""
        return self.mock_settings

    @provide(scope=Scope.REQUEST)
    def provide_batch_repository(self, settings: Settings) -> BatchRepositoryProtocol:
        """Provide BatchRepositoryPostgresImpl with properly mocked session factory.

        Following Rule 042: Inject mocks through constructor, not patching.
        """
        # Create a proper mock session factory that returns async context manager
        mock_session_factory = create_mock_session_factory(self.mock_session)

        repository = BatchRepositoryPostgresImpl(session_factory=mock_session_factory, metrics=None)
        return repository

    @provide(scope=Scope.REQUEST)
    def provide_state_store(self) -> StateStoreProtocol:
        """Provide mock state store."""
        return self.mock_state_store

    @provide(scope=Scope.REQUEST)
    def provide_cache_manager(self) -> CacheManagerProtocol:
        """Provide mock cache manager."""
        return self.mock_cache_manager

    @provide(scope=Scope.REQUEST)
    def provide_event_publisher(self) -> EventPublisherProtocol:
        """Provide mock event publisher."""
        return self.mock_event_publisher

    @provide(scope=Scope.REQUEST)
    def provide_event_processor(
        self,
        batch_repository: BatchRepositoryProtocol,
        state_store: StateStoreProtocol,
        cache_manager: CacheManagerProtocol,
        event_publisher: EventPublisherProtocol,
    ) -> EventProcessorProtocol:
        """Provide EventProcessorImpl with mocked dependencies."""
        return EventProcessorImpl(
            batch_repository=batch_repository,
            state_store=state_store,
            cache_manager=cache_manager,
            event_publisher=event_publisher,
        )


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
async def event_processor(di_container: AsyncContainer) -> EventProcessorProtocol:
    """Provide event processor from DI container."""
    async with di_container(scope=Scope.REQUEST) as request_container:
        from typing import cast

        processor = await request_container.get(EventProcessorProtocol)
        return cast(EventProcessorProtocol, processor)


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session for testing."""
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    # Configure non-async methods as regular Mock
    session.add = Mock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


class TestUpdateEssayFileMapping:
    """Tests for update_essay_file_mapping method handling nullable batch_id."""

    @pytest.mark.parametrize(
        "text_storage_id,expected_text_storage",
        [
            ("storage-123", "storage-123"),
            (None, None),
            ("", None),  # Empty string should be treated as None
        ],
    )
    @pytest.mark.asyncio
    async def test_creates_essay_with_null_batch_id_when_essay_not_exists(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        text_storage_id: str | None,
        expected_text_storage: str | None,
    ) -> None:
        """Test creating essay with null batch_id when essay doesn't exist."""
        # Arrange
        essay_id = "essay-123"
        file_upload_id = "upload-456"

        # Mock SQLAlchemy query to return no existing essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = None  # No existing essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.update_essay_file_mapping(
            essay_id=essay_id,
            file_upload_id=file_upload_id,
            text_storage_id=text_storage_id,
        )

        # Assert - Verify new essay was created with null batch_id
        mock_session.add.assert_called_once()
        created_essay = mock_session.add.call_args[0][0]

        assert created_essay.essay_id == essay_id
        assert created_essay.batch_id is None  # Critical: batch_id should be None
        assert created_essay.file_upload_id == file_upload_id
        if expected_text_storage:
            assert created_essay.original_text_storage_id == expected_text_storage

        # Verify database operations
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.parametrize(
        "existing_batch_id,existing_text_storage,new_text_storage,expected_text_storage",
        [
            (None, None, "new-storage", "new-storage"),  # Orphaned essay gets text storage
            ("batch-456", "old-storage", "new-storage", "new-storage"),  # Associated essay updates
            (None, "old-storage", None, "old-storage"),  # No text storage provided, keep existing
            (
                "batch-789",
                None,
                "new-storage",
                "new-storage",
            ),  # Associated essay gets first text storage
        ],
    )
    @pytest.mark.asyncio
    async def test_updates_existing_essay_file_mapping(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
        existing_batch_id: str | None,
        existing_text_storage: str | None,
        new_text_storage: str | None,
        expected_text_storage: str | None,
    ) -> None:
        """Test updating existing essay file mapping preserves batch association."""
        # Arrange
        essay_id = "essay-existing"
        file_upload_id = "upload-new"

        # Create mock existing essay
        mock_essay = Mock(spec=EssayResult)
        mock_essay.essay_id = essay_id
        mock_essay.batch_id = existing_batch_id
        mock_essay.original_text_storage_id = existing_text_storage

        # Mock SQLAlchemy query to return existing essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.update_essay_file_mapping(
            essay_id=essay_id,
            file_upload_id=file_upload_id,
            text_storage_id=new_text_storage,
        )

        # Assert - Verify existing essay was updated
        assert mock_essay.file_upload_id == file_upload_id
        assert mock_essay.batch_id == existing_batch_id  # Preserve existing batch association
        if new_text_storage:
            assert mock_essay.original_text_storage_id == expected_text_storage

        # Verify no new essay was added
        mock_session.add.assert_not_called()

        # Verify database operations
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_database_errors_gracefully(
        self,
        batch_repository: BatchRepositoryPostgresImpl,
        mock_session: AsyncMock,
    ) -> None:
        """Test handling database errors during essay file mapping update."""
        # Arrange
        essay_id = "essay-error"
        file_upload_id = "upload-error"

        # Mock database error
        mock_session.execute.side_effect = Exception("Database connection lost")

        # Mock metrics recording methods using setattr to avoid type issues
        mock_record_operation = Mock()
        mock_record_error = Mock()
        setattr(
            batch_repository,
            "_record_operation_metrics",
            mock_record_operation,
        )
        setattr(batch_repository, "_record_error_metrics", mock_record_error)

        # Act & Assert - No patching needed, mock is injected through DI
        with pytest.raises(Exception, match="Database connection lost"):
            await batch_repository.update_essay_file_mapping(
                essay_id=essay_id,
                file_upload_id=file_upload_id,
            )

        # Verify error metrics were recorded
        mock_record_error.assert_called_once_with("Exception", "update_essay_file_mapping")


class TestAssociateEssayWithBatch:
    """Tests for associate_essay_with_batch method."""

    @pytest.mark.asyncio
    async def test_associates_orphaned_essay_with_batch(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
    ) -> None:
        """Test associating orphaned essay (batch_id=None) with its batch."""
        # Arrange
        essay_id = "orphaned-essay"
        batch_id = "new-batch-123"

        # Create mock orphaned essay
        mock_essay = Mock(spec=EssayResult)
        mock_essay.essay_id = essay_id
        mock_essay.batch_id = None  # Orphaned essay

        # Mock SQLAlchemy query to return orphaned essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = mock_essay
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.associate_essay_with_batch(
            essay_id=essay_id,
            batch_id=batch_id,
        )

        # Assert - Verify essay was associated with batch
        assert mock_essay.batch_id == batch_id
        assert mock_essay.updated_at is not None

        # Verify database operations
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_already_associated_essays(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
    ) -> None:
        """Test skipping essays that are already associated with a batch."""
        # Arrange
        essay_id = "associated-essay"
        batch_id = "new-batch-123"

        # Mock SQLAlchemy query to return no essay (already associated or doesn't exist)
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = None  # No orphaned essay found
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - No patching needed, mock is injected through DI
        await batch_repository.associate_essay_with_batch(
            essay_id=essay_id,
            batch_id=batch_id,
        )

        # Assert - Verify no changes were made (no essay found to update)
        # Verify database operations
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_missing_essay_gracefully(
        self,
        batch_repository: BatchRepositoryProtocol,
        mock_session: AsyncMock,
    ) -> None:
        """Test handling case where essay doesn't exist during association."""
        # Arrange
        essay_id = "non-existent-essay"
        batch_id = "batch-123"

        # Mock SQLAlchemy query to return no essay
        mock_result = Mock()
        mock_scalars = Mock()
        mock_scalars.first.return_value = None
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Act - Should not raise exception, no patching needed
        await batch_repository.associate_essay_with_batch(
            essay_id=essay_id,
            batch_id=batch_id,
        )

        # Assert - Verify graceful handling (no errors raised)
        mock_session.execute.assert_called_once()


class TestProcessBatchRegistered:
    """Tests for process_batch_registered method handling orphaned essays."""

    @pytest.fixture
    def mock_event_processor(self, test_provider: MockDIProvider) -> EventProcessorProtocol:
        """Provide event processor with pure mocks for simpler testing."""
        return EventProcessorImpl(
            batch_repository=test_provider.mock_batch_repo,
            state_store=test_provider.mock_state_store,
            cache_manager=test_provider.mock_cache_manager,
            event_publisher=test_provider.mock_event_publisher,
        )

    @pytest.mark.asyncio
    async def test_creates_batch_and_associates_orphaned_essays(
        self,
        mock_event_processor: EventProcessorProtocol,
        test_provider: MockDIProvider,
    ) -> None:
        """Test creating batch and associating orphaned essays during batch registration."""
        # Arrange
        batch_id = str(uuid4())
        user_id = str(uuid4())
        essay_ids = ["essay-1", "essay-2", "essay-3"]
        expected_essay_count = 3

        metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.INITIALIZED,
        )

        data = BatchEssaysRegistered(
            entity_id=batch_id,
            user_id=user_id,
            essay_ids=essay_ids,
            expected_essay_count=expected_essay_count,
            metadata=metadata,
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-nullable-batch"),
        )

        envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(timezone.utc),
            source_service="test",
            data=data,
        )

        # Act
        await mock_event_processor.process_batch_registered(envelope, data)

        # Assert - Verify batch creation
        assert data.student_prompt_ref is not None
        expected_metadata = {
            "student_prompt_ref": data.student_prompt_ref.model_dump(mode="json"),
        }
        test_provider.mock_batch_repo.create_batch.assert_called_once_with(
            batch_id=batch_id,
            user_id=user_id,
            essay_count=expected_essay_count,
            metadata=expected_metadata,
        )

        # Verify orphaned essay associations
        assert test_provider.mock_batch_repo.associate_essay_with_batch.call_count == len(essay_ids)

        # Verify each essay was associated
        for essay_id in essay_ids:
            test_provider.mock_batch_repo.associate_essay_with_batch.assert_any_call(
                essay_id=essay_id,
                batch_id=batch_id,
            )

        # Verify cache invalidation
        test_provider.mock_cache_manager.invalidate_user_batches.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_handles_batch_without_essay_ids(
        self,
        mock_event_processor: EventProcessorProtocol,
        test_provider: MockDIProvider,
    ) -> None:
        """Test handling batch registration when essay_ids attribute is missing."""
        # Arrange
        batch_id = str(uuid4())
        user_id = str(uuid4())
        expected_essay_count = 5

        metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.INITIALIZED,
        )

        # Create data without essay_ids attribute
        data = BatchEssaysRegistered(
            entity_id=batch_id,
            user_id=user_id,
            essay_ids=[],  # Empty list
            expected_essay_count=expected_essay_count,
            metadata=metadata,
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-nullable-missing"),
        )

        # Remove essay_ids to simulate missing attribute
        delattr(data, "essay_ids")

        envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(timezone.utc),
            source_service="test",
            data=data,
        )

        # Act
        await mock_event_processor.process_batch_registered(envelope, data)

        # Assert - Verify batch creation still works
        assert data.student_prompt_ref is not None
        expected_metadata = {
            "student_prompt_ref": data.student_prompt_ref.model_dump(mode="json"),
        }
        test_provider.mock_batch_repo.create_batch.assert_called_once_with(
            batch_id=batch_id,
            user_id=user_id,
            essay_count=expected_essay_count,
            metadata=expected_metadata,
        )

        # Verify no essay associations attempted
        test_provider.mock_batch_repo.associate_essay_with_batch.assert_not_called()

        # Verify cache invalidation still happens
        test_provider.mock_cache_manager.invalidate_user_batches.assert_called_once_with(user_id)

    @pytest.mark.asyncio
    async def test_processes_empty_essay_ids_list(
        self,
        mock_event_processor: EventProcessorProtocol,
        test_provider: MockDIProvider,
    ) -> None:
        """Test processing batch registration with empty essay_ids list."""
        # Arrange
        batch_id = str(uuid4())
        user_id = str(uuid4())
        expected_essay_count = 0

        metadata = SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            processing_stage=ProcessingStage.INITIALIZED,
        )

        data = BatchEssaysRegistered(
            entity_id=batch_id,
            user_id=user_id,
            essay_ids=[],  # Empty list
            expected_essay_count=expected_essay_count,
            metadata=metadata,
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-nullable-empty"),
        )

        envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(timezone.utc),
            source_service="test",
            data=data,
        )

        # Act
        await mock_event_processor.process_batch_registered(envelope, data)

        # Assert - Verify batch creation
        assert data.student_prompt_ref is not None
        expected_metadata = {
            "student_prompt_ref": data.student_prompt_ref.model_dump(mode="json"),
        }
        test_provider.mock_batch_repo.create_batch.assert_called_once_with(
            batch_id=batch_id,
            user_id=user_id,
            essay_count=expected_essay_count,
            metadata=expected_metadata,
        )

        # Verify no essay associations attempted
        test_provider.mock_batch_repo.associate_essay_with_batch.assert_not_called()

        # Verify cache invalidation
        test_provider.mock_cache_manager.invalidate_user_batches.assert_called_once_with(user_id)
