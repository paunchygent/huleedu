"""Integration tests for PostgreSQL Batch Repository using test containers.

These tests use real PostgreSQL databases to verify the production repository
implementation works correctly with actual database operations.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from common_core.domain_enums import CourseCode
from common_core.pipeline_models import (
    PhaseName,
    PipelineExecutionStatus,
    PipelineStateDetail,
    ProcessingPipelineState,
)
from common_core.status_enums import BatchStatus
from testcontainers.postgres import PostgresContainer

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_repository_postgres_impl import (
    PostgreSQLBatchRepositoryImpl,
)
from services.batch_orchestrator_service.tests import make_prompt_ref


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

        settings.DATABASE_URL = connection_url
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
        """Sample batch registration for testing - lean registration model."""
        return BatchRegistrationRequestV1(
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-software-engineering"),
            user_id="user_123",
            expected_essay_count=25,
            enable_cj_assessment=True,
        )

    @pytest.fixture
    def sample_batch_context(self) -> BatchRegistrationRequestV1:
        """Sample batch context for testing."""
        return BatchRegistrationRequestV1(
            expected_essay_count=5,
            course_code=CourseCode.SV2,
            student_prompt_ref=make_prompt_ref("prompt-swedish-culture"),
            user_id="user_integration_test",
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
            "correlation_id": "test-corr-schema",
            "status": BatchStatus.AWAITING_CONTENT_VALIDATION.value,
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
            "status": BatchStatus.AWAITING_CONTENT_VALIDATION.value,
            "requested_pipelines": [PhaseName.SPELLCHECK.value, PhaseName.AI_FEEDBACK.value],
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
        assert retrieved_batch["status"] == BatchStatus.AWAITING_CONTENT_VALIDATION.value
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
            correlation_id="test-context-correlation",
        )

        # Act - Retrieve context
        retrieved_context = await postgres_repository.get_batch_context(batch_id)

        # Assert
        assert store_success is True
        assert retrieved_context is not None
        assert retrieved_context.course_code == CourseCode.ENG5
        assert retrieved_context.user_id == "user_123"
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
        pipeline_state = ProcessingPipelineState(
            batch_id=batch_id,
            requested_pipelines=[PhaseName.SPELLCHECK.value, PhaseName.AI_FEEDBACK.value],
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.PENDING_DEPENDENCIES),
            ai_feedback=PipelineStateDetail(status=PipelineExecutionStatus.PENDING_DEPENDENCIES),
        )

        # Create batch first
        await postgres_repository.create_batch(
            {
                "id": batch_id,
                "correlation_id": "test-corr-pipeline",
                "status": BatchStatus.READY_FOR_PIPELINE_EXECUTION.value,
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

        # Verify spellcheck phase state
        spellcheck_detail = retrieved_state.get_pipeline(PhaseName.SPELLCHECK.value)
        assert spellcheck_detail is not None
        assert spellcheck_detail.status == PipelineExecutionStatus.PENDING_DEPENDENCIES

        # Verify AI feedback phase state
        ai_feedback_detail = retrieved_state.get_pipeline(PhaseName.AI_FEEDBACK.value)
        assert ai_feedback_detail is not None
        assert ai_feedback_detail.status == PipelineExecutionStatus.PENDING_DEPENDENCIES

    @pytest.mark.asyncio
    async def test_atomic_phase_status_update(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test atomic phase status updates prevent race conditions."""
        # Arrange
        batch_id = "test-atomic-batch"
        phase_name = PhaseName.SPELLCHECK

        # Create batch and set initial pipeline state
        await postgres_repository.create_batch(
            {
                "id": batch_id,
                "correlation_id": "test-corr-atomic",
                "status": BatchStatus.PROCESSING_PIPELINES.value,
            },
        )

        # Create proper ProcessingPipelineState object for atomic testing
        initial_state = ProcessingPipelineState(
            batch_id=batch_id,
            requested_pipelines=[phase_name.value],
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.PENDING_DEPENDENCIES),
        )
        await postgres_repository.save_processing_pipeline_state(batch_id, initial_state)

        # Act - First atomic update (should succeed)
        success1 = await postgres_repository.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=phase_name,
            expected_status=PipelineExecutionStatus.PENDING_DEPENDENCIES,
            new_status=PipelineExecutionStatus.IN_PROGRESS,
            completion_timestamp="2025-01-30T10:30:00Z",
        )

        # Act - Second atomic update with wrong expected status (should fail)
        success2 = await postgres_repository.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=phase_name,
            # Wrong - it's now IN_PROGRESS
            expected_status=PipelineExecutionStatus.PENDING_DEPENDENCIES,
            new_status=PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
        )

        # Act - Third atomic update with correct expected status (should succeed)
        success3 = await postgres_repository.update_phase_status_atomically(
            batch_id=batch_id,
            phase_name=phase_name,
            expected_status=PipelineExecutionStatus.IN_PROGRESS,  # Correct current status
            new_status=PipelineExecutionStatus.COMPLETED_SUCCESSFULLY,
            completion_timestamp="2025-01-30T11:00:00Z",
        )

        # Assert
        assert success1 is True  # First update succeeded
        assert success2 is False  # Second update failed (race condition prevented)
        assert success3 is True  # Third update succeeded

        # Verify final state
        final_state = await postgres_repository.get_processing_pipeline_state(batch_id)
        assert final_state is not None
        pipeline_detail = final_state.get_pipeline(phase_name.value)
        assert pipeline_detail is not None
        assert pipeline_detail.status == PipelineExecutionStatus.COMPLETED_SUCCESSFULLY
        assert pipeline_detail.completed_at is not None

    @pytest.mark.asyncio
    async def test_concurrent_atomic_operations(
        self,
        postgres_repository: PostgreSQLBatchRepositoryImpl,
    ) -> None:
        """Test that concurrent atomic operations are handled correctly."""
        # Arrange
        batch_id = "test-concurrent-batch"
        phase_name = PhaseName.SPELLCHECK

        # Create batch and set initial state
        await postgres_repository.create_batch(
            {
                "id": batch_id,
                "correlation_id": "test-corr-concurrent",
                "status": BatchStatus.PROCESSING_PIPELINES.value,
            },
        )

        # Create proper ProcessingPipelineState object for concurrent testing
        initial_state = ProcessingPipelineState(
            batch_id=batch_id,
            requested_pipelines=[phase_name.value],
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.PENDING_DEPENDENCIES),
        )
        await postgres_repository.save_processing_pipeline_state(batch_id, initial_state)

        # Act - Run concurrent atomic updates
        async def attempt_update(
            expected: PipelineExecutionStatus, new: PipelineExecutionStatus
        ) -> bool:
            return await postgres_repository.update_phase_status_atomically(
                batch_id=batch_id,
                phase_name=phase_name,
                expected_status=expected,
                new_status=new,
            )

        # Run two concurrent updates trying to move from PENDING_DEPENDENCIES to different states
        task1 = asyncio.create_task(
            attempt_update(
                PipelineExecutionStatus.PENDING_DEPENDENCIES, PipelineExecutionStatus.IN_PROGRESS
            )
        )
        task2 = asyncio.create_task(
            attempt_update(
                PipelineExecutionStatus.PENDING_DEPENDENCIES, PipelineExecutionStatus.FAILED
            )
        )

        results = await asyncio.gather(task1, task2, return_exceptions=True)

        # Assert - Exactly one should succeed, one should fail
        successes = sum(1 for result in results if result is True)
        failures = sum(1 for result in results if result is False)

        assert successes == 1, f"Expected exactly 1 success, got {successes}"
        assert failures == 1, f"Expected exactly 1 failure, got {failures}"

        # Verify the final state is one of the attempted states
        final_state = await postgres_repository.get_processing_pipeline_state(batch_id)
        assert final_state is not None
        pipeline_detail = final_state.get_pipeline(phase_name.value)
        assert pipeline_detail is not None
        assert pipeline_detail.status.value in ["in_progress", "failed"]

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
                "correlation_id": "test-corr-status",
                "status": BatchStatus.AWAITING_CONTENT_VALIDATION.value,
            },
        )

        # Act - Update status
        update_success = await postgres_repository.update_batch_status(
            batch_id,
            BatchStatus.READY_FOR_PIPELINE_EXECUTION.value,
        )

        # Act - Retrieve updated batch
        updated_batch = await postgres_repository.get_batch_by_id(batch_id)

        # Assert
        assert update_success is True
        assert updated_batch is not None
        assert updated_batch["status"] == BatchStatus.READY_FOR_PIPELINE_EXECUTION.value

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
            BatchStatus.COMPLETED_SUCCESSFULLY.value,
        )
        assert status_update is False

        # Test pipeline state save (should fail)
        test_state = ProcessingPipelineState(
            batch_id=nonexistent_id,
            requested_pipelines=["test"],
        )
        pipeline_save = await postgres_repository.save_processing_pipeline_state(
            nonexistent_id,
            test_state,
        )
        assert pipeline_save is False
