"""
Integration tests for PostgreSQL Essay Repository using test containers.

These tests use real PostgreSQL databases to verify the production repository
implementation works correctly with actual database operations.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.error_enums import ErrorCode
from common_core.metadata_models import EntityReference
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import HuleEduError
from testcontainers.postgres import PostgresContainer

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)


class TestPostgreSQLEssayRepositoryIntegration:
    """Integration tests with real PostgreSQL database."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, Any, None]:
        """Start PostgreSQL test container for integration tests."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    class PostgreSQLTestSettings(Settings):
        """Test settings that override DATABASE_URL property."""

        def __init__(self, database_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)
            self.DATABASE_POOL_SIZE = 2
            self.DATABASE_MAX_OVERFLOW = 1
            self.DATABASE_POOL_PRE_PING = True
            self.DATABASE_POOL_RECYCLE = 3600

        @property
        def DATABASE_URL(self) -> str:
            """Override to return test database URL."""
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def test_settings(self, postgres_container: PostgresContainer) -> Settings:
        """Create test settings pointing to the test container database."""
        # Get connection URL and ensure it uses asyncpg driver
        connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in connection_url:
            connection_url = connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in connection_url:
            connection_url = connection_url.replace("postgresql://", "postgresql+asyncpg://")

        # Create test settings instance with test database configuration
        return self.PostgreSQLTestSettings(database_url=connection_url)

    @pytest.fixture
    def sample_entity_reference(self) -> EntityReference:
        """Sample entity reference for testing."""
        unique_id = str(uuid4())[:8]  # Short unique suffix
        return EntityReference(
            entity_id=f"test-essay-{unique_id}",
            entity_type="essay",
            parent_id=f"test-batch-{unique_id}",
        )

    @pytest.fixture
    async def postgres_repository(self, test_settings: Settings) -> PostgreSQLEssayRepository:
        """Create PostgreSQL repository with test database."""
        repository = PostgreSQLEssayRepository(test_settings)
        # Initialize the database schema
        await repository.initialize_db_schema()
        # Run migrations to apply constraints
        await repository.run_migrations()

        # Clean up any existing data to ensure test isolation
        async with repository.session() as session:
            from sqlalchemy import delete

            from services.essay_lifecycle_service.models_db import BatchEssayTracker, EssayStateDB

            await session.execute(delete(EssayStateDB))
            await session.execute(delete(BatchEssayTracker))
            await session.commit()

        return repository

    async def create_batch_tracker(
        self, repository: PostgreSQLEssayRepository, batch_id: str, essay_ids: list[str] | None = None
    ) -> None:
        """Helper method to create batch tracker record for foreign key constraint compliance."""
        if essay_ids is None:
            essay_ids = []

        async with repository.session() as session:
            from services.essay_lifecycle_service.models_db import BatchEssayTracker

            batch_tracker = BatchEssayTracker(
                batch_id=batch_id,
                expected_essay_ids=essay_ids,
                available_slots=essay_ids.copy(),
                expected_count=len(essay_ids),
                course_code=CourseCode.ENG5.value,
                essay_instructions="Test essay instructions",
                user_id="test-user",
                correlation_id=str(uuid4()),
                timeout_seconds=300,
                total_slots=len(essay_ids),
                assigned_slots=0,
                is_ready=False,
            )

            session.add(batch_tracker)
            await session.commit()

    @pytest.mark.asyncio
    async def test_database_schema_initialization(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test that database schema is created correctly."""
        # The schema should be initialized in the fixture
        # Let's verify we can perform basic operations
        batch_id = "schema-test-batch"
        essay_id = "schema-test-essay"

        # Create batch tracker first to satisfy foreign key constraint
        await self.create_batch_tracker(postgres_repository, batch_id, [essay_id])

        essay_ref = EntityReference(
            entity_id=essay_id, entity_type="essay", parent_id=batch_id
        )

        created_essay = await postgres_repository.create_essay_record(essay_ref)
        assert created_essay.essay_id == essay_id
        assert created_essay.batch_id == batch_id
        assert created_essay.current_status == EssayStatus.UPLOADED

    @pytest.mark.asyncio
    async def test_create_and_retrieve_essay(
        self,
        postgres_repository: PostgreSQLEssayRepository,
        sample_entity_reference: EntityReference,
    ) -> None:
        """Test creating and retrieving an essay."""
        # Create batch tracker first to satisfy foreign key constraint
        assert sample_entity_reference.parent_id is not None
        await self.create_batch_tracker(
            postgres_repository,
            sample_entity_reference.parent_id,
            [sample_entity_reference.entity_id]
        )

        # Act - Create essay
        created_essay = await postgres_repository.create_essay_record(sample_entity_reference)

        # Act - Retrieve essay
        retrieved_essay = await postgres_repository.get_essay_state(
            sample_entity_reference.entity_id
        )

        # Assert
        assert created_essay.essay_id == sample_entity_reference.entity_id
        assert created_essay.batch_id == sample_entity_reference.parent_id
        assert created_essay.current_status == EssayStatus.UPLOADED

        assert retrieved_essay is not None
        assert retrieved_essay.essay_id == sample_entity_reference.entity_id
        assert retrieved_essay.batch_id == sample_entity_reference.parent_id
        assert retrieved_essay.current_status == EssayStatus.UPLOADED
        assert isinstance(retrieved_essay.created_at, datetime)
        assert isinstance(retrieved_essay.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_update_essay_state(
        self,
        postgres_repository: PostgreSQLEssayRepository,
        sample_entity_reference: EntityReference,
    ) -> None:
        """Test updating essay state and metadata."""
        # Create batch tracker first to satisfy foreign key constraint
        assert sample_entity_reference.parent_id is not None
        await self.create_batch_tracker(
            postgres_repository,
            sample_entity_reference.parent_id,
            [sample_entity_reference.entity_id]
        )

        # Arrange - Create essay
        await postgres_repository.create_essay_record(sample_entity_reference)

        # Act - Update essay state
        new_metadata = {"updated_by": "test", "processing_step": "spellcheck"}
        await postgres_repository.update_essay_state(
            essay_id=sample_entity_reference.entity_id,
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata=new_metadata,
        )

        # Act - Retrieve updated essay
        updated_essay = await postgres_repository.get_essay_state(sample_entity_reference.entity_id)

        # Assert
        assert updated_essay is not None
        assert updated_essay.current_status == EssayStatus.AWAITING_SPELLCHECK
        assert updated_essay.processing_metadata["updated_by"] == "test"
        assert updated_essay.processing_metadata["processing_step"] == "spellcheck"
        assert EssayStatus.AWAITING_SPELLCHECK.value in updated_essay.timeline

    @pytest.mark.asyncio
    async def test_slot_assignment_operations(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test slot assignment create/update operations."""
        # Arrange
        essay_id = "slot-test-essay"
        batch_id = "slot-test-batch"
        text_storage_id = "storage-123"

        # Create batch tracker first to satisfy foreign key constraint
        await self.create_batch_tracker(postgres_repository, batch_id, [essay_id])

        # Act - Create essay for slot assignment
        created_essay = await postgres_repository.create_or_update_essay_state_for_slot_assignment(
            internal_essay_id=essay_id,
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            original_file_name="test_essay.txt",
            file_size=1024,
            content_hash="abc123",
            initial_status=EssayStatus.READY_FOR_PROCESSING,
        )

        # Assert essay creation
        assert created_essay.essay_id == essay_id
        assert created_essay.batch_id == batch_id
        assert created_essay.current_status == EssayStatus.READY_FOR_PROCESSING
        assert created_essay.storage_references[ContentType.ORIGINAL_ESSAY] == text_storage_id
        assert created_essay.processing_metadata["original_file_name"] == "test_essay.txt"
        assert created_essay.processing_metadata["file_size"] == 1024

        # Act - Test idempotency check
        found_essay = await postgres_repository.get_essay_by_text_storage_id_and_batch_id(
            batch_id, text_storage_id
        )

        # Assert idempotency
        assert found_essay is not None
        assert found_essay.essay_id == essay_id

    @pytest.mark.asyncio
    async def test_batch_operations(self, postgres_repository: PostgreSQLEssayRepository) -> None:
        """Test batch-level operations."""
        # Arrange - Create multiple essays in same batch
        batch_id = "batch-ops-test"
        essay_ids = [f"essay-{i}" for i in range(3)]

        # Create batch tracker first to satisfy foreign key constraint
        await self.create_batch_tracker(postgres_repository, batch_id, essay_ids)

        for i in range(3):
            essay_ref = EntityReference(
                entity_id=f"essay-{i}", entity_type="essay", parent_id=batch_id
            )
            await postgres_repository.create_essay_record(essay_ref)

            # Update some to different statuses
            if i == 0:
                await postgres_repository.update_essay_state(
                    essay_id=f"essay-{i}",
                    new_status=EssayStatus.AWAITING_SPELLCHECK,
                    metadata={},
                )
            elif i == 1:
                await postgres_repository.update_essay_state(
                    essay_id=f"essay-{i}",
                    new_status=EssayStatus.SPELLCHECKED_SUCCESS,
                    metadata={},
                )

        # Act - List essays by batch
        batch_essays = await postgres_repository.list_essays_by_batch(batch_id)

        # Act - Get batch status summary
        status_summary = await postgres_repository.get_batch_status_summary(batch_id)

        # Assert
        assert len(batch_essays) == 3
        assert all(essay.batch_id == batch_id for essay in batch_essays)

        assert status_summary[EssayStatus.UPLOADED] == 1
        assert status_summary[EssayStatus.AWAITING_SPELLCHECK] == 1
        assert status_summary[EssayStatus.SPELLCHECKED_SUCCESS] == 1

    @pytest.mark.asyncio
    async def test_phase_based_essay_listing(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test listing essays by batch and processing phase."""
        # Arrange - Create essays in different phases
        batch_id = "phase-test-batch"

        # Create essays and set them to different statuses
        essay_statuses = [
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKED_SUCCESS,
            EssayStatus.AWAITING_CJ_ASSESSMENT,
            EssayStatus.CJ_ASSESSMENT_SUCCESS,
            EssayStatus.UPLOADED,  # Not in any phase
        ]

        essay_ids = [f"phase-essay-{i}" for i in range(len(essay_statuses))]

        # Create batch tracker first to satisfy foreign key constraint
        await self.create_batch_tracker(postgres_repository, batch_id, essay_ids)

        for i, status in enumerate(essay_statuses):
            essay_ref = EntityReference(
                entity_id=f"phase-essay-{i}", entity_type="essay", parent_id=batch_id
            )
            await postgres_repository.create_essay_record(essay_ref)
            await postgres_repository.update_essay_state(
                essay_id=f"phase-essay-{i}", new_status=status, metadata={}
            )

        # Act - List essays by spellcheck phase
        spellcheck_essays = await postgres_repository.list_essays_by_batch_and_phase(
            batch_id, "spellcheck"
        )

        # Act - List essays by cj_assessment phase
        cj_essays = await postgres_repository.list_essays_by_batch_and_phase(
            batch_id, "cj_assessment"
        )

        # Act - List essays by non-existent phase
        unknown_phase_essays = await postgres_repository.list_essays_by_batch_and_phase(
            batch_id, "unknown_phase"
        )

        # Assert
        assert len(spellcheck_essays) == 2  # AWAITING_SPELLCHECK + SPELLCHECKED_SUCCESS
        assert len(cj_essays) == 2  # AWAITING_CJ_ASSESSMENT + CJ_ASSESSMENT_SUCCESS
        assert len(unknown_phase_essays) == 0

        spellcheck_statuses = {essay.current_status for essay in spellcheck_essays}
        assert EssayStatus.AWAITING_SPELLCHECK in spellcheck_statuses
        assert EssayStatus.SPELLCHECKED_SUCCESS in spellcheck_statuses

    @pytest.mark.asyncio
    async def test_nonexistent_essay_operations(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test operations on nonexistent essays return appropriate results."""
        nonexistent_id = "nonexistent-essay-123"

        # Test retrieval
        essay = await postgres_repository.get_essay_state(nonexistent_id)
        assert essay is None

        # Test update (should raise HuleEduError with RESOURCE_NOT_FOUND)
        with pytest.raises(HuleEduError) as exc_info:
            await postgres_repository.update_essay_state(
                essay_id=nonexistent_id,
                new_status=EssayStatus.AWAITING_SPELLCHECK,
                metadata={},
            )

        # Validate error structure
        error = exc_info.value
        assert error.error_detail.error_code == ErrorCode.RESOURCE_NOT_FOUND
        assert "nonexistent-essay-123" in error.error_detail.message
        assert error.error_detail.service == "essay_lifecycle_service"
        assert error.error_detail.operation == "update_essay_state"

        # Test idempotency check with nonexistent batch/storage
        found_essay = await postgres_repository.get_essay_by_text_storage_id_and_batch_id(
            "nonexistent-batch", "nonexistent-storage"
        )
        assert found_essay is None

    @pytest.mark.asyncio
    async def test_timeline_and_metadata_persistence(
        self,
        postgres_repository: PostgreSQLEssayRepository,
        sample_entity_reference: EntityReference,
    ) -> None:
        """Test that timeline and metadata are properly persisted and retrieved."""
        # Create batch tracker first to satisfy foreign key constraint
        assert sample_entity_reference.parent_id is not None
        await self.create_batch_tracker(
            postgres_repository,
            sample_entity_reference.parent_id,
            [sample_entity_reference.entity_id]
        )

        # Arrange - Create essay
        await postgres_repository.create_essay_record(sample_entity_reference)

        # Act - Update multiple times to build timeline
        metadata1 = {"step": "spellcheck", "data": {"corrections": 5}}
        await postgres_repository.update_essay_state(
            essay_id=sample_entity_reference.entity_id,
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata=metadata1,
        )

        metadata2 = {"step": "completed", "data": {"final_score": 85}}
        await postgres_repository.update_essay_state(
            essay_id=sample_entity_reference.entity_id,
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata=metadata2,
        )

        # Act - Retrieve final state
        final_essay = await postgres_repository.get_essay_state(sample_entity_reference.entity_id)

        # Assert
        assert final_essay is not None
        assert final_essay.current_status == EssayStatus.SPELLCHECKED_SUCCESS

        # Check timeline has both status transitions
        assert EssayStatus.UPLOADED.value in final_essay.timeline
        assert EssayStatus.AWAITING_SPELLCHECK.value in final_essay.timeline
        assert EssayStatus.SPELLCHECKED_SUCCESS.value in final_essay.timeline

        # Check metadata is preserved
        assert final_essay.processing_metadata["step"] == "completed"
        assert final_essay.processing_metadata["data"]["final_score"] == 85

    @pytest.mark.asyncio
    async def test_atomic_batch_essay_creation_success(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test successful atomic batch creation of multiple essays."""
        # Arrange - Create batch of entity references
        batch_id = "atomic-test-batch"
        essay_ids = [f"atomic-essay-{i:03d}" for i in range(1, 4)]

        # Create batch tracker first to satisfy foreign key constraint
        await self.create_batch_tracker(postgres_repository, batch_id, essay_ids)

        essay_refs = [
            EntityReference(
                entity_id=f"atomic-essay-{i:03d}", entity_type="essay", parent_id=batch_id
            )
            for i in range(1, 4)  # 3 essays
        ]

        # Act - Create all essays in atomic batch operation
        created_essays = await postgres_repository.create_essay_records_batch(essay_refs)

        # Assert - All essays created successfully
        assert len(created_essays) == 3

        # Verify each essay has correct data
        for i, essay in enumerate(created_essays, 1):
            assert essay.essay_id == f"atomic-essay-{i:03d}"
            assert essay.batch_id == batch_id
            assert essay.current_status == EssayStatus.UPLOADED
            assert EssayStatus.UPLOADED.value in essay.timeline
            assert isinstance(essay.created_at, datetime)
            assert isinstance(essay.updated_at, datetime)

        # Verify all essays can be retrieved from database
        for i in range(1, 4):
            essay_id = f"atomic-essay-{i:03d}"
            retrieved_essay = await postgres_repository.get_essay_state(essay_id)
            assert retrieved_essay is not None
            assert retrieved_essay.essay_id == essay_id
            assert retrieved_essay.batch_id == batch_id

        # Verify batch listing returns all essays
        batch_essays = await postgres_repository.list_essays_by_batch(batch_id)
        assert len(batch_essays) == 3
        batch_essay_ids = {essay.essay_id for essay in batch_essays}
        expected_ids = {f"atomic-essay-{i:03d}" for i in range(1, 4)}
        assert batch_essay_ids == expected_ids

    @pytest.mark.asyncio
    async def test_atomic_batch_essay_creation_empty_list(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test atomic batch creation with empty list returns empty result."""
        # Act - Create batch with empty list
        created_essays = await postgres_repository.create_essay_records_batch([])

        # Assert - Empty list returned
        assert created_essays == []

    @pytest.mark.asyncio
    async def test_atomic_batch_essay_creation_preserves_atomicity(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test that batch creation is truly atomic - all or nothing."""
        # Arrange - Create batch tracker and one essay to test for duplicate key constraint
        batch_id = "atomicity-test-batch"
        essay_ids = ["duplicate-essay-001", "new-essay-002", "new-essay-003"]

        # Create batch tracker first to satisfy foreign key constraint
        await self.create_batch_tracker(postgres_repository, batch_id, essay_ids)

        existing_ref = EntityReference(
            entity_id="duplicate-essay-001", entity_type="essay", parent_id=batch_id
        )
        await postgres_repository.create_essay_record(existing_ref)

        # Arrange - Create batch that includes the duplicate
        batch_refs = [
            EntityReference(
                entity_id="duplicate-essay-001",  # This will cause constraint violation
                entity_type="essay",
                parent_id=batch_id,
            ),
            EntityReference(
                entity_id="new-essay-002", entity_type="essay", parent_id=batch_id
            ),
            EntityReference(
                entity_id="new-essay-003", entity_type="essay", parent_id=batch_id
            ),
        ]

        # Act & Assert - Batch creation should fail completely
        with pytest.raises(HuleEduError):
            await postgres_repository.create_essay_records_batch(batch_refs)

        # Assert - No new essays should exist (atomic rollback)
        # The existing essay should still be there
        existing_essay = await postgres_repository.get_essay_state("duplicate-essay-001")
        assert existing_essay is not None

        # But the new essays should NOT exist (transaction rolled back)
        new_essay_2 = await postgres_repository.get_essay_state("new-essay-002")
        new_essay_3 = await postgres_repository.get_essay_state("new-essay-003")
        assert new_essay_2 is None
        assert new_essay_3 is None

        # Verify batch count is still 1 (only the original essay)
        batch_essays = await postgres_repository.list_essays_by_batch(batch_id)
        assert len(batch_essays) == 1
