"""Integration tests for PostgreSQL Batch Repository using test containers.

These tests use real PostgreSQL databases to verify the production repository
implementation works correctly with actual database operations.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from testcontainers.postgres import PostgresContainer

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_repository_postgres_impl import (
    PostgreSQLBatchRepositoryImpl,
)


class TestPostgreSQLBatchRepositoryIntegration:
    """Integration tests with real PostgreSQL database."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> PostgresContainer:
        """Start PostgreSQL test container for integration tests."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture
    def test_settings(self, postgres_container: PostgresContainer) -> MagicMock:
        """Create test settings pointing to the test container database."""
        settings = MagicMock()
        # Ensure the connection URL uses asyncpg driver for async operations
        connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in connection_url:
            connection_url = connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in connection_url:
            connection_url = connection_url.replace("postgresql://", "postgresql+asyncpg://")

        settings.database_url = connection_url
        settings.DB_POOL_SIZE = 2
        settings.DB_MAX_OVERFLOW = 1
        return settings

    @pytest.fixture
    async def postgres_repository(self, test_settings: MagicMock) -> PostgreSQLBatchRepositoryImpl:
        """Create PostgreSQL repository with test database."""
        repository = PostgreSQLBatchRepositoryImpl(test_settings)
        # Initialize the database schema
        await repository.initialize_db_schema()
        return repository

    @pytest.fixture
    def sample_batch_registration(self) -> BatchRegistrationRequestV1:
        """Sample batch registration for testing."""
        return BatchRegistrationRequestV1(
            course_code="CS101",
            class_designation="Fall 2025",
            teacher_name="Dr. Smith",
            essay_instructions="Write a 500-word essay about software engineering.",
            expected_essay_count=25,
            enable_cj_assessment=True,
        )

    @pytest.mark.asyncio
    async def test_database_schema_initialization(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test that database schema is created correctly."""
        # The schema should be initialized in the fixture
        # Let's verify we can perform basic operations
        batch_data = {
            "id": "test-schema-batch",
            "status": "awaiting_content_validation",
            "name": "Schema Test Batch",
        }

        result = await postgres_repository.create_batch(batch_data)
        assert result["id"] == "test-schema-batch"
        assert "created_at" in result

    @pytest.mark.asyncio
    async def test_create_and_retrieve_batch(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test creating and retrieving a batch."""
        # Arrange
        batch_data = {
            "id": "test-batch-001",
            "correlation_id": "corr-123",
            "name": "Integration Test Batch",
            "description": "Test batch for integration testing",
            "status": "awaiting_content_validation",
            "requested_pipelines": ["spellcheck", "ai_feedback"],
            "total_essays": 10,
        }

        # Act - Create batch
        create_result = await postgres_repository.create_batch(batch_data)

        # Act - Retrieve batch
        retrieved_batch = await postgres_repository.get_batch_by_id("test-batch-001")

        # Assert
        assert create_result["id"] == "test-batch-001"
        assert retrieved_batch is not None
        assert retrieved_batch["id"] == "test-batch-001"
        assert retrieved_batch["name"] == "Integration Test Batch"
        assert retrieved_batch["status"] == "awaiting_content_validation"
        assert retrieved_batch["total_essays"] == 10
        assert retrieved_batch["correlation_id"] == "corr-123"

    @pytest.mark.asyncio
    async def test_batch_context_storage_and_retrieval(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
        sample_batch_registration: BatchRegistrationRequestV1,
    ) -> None:
        """Test storing and retrieving batch context."""
        # Arrange
        batch_id = "test-context-batch"

        # Act - Store context
        store_success = await postgres_repository.store_batch_context(
            batch_id,
            sample_batch_registration,
        )

        # Act - Retrieve context
        retrieved_context = await postgres_repository.get_batch_context(batch_id)

        # Assert
        assert store_success is True
        assert retrieved_context is not None
        assert retrieved_context.course_code == "CS101"
        assert retrieved_context.class_designation == "Fall 2025"
        assert retrieved_context.expected_essay_count == 25
        assert retrieved_context.enable_cj_assessment is True

    @pytest.mark.asyncio
    async def test_pipeline_state_persistence(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test saving and retrieving pipeline state."""
        # Arrange
        batch_id = "test-pipeline-batch"
        pipeline_state = {
            "spellcheck_status": "pending",
            "ai_feedback_status": "not_started",
            "processing_metadata": {"started_at": "2025-01-30T10:00:00Z"},
        }

        # Create batch first
        await postgres_repository.create_batch(
            {
                "id": batch_id,
                "status": "ready_for_pipeline_execution",
            },
        )

        # Act - Save pipeline state
        save_success = await postgres_repository.save_processing_pipeline_state(
            batch_id,
            pipeline_state,
        )

        # Act - Retrieve pipeline state
        retrieved_state = await postgres_repository.get_processing_pipeline_state(batch_id)

        # Assert
        assert save_success is True
        assert retrieved_state is not None
        assert retrieved_state["spellcheck_status"] == "pending"
        assert retrieved_state["ai_feedback_status"] == "not_started"
        assert retrieved_state["processing_metadata"]["started_at"] == "2025-01-30T10:00:00Z"

    @pytest.mark.asyncio
    async def test_atomic_phase_status_update(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test atomic phase status updates prevent race conditions."""
        # Arrange
        batch_id = "test-atomic-batch"
        phase_name = "spellcheck"

        # Create batch and set initial pipeline state
        await postgres_repository.create_batch(
            {
                "id": batch_id,
                "status": "processing_pipelines",
            },
        )

        await postgres_repository.save_processing_pipeline_state(
            batch_id,
            {f"{phase_name}_status": "pending"},
        )

        # Act - First atomic update (should succeed)
        success1 = await postgres_repository.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=phase_name,
            expected_status="pending",
            new_status="in_progress",
            completion_timestamp="2025-01-30T10:30:00Z",
        )

        # Act - Second atomic update with wrong expected status (should fail)
        success2 = await postgres_repository.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=phase_name,
            expected_status="pending",  # Wrong - it's now "in_progress"
            new_status="completed",
        )

        # Act - Third atomic update with correct expected status (should succeed)
        success3 = await postgres_repository.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=phase_name,
            expected_status="in_progress",  # Correct current status
            new_status="completed",
            completion_timestamp="2025-01-30T11:00:00Z",
        )

        # Assert
        assert success1 is True  # First update succeeded
        assert success2 is False  # Second update failed (race condition prevented)
        assert success3 is True  # Third update succeeded

        # Verify final state
        final_state = await postgres_repository.get_processing_pipeline_state(batch_id)
        assert final_state is not None
        assert final_state[f"{phase_name}_status"] == "completed"
        assert final_state[f"{phase_name}_completed_at"] == "2025-01-30T11:00:00Z"

    @pytest.mark.asyncio
    async def test_concurrent_atomic_operations(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test that concurrent atomic operations are handled correctly."""
        # Arrange
        batch_id = "test-concurrent-batch"
        phase_name = "spellcheck"

        # Create batch and set initial state
        await postgres_repository.create_batch(
            {
                "id": batch_id,
                "status": "processing_pipelines",
            },
        )

        await postgres_repository.save_processing_pipeline_state(
            batch_id,
            {f"{phase_name}_status": "pending"},
        )

        # Act - Run concurrent atomic updates
        async def attempt_update(expected: str, new: str) -> bool:
            return await postgres_repository.update_phase_status_atomically(
                batch_id=batch_id,
                phase_name=phase_name,
                expected_status=expected,
                new_status=new,
            )

        # Run two concurrent updates trying to move from "pending" to different states
        task1 = asyncio.create_task(attempt_update("pending", "in_progress"))
        task2 = asyncio.create_task(attempt_update("pending", "failed"))

        results = await asyncio.gather(task1, task2, return_exceptions=True)

        # Assert - Exactly one should succeed, one should fail
        successes = sum(1 for result in results if result is True)
        failures = sum(1 for result in results if result is False)

        assert successes == 1, f"Expected exactly 1 success, got {successes}"
        assert failures == 1, f"Expected exactly 1 failure, got {failures}"

        # Verify the final state is one of the attempted states
        final_state = await postgres_repository.get_processing_pipeline_state(batch_id)
        assert final_state is not None
        final_status = final_state[f"{phase_name}_status"]
        assert final_status in ["in_progress", "failed"]

    @pytest.mark.asyncio
    async def test_batch_status_update(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test updating batch status."""
        # Arrange
        batch_id = "test-status-batch"

        # Create batch
        await postgres_repository.create_batch(
            {
                "id": batch_id,
                "status": "awaiting_content_validation",
            },
        )

        # Act - Update status
        update_success = await postgres_repository.update_batch_status(
            batch_id,
            "ready_for_pipeline_execution",
        )

        # Act - Retrieve updated batch
        updated_batch = await postgres_repository.get_batch_by_id(batch_id)

        # Assert
        assert update_success is True
        assert updated_batch is not None
        assert updated_batch["status"] == "ready_for_pipeline_execution"

    @pytest.mark.asyncio
    async def test_nonexistent_batch_operations(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test operations on nonexistent batches return appropriate results."""
        nonexistent_id = "nonexistent-batch-123"

        # Test retrieval
        batch = await postgres_repository.get_batch_by_id(nonexistent_id)
        assert batch is None

        # Test context retrieval
        context = await postgres_repository.get_batch_context(nonexistent_id)
        assert context is None

        # Test pipeline state retrieval
        state = await postgres_repository.get_processing_pipeline_state(nonexistent_id)
        assert state is None

        # Test status update
        status_update = await postgres_repository.update_batch_status(
            nonexistent_id,
            "completed_successfully",
        )
        assert status_update is False

        # Test pipeline state save (should fail)
        pipeline_save = await postgres_repository.save_processing_pipeline_state(
            nonexistent_id,
            {"test": "data"},
        )
        assert pipeline_save is False
