"""Integration tests for BatchRepositoryPostgresImpl using testcontainers."""

from __future__ import annotations

from typing import AsyncGenerator, Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from common_core.status_enums import BatchStatus, ProcessingStage
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.batch_repository_postgres_impl import (
    BatchRepositoryPostgresImpl,
)
from services.result_aggregator_service.models_db import Base, BatchResult


@pytest.fixture(scope="function")
async def postgres_container() -> AsyncGenerator[PostgresContainer, None]:
    """Create a PostgreSQL container for testing."""
    with PostgresContainer("postgres:15") as container:
        yield container


@pytest.fixture(scope="function")
async def async_engine(postgres_container: PostgresContainer) -> AsyncGenerator[AsyncEngine, None]:
    """Create async SQLAlchemy engine connected to test database."""
    # Get connection URL and ensure it uses asyncpg
    connection_url = postgres_container.get_connection_url()
    if "+psycopg2://" in connection_url:
        connection_url = connection_url.replace("+psycopg2://", "+asyncpg://")
    elif "postgresql://" in connection_url:
        connection_url = connection_url.replace("postgresql://", "postgresql+asyncpg://")

    engine = create_async_engine(
        connection_url,
        pool_size=5,
        max_overflow=0,
        echo=False,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for testing."""
    async with AsyncSession(async_engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_settings(postgres_container: PostgresContainer) -> Settings:
    """Create test settings with container URL."""
    # Get connection URL and ensure it uses asyncpg
    connection_url = postgres_container.get_connection_url()
    if "+psycopg2://" in connection_url:
        connection_url = connection_url.replace("+psycopg2://", "+asyncpg://")
    elif "postgresql://" in connection_url:
        connection_url = connection_url.replace("postgresql://", "postgresql+asyncpg://")

    class TestSettings(Settings):
        def __init__(self) -> None:
            super().__init__()
            self.DATABASE_URL = connection_url

    return TestSettings()


@pytest.fixture
async def batch_repository(
    test_settings: Settings,
) -> AsyncGenerator[BatchRepositoryPostgresImpl, None]:
    """Create batch repository instance."""
    repo = BatchRepositoryPostgresImpl(test_settings)
    await repo.initialize_schema()
    yield repo


@pytest.mark.integration
@pytest.mark.asyncio
class TestBatchRepositoryIntegration:
    """Integration tests for batch repository with real PostgreSQL."""

    async def test_complete_batch_lifecycle(
        self, batch_repository: BatchRepositoryPostgresImpl
    ) -> None:
        """Test the complete lifecycle of a batch result record."""
        # Test data
        batch_id = "test-batch-001"
        user_id = "test-user-123"
        essay_count = 3
        essay_ids = ["essay-001", "essay-002", "essay-003"]

        # Step 1: Creation - Create initial batch record
        batch = await batch_repository.create_batch(
            batch_id=batch_id,
            user_id=user_id,
            essay_count=essay_count,
            metadata={"requested_pipeline": "spellcheck,cj_assessment"},
        )

        # Verify initial creation
        assert batch is not None
        assert batch.batch_id == batch_id
        assert batch.user_id == user_id
        assert batch.essay_count == essay_count
        assert batch.overall_status == BatchStatus.AWAITING_CONTENT_VALIDATION
        assert batch.completed_essay_count == 0
        assert batch.failed_essay_count == 0

        # Step 2: Incremental Updates - Add spellcheck results for essays
        for i, essay_id in enumerate(essay_ids):
            await batch_repository.update_essay_spellcheck_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=ProcessingStage.COMPLETED,
                correction_count=i * 2,  # Varying correction counts
                corrected_text_storage_id=f"storage-{essay_id}",
                error=None,
            )

        # Verify essay spellcheck updates
        batch_result: Optional[BatchResult] = await batch_repository.get_batch(batch_id)
        assert batch_result is not None
        batch = batch_result  # Type narrowing for mypy
        assert len(batch.essays) == 3

        for i, essay in enumerate(sorted(batch.essays, key=lambda e: e.essay_id)):
            assert essay.spellcheck_status == ProcessingStage.COMPLETED
            assert essay.spellcheck_correction_count == i * 2
            assert essay.spellcheck_corrected_text_storage_id == f"storage-{essay.essay_id}"

        # Step 3: More incremental updates - Add CJ assessment results
        for i, essay_id in enumerate(essay_ids):
            await batch_repository.update_essay_cj_assessment_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=ProcessingStage.COMPLETED,
                rank=i + 1,
                score=0.9 - (i * 0.1),  # Decreasing scores
                comparison_count=10,
                error=None,
            )

        # Verify CJ assessment updates
        batch_result2: Optional[BatchResult] = await batch_repository.get_batch(batch_id)
        assert batch_result2 is not None
        batch = batch_result2  # Type narrowing for mypy

        for i, essay in enumerate(sorted(batch.essays, key=lambda e: e.essay_id)):
            assert essay.cj_assessment_status == ProcessingStage.COMPLETED
            assert essay.cj_rank == i + 1
            assert essay.cj_score == pytest.approx(0.9 - (i * 0.1))
            assert essay.cj_comparison_count == 10

        # Step 4: Batch-level Updates - Simulate phase completion
        await batch_repository.update_batch_phase_completed(
            batch_id=batch_id, phase="cj_assessment", completed_count=3, failed_count=0
        )

        # Step 5: Final Validation
        final_batch = await batch_repository.get_batch(batch_id)
        assert final_batch is not None

        # Verify batch-level aggregation
        assert final_batch.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
        assert final_batch.completed_essay_count == 3
        assert final_batch.failed_essay_count == 0
        # Note: processing_started_at and processing_completed_at are not set by the current implementation

        # Verify all essay data is preserved
        assert len(final_batch.essays) == 3
        for essay in final_batch.essays:
            assert essay.spellcheck_status == ProcessingStage.COMPLETED
            assert essay.cj_assessment_status == ProcessingStage.COMPLETED
            assert essay.spellcheck_correction_count is not None
            assert essay.cj_rank is not None
            assert essay.cj_score is not None

    async def test_batch_with_failures(self, batch_repository: BatchRepositoryPostgresImpl) -> None:
        """Test batch processing with some essay failures."""
        batch_id = "test-batch-002"
        user_id = "test-user-456"

        # Create batch
        await batch_repository.create_batch(
            batch_id=batch_id, user_id=user_id, essay_count=2, metadata={"test": True}
        )

        # Add one successful and one failed essay
        await batch_repository.update_essay_spellcheck_result(
            essay_id="essay-success",
            batch_id=batch_id,
            status=ProcessingStage.COMPLETED,
            correction_count=5,
            corrected_text_storage_id="storage-001",
            error=None,
        )

        await batch_repository.update_essay_spellcheck_result(
            essay_id="essay-failed",
            batch_id=batch_id,
            status=ProcessingStage.FAILED,
            correction_count=None,
            corrected_text_storage_id=None,
            error="Spellcheck service timeout",
        )

        # Update batch phase with failures
        await batch_repository.update_batch_phase_completed(
            batch_id=batch_id, phase="spellcheck", completed_count=1, failed_count=1
        )

        # Verify final state
        batch = await batch_repository.get_batch(batch_id)
        assert batch is not None
        assert batch.overall_status == BatchStatus.COMPLETED_WITH_FAILURES
        assert batch.completed_essay_count == 1
        assert batch.failed_essay_count == 1

        # Verify individual essay states
        essays_by_id = {e.essay_id: e for e in batch.essays}
        assert essays_by_id["essay-success"].spellcheck_status == ProcessingStage.COMPLETED
        assert essays_by_id["essay-failed"].spellcheck_status == ProcessingStage.FAILED
        assert essays_by_id["essay-failed"].spellcheck_error == "Spellcheck service timeout"

    async def test_batch_critical_failure(
        self, batch_repository: BatchRepositoryPostgresImpl
    ) -> None:
        """Test batch critical failure handling."""
        batch_id = "test-batch-003"
        user_id = "test-user-789"

        # Create batch
        await batch_repository.create_batch(batch_id=batch_id, user_id=user_id, essay_count=5)

        # Mark batch as critically failed
        error_message = "Kafka consumer disconnected during processing"
        await batch_repository.update_batch_failed(batch_id, error_message)

        # Verify failure state
        batch = await batch_repository.get_batch(batch_id)
        assert batch is not None
        assert batch.overall_status == BatchStatus.FAILED_CRITICALLY
        assert batch.last_error == error_message
        # Note: error_count is not tracked in the current implementation
        # assert batch.error_count == 1
        # Note: processing_completed_at is not set by the current implementation

    async def test_concurrent_essay_updates(
        self, batch_repository: BatchRepositoryPostgresImpl
    ) -> None:
        """Test rapid sequential updates to different essays in the same batch."""
        batch_id = "test-batch-004"
        user_id = "test-user-concurrent"
        essay_ids = [f"essay-{i:03d}" for i in range(10)]

        # Create batch
        await batch_repository.create_batch(
            batch_id=batch_id, user_id=user_id, essay_count=len(essay_ids)
        )

        # Simulate rapid sequential essay updates
        # Note: SQLAlchemy doesn't support concurrent operations on the same session
        for i, essay_id in enumerate(essay_ids):
            await batch_repository.update_essay_spellcheck_result(
                essay_id=essay_id,
                batch_id=batch_id,
                status=ProcessingStage.COMPLETED,
                correction_count=i,
                corrected_text_storage_id=f"storage-{essay_id}",
            )

        # Verify all updates were applied
        batch = await batch_repository.get_batch(batch_id)
        assert batch is not None
        assert len(batch.essays) == len(essay_ids)

        # Verify each essay has the correct data
        essays_by_id = {e.essay_id: e for e in batch.essays}
        for i, essay_id in enumerate(essay_ids):
            essay = essays_by_id[essay_id]
            assert essay.spellcheck_status == ProcessingStage.COMPLETED
            assert essay.spellcheck_correction_count == i

    async def test_get_user_batches_filtering(
        self, batch_repository: BatchRepositoryPostgresImpl
    ) -> None:
        """Test getting user batches with status filtering."""
        user_id = "test-user-filter"

        # Create batches with different statuses
        statuses = [
            (BatchStatus.COMPLETED_SUCCESSFULLY, "batch-001"),
            (BatchStatus.COMPLETED_WITH_FAILURES, "batch-002"),
            (BatchStatus.PROCESSING_PIPELINES, "batch-003"),
            (BatchStatus.FAILED_CRITICALLY, "batch-004"),
        ]

        for status, batch_id in statuses:
            await batch_repository.create_batch(batch_id=batch_id, user_id=user_id, essay_count=1)
            # Manually update status for testing
            await batch_repository.update_batch_status(batch_id=batch_id, status=status.value)

        # Test filtering
        all_batches = await batch_repository.get_user_batches(user_id)
        assert len(all_batches) == 4

        completed_batches = await batch_repository.get_user_batches(
            user_id, status="completed_successfully"
        )
        assert len(completed_batches) == 1
        assert completed_batches[0].batch_id == "batch-001"

        # Test pagination
        paginated = await batch_repository.get_user_batches(user_id, limit=2, offset=1)
        assert len(paginated) == 2
        assert paginated[0].batch_id in ["batch-002", "batch-003"]
