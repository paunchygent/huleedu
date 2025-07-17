"""
Integration tests for PostgreSQL Essay Repository using test containers.

These tests use real PostgreSQL databases to verify the production repository
implementation works correctly with actual database operations.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Any

import pytest
from common_core.domain_enums import ContentType
from common_core.metadata_models import EntityReference
from common_core.status_enums import EssayStatus
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
            object.__setattr__(self, '_database_url', database_url)
            self.DATABASE_POOL_SIZE = 2
            self.DATABASE_MAX_OVERFLOW = 1
            self.DATABASE_POOL_PRE_PING = True
            self.DATABASE_POOL_RECYCLE = 3600
        
        @property
        def DATABASE_URL(self) -> str:
            """Override to return test database URL."""
            return object.__getattribute__(self, '_database_url')

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
        import uuid

        unique_id = str(uuid.uuid4())[:8]  # Short unique suffix
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

        # Clean up any existing data to ensure test isolation
        async with repository.session() as session:
            from sqlalchemy import delete

            from services.essay_lifecycle_service.models_db import EssayStateDB

            await session.execute(delete(EssayStateDB))
            await session.commit()

        return repository

    @pytest.mark.asyncio
    async def test_database_schema_initialization(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> None:
        """Test that database schema is created correctly."""
        # The schema should be initialized in the fixture
        # Let's verify we can perform basic operations
        essay_ref = EntityReference(
            entity_id="schema-test-essay", entity_type="essay", parent_id="schema-test-batch"
        )

        created_essay = await postgres_repository.create_essay_record(essay_ref)
        assert created_essay.essay_id == "schema-test-essay"
        assert created_essay.batch_id == "schema-test-batch"
        assert created_essay.current_status == EssayStatus.UPLOADED

    @pytest.mark.asyncio
    async def test_create_and_retrieve_essay(
        self,
        postgres_repository: PostgreSQLEssayRepository,
        sample_entity_reference: EntityReference,
    ) -> None:
        """Test creating and retrieving an essay."""
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
        # Arrange - Create essay
        await postgres_repository.create_essay_record(sample_entity_reference)

        # Act - Update essay state
        new_metadata = {"updated_by": "test", "processing_step": "spellcheck"}
        await postgres_repository.update_essay_state(
            sample_entity_reference.entity_id, EssayStatus.AWAITING_SPELLCHECK, new_metadata
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

        for i in range(3):
            essay_ref = EntityReference(
                entity_id=f"essay-{i}", entity_type="essay", parent_id=batch_id
            )
            await postgres_repository.create_essay_record(essay_ref)

            # Update some to different statuses
            if i == 0:
                await postgres_repository.update_essay_state(
                    f"essay-{i}", EssayStatus.AWAITING_SPELLCHECK, {}
                )
            elif i == 1:
                await postgres_repository.update_essay_state(
                    f"essay-{i}", EssayStatus.SPELLCHECKED_SUCCESS, {}
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

        for i, status in enumerate(essay_statuses):
            essay_ref = EntityReference(
                entity_id=f"phase-essay-{i}", entity_type="essay", parent_id=batch_id
            )
            await postgres_repository.create_essay_record(essay_ref)
            await postgres_repository.update_essay_state(f"phase-essay-{i}", status, {})

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

        # Test update (should raise error)
        with pytest.raises(ValueError, match="not found"):
            await postgres_repository.update_essay_state(
                nonexistent_id, EssayStatus.AWAITING_SPELLCHECK, {}
            )

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
        # Arrange - Create essay
        await postgres_repository.create_essay_record(sample_entity_reference)

        # Act - Update multiple times to build timeline
        metadata1 = {"step": "spellcheck", "data": {"corrections": 5}}
        await postgres_repository.update_essay_state(
            sample_entity_reference.entity_id, EssayStatus.AWAITING_SPELLCHECK, metadata1
        )

        metadata2 = {"step": "completed", "data": {"final_score": 85}}
        await postgres_repository.update_essay_state(
            sample_entity_reference.entity_id, EssayStatus.SPELLCHECKED_SUCCESS, metadata2
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
