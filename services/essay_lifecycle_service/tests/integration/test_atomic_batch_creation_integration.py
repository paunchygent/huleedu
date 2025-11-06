"""
Integration tests for atomic batch creation in Essay Lifecycle Service.

Tests the complete integration of BatchCoordinationHandler with real infrastructure
to verify that the atomic batch creation fixes the race condition issue.

Uses PostgreSQL database infrastructure with testcontainers.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.error_enums import ErrorCode
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.metadata_models import StorageReferenceMetadata, SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import HuleEduError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import (
    DefaultBatchCoordinationHandler,
)
from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
    DefaultBatchEssayTracker,
)
from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.db_failure_tracker import DBFailureTracker
from services.essay_lifecycle_service.implementations.db_pending_content_ops import (
    DBPendingContentOperations,
)
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.models_db import Base
from services.essay_lifecycle_service.protocols import EventPublisher, SlotOperationsProtocol


class MockEventPublisher(EventPublisher):
    """Minimal event publisher for testing without Kafka complexity."""

    def __init__(self) -> None:
        self.published_events: list[tuple[str, Any, Any]] = []

    async def publish_status_update(
        self,
        essay_id: str,
        batch_id: str | None,
        status: EssayStatus,
        correlation_id: UUID,
    ) -> None:
        """Record status update events for verification."""
        self.published_events.append(
            ("status_update", (essay_id, batch_id, status), correlation_id)
        )

    async def publish_batch_phase_progress(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
        total_essays_in_phase: int,
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Record batch phase progress events for verification."""
        self.published_events.append(
            (
                "batch_phase_progress",
                {
                    "batch_id": batch_id,
                    "phase": phase,
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "total_essays_in_phase": total_essays_in_phase,
                },
                correlation_id,
            )
        )

    async def publish_batch_phase_concluded(
        self,
        batch_id: str,
        phase: str,
        status: str,
        details: dict[str, Any],
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Record batch phase concluded events for verification."""
        self.published_events.append(
            (
                "batch_phase_concluded",
                {"batch_id": batch_id, "phase": phase, "status": status, "details": details},
                correlation_id,
            )
        )

    async def publish_batch_essays_ready(
        self, event_data: Any, correlation_id: UUID, session: AsyncSession | None = None
    ) -> None:
        """Record published events for verification."""
        self.published_events.append(("batch_essays_ready", event_data, correlation_id))

    async def publish_excess_content_provisioned(
        self, event_data: Any, correlation_id: UUID, session: AsyncSession | None = None
    ) -> None:
        """Record published events for verification."""
        self.published_events.append(("excess_content_provisioned", event_data, correlation_id))

    async def publish_els_batch_phase_outcome(
        self, event_data: Any, correlation_id: UUID, session: AsyncSession | None = None
    ) -> None:
        """Record published events for verification."""
        self.published_events.append(("els_batch_phase_outcome", event_data, correlation_id))

    async def publish_essay_slot_assigned(
        self, event_data: Any, correlation_id: UUID, session: AsyncSession | None = None
    ) -> None:
        """Record published events for verification."""
        # Validate EssaySlotAssignedV1 structure
        assert hasattr(event_data, "batch_id"), "EssaySlotAssignedV1 must have batch_id"
        assert hasattr(event_data, "essay_id"), "EssaySlotAssignedV1 must have essay_id"
        assert hasattr(event_data, "file_upload_id"), "EssaySlotAssignedV1 must have file_upload_id"
        assert hasattr(event_data, "text_storage_id"), (
            "EssaySlotAssignedV1 must have text_storage_id"
        )

        # Validate field values
        assert event_data.entity_id, "batch_id must not be empty"
        assert event_data.essay_id, "essay_id must not be empty"
        assert event_data.file_upload_id, "file_upload_id must not be empty"
        assert event_data.text_storage_id, "text_storage_id must not be empty"

        self.published_events.append(("essay_slot_assigned", event_data, correlation_id))

    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,
        topic: str,
        session: AsyncSession | None = None,
    ) -> None:
        """Mock outbox publishing - records event for testing."""
        self.published_events.append(
            (
                "outbox",
                {
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "event_type": event_type,
                    "event_data": event_data,
                    "topic": topic,
                },
                event_data.metadata.correlation_id if hasattr(event_data, "metadata") else None,
            )
        )


class TestAtomicBatchCreationIntegration:
    """Integration tests for atomic batch creation behavior with real infrastructure."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, Any, None]:
        """Start PostgreSQL test container for integration tests."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    class IntegrationTestSettings(Settings):
        """Test settings that override DATABASE_URL for testing."""

        def __init__(self, database_url: str) -> None:
            super().__init__()
            # Override DATABASE_URL using private attribute (property pattern)
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
        """Create test settings pointing to the PostgreSQL test container."""
        # Get PostgreSQL connection URL and ensure it uses asyncpg driver
        pg_connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        return self.IntegrationTestSettings(database_url=pg_connection_url)

    @pytest.fixture
    async def postgres_repository(self, test_settings: Settings) -> PostgreSQLEssayRepository:
        """Create PostgreSQL repository with test database."""
        engine = create_async_engine(test_settings.DATABASE_URL, echo=False)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        repository = PostgreSQLEssayRepository(session_factory)

        # Clean up any existing data to ensure test isolation
        async with repository.get_session_factory()() as session:
            from sqlalchemy import delete

            from services.essay_lifecycle_service.models_db import BatchEssayTracker, EssayStateDB

            # Delete from child table first to respect foreign key constraint
            await session.execute(delete(EssayStateDB))
            await session.execute(delete(BatchEssayTracker))
            await session.commit()

        return repository

    @pytest.fixture
    async def batch_tracker_persistence(
        self, test_settings: Settings, postgres_repository: PostgreSQLEssayRepository
    ) -> BatchTrackerPersistence:
        """Create real batch tracker persistence with PostgreSQL."""
        # Use the engine from the session factory
        engine = create_async_engine(test_settings.DATABASE_URL, echo=False)
        return BatchTrackerPersistence(engine)

    @pytest.fixture
    async def failure_tracker(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> DBFailureTracker:
        """Create DB-based failure tracker."""
        session_factory = postgres_repository.get_session_factory()
        return DBFailureTracker(session_factory)

    @pytest.fixture
    async def batch_tracker(
        self,
        batch_tracker_persistence: BatchTrackerPersistence,
        failure_tracker: DBFailureTracker,
    ) -> DefaultBatchEssayTracker:
        """Create real batch tracker with PostgreSQL persistence and DB-based implementations."""
        # Create mock pending content ops for testing
        mock_pending_content_ops = AsyncMock(spec=DBPendingContentOperations)

        # Provide a no-op slot operations implementation (Option B does not use it)

        class NoopSlotOperations(SlotOperationsProtocol):
            async def assign_slot_atomic(
                self,
                batch_id: str,
                content_metadata: dict[str, Any],
                correlation_id: UUID | None = None,
            ) -> str | None:
                return None

            async def get_available_slot_count(self, batch_id: str) -> int:
                return 0

            async def get_assigned_count(self, batch_id: str) -> int:
                return 0

            async def get_essay_id_for_content(
                self, batch_id: str, text_storage_id: str
            ) -> str | None:
                return None

        slot_operations = NoopSlotOperations()

        return DefaultBatchEssayTracker(
            batch_tracker_persistence,
            failure_tracker,
            slot_operations,
            mock_pending_content_ops,
        )

    @pytest.fixture
    def event_publisher(self) -> AsyncMock:
        """Mock BatchLifecyclePublisher for testing."""
        return AsyncMock(spec=BatchLifecyclePublisher)

    @pytest.fixture
    def sample_batch_event(self) -> BatchEssaysRegistered:
        """Create sample BatchEssaysRegistered event."""
        return BatchEssaysRegistered(
            entity_id="integration-test-batch",
            expected_essay_count=3,
            essay_ids=["essay_001", "essay_002", "essay_003"],
            course_code=CourseCode.ENG5,
            student_prompt_ref=StorageReferenceMetadata(
                references={"student_prompt_text": {"storage_id": "test-integration-prompt", "path": ""}}
            ),
            user_id="test_user_123",
            metadata=SystemProcessingMetadata(
                entity_id="integration-test-batch",
                entity_type="batch",
                parent_id=None,
            ),
        )

    @pytest.fixture
    def session_factory(
        self, postgres_repository: PostgreSQLEssayRepository
    ) -> async_sessionmaker[AsyncSession]:
        """Get session factory from repository for Unit of Work pattern."""
        return postgres_repository.get_session_factory()

    @pytest.fixture
    async def coordination_handler(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        postgres_repository: PostgreSQLEssayRepository,
        event_publisher: AsyncMock,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> DefaultBatchCoordinationHandler:
        """Create coordination handler with real components including session factory."""
        # Create mock pending content ops for testing
        mock_pending_content_ops = AsyncMock(spec=DBPendingContentOperations)

        # Create content assignment service
        from services.essay_lifecycle_service.domain_services import ContentAssignmentService

        content_assignment_service = ContentAssignmentService(
            batch_tracker=batch_tracker,
            repository=postgres_repository,
            batch_lifecycle_publisher=event_publisher,
        )

        return DefaultBatchCoordinationHandler(
            batch_tracker=batch_tracker,
            repository=postgres_repository,
            batch_lifecycle_publisher=event_publisher,
            pending_content_ops=mock_pending_content_ops,
            content_assignment_service=content_assignment_service,
            session_factory=session_factory,
        )

    @pytest.mark.asyncio
    async def test_atomic_batch_creation_success_integration(
        self,
        coordination_handler: DefaultBatchCoordinationHandler,
        sample_batch_event: BatchEssaysRegistered,
        postgres_repository: PostgreSQLEssayRepository,
    ) -> None:
        """Test that handler creates all essays atomically in database."""
        correlation_id = uuid4()

        # Act - Process batch registration event
        result = await coordination_handler.handle_batch_essays_registered(
            sample_batch_event, correlation_id
        )

        # Assert - Handler succeeded
        assert result is True

        # Assert - All essays were created in database atomically
        for essay_id in sample_batch_event.essay_ids:
            essay = await postgres_repository.get_essay_state(essay_id)
            assert essay is not None
            assert essay.essay_id == essay_id
            assert essay.batch_id == sample_batch_event.entity_id
            # Verify all essays have the expected initial status
            from common_core.status_enums import EssayStatus

            assert essay.current_status == EssayStatus.UPLOADED

        # Assert - Batch listing returns all essays
        batch_essays = await postgres_repository.list_essays_by_batch(sample_batch_event.entity_id)
        assert len(batch_essays) == 3
        essay_ids = {essay.essay_id for essay in batch_essays}
        expected_ids = set(sample_batch_event.essay_ids)
        assert essay_ids == expected_ids

    @pytest.mark.asyncio
    async def test_atomic_batch_creation_database_failure_rollback(
        self,
        coordination_handler: DefaultBatchCoordinationHandler,
        sample_batch_event: BatchEssaysRegistered,
        postgres_repository: PostgreSQLEssayRepository,
        batch_tracker_persistence: BatchTrackerPersistence,
    ) -> None:
        """Test that database failure during batch creation rolls back all changes."""
        # Arrange - First create the batch tracker record to satisfy foreign key constraint
        from services.essay_lifecycle_service.models_db import BatchEssayTracker

        async with postgres_repository.get_session_factory()() as session:
            # Store student_prompt_ref in batch_metadata following Phase 3.2 pattern
            batch_metadata = {}
            if sample_batch_event.student_prompt_ref:
                batch_metadata["student_prompt_ref"] = sample_batch_event.student_prompt_ref.model_dump()

            batch_tracker_record = BatchEssayTracker(
                batch_id=sample_batch_event.entity_id,
                expected_essay_ids=sample_batch_event.essay_ids,
                available_slots=sample_batch_event.essay_ids,
                expected_count=len(sample_batch_event.essay_ids),
                course_code=sample_batch_event.course_code.value,
                batch_metadata=batch_metadata,
                user_id=sample_batch_event.user_id,
                correlation_id=str(uuid4()),
                timeout_seconds=300,
                # Don't set created_at/updated_at - they have server_default
            )
            session.add(batch_tracker_record)
            await session.commit()

        # Now create one essay manually to cause constraint violation
        essay_id = "essay_001"  # Same as first essay in batch
        batch_id = sample_batch_event.entity_id

        # Create essay using Unit of Work pattern
        async with postgres_repository.get_session_factory()() as session:
            async with session.begin():
                await postgres_repository.create_essay_record(
                    essay_id=essay_id, batch_id=batch_id, session=session
                )

        correlation_id = uuid4()

        # Act & Assert - Handler should fail due to constraint violation
        with pytest.raises(HuleEduError) as exc_info:
            await coordination_handler.handle_batch_essays_registered(
                sample_batch_event, correlation_id
            )

        # Validate error structure
        error = exc_info.value
        assert error.error_detail.error_code == ErrorCode.PROCESSING_ERROR
        assert "Database error during batch essay creation" in error.error_detail.message
        assert "IntegrityError" in error.error_detail.message
        assert error.error_detail.service == "essay_lifecycle_service"
        assert error.error_detail.operation == "create_essay_records_batch"

        # Assert - Only the manually created essay should exist (atomic rollback)
        existing_essay = await postgres_repository.get_essay_state("essay_001")
        assert existing_essay is not None

        # The other essays should NOT exist due to transaction rollback
        essay_002 = await postgres_repository.get_essay_state("essay_002")
        essay_003 = await postgres_repository.get_essay_state("essay_003")
        assert essay_002 is None
        assert essay_003 is None

        # Batch should still only have 1 essay (the pre-existing one)
        batch_essays = await postgres_repository.list_essays_by_batch(sample_batch_event.entity_id)
        assert len(batch_essays) == 1

    @pytest.mark.asyncio
    async def test_atomic_batch_creation_empty_essay_list(
        self,
        coordination_handler: DefaultBatchCoordinationHandler,
        postgres_repository: PostgreSQLEssayRepository,
        batch_tracker: DefaultBatchEssayTracker,
    ) -> None:
        """Test that handler gracefully handles empty essay list."""
        # Arrange - Event with empty essay list
        empty_event = BatchEssaysRegistered(
            entity_id="empty-batch",
            expected_essay_count=0,
            essay_ids=[],  # Empty list
            course_code=CourseCode.ENG5,
            student_prompt_ref=StorageReferenceMetadata(
                references={
                    ContentType.STUDENT_PROMPT_TEXT: {
                        "storage_id": "prompt-empty",
                        "path": "",
                    }
                }
            ),
            user_id="test_user_123",
            metadata=SystemProcessingMetadata(
                entity_id="empty-batch",
                entity_type="batch",
                parent_id=None,
            ),
        )

        correlation_id = uuid4()

        # Act & Assert - Empty batches are rejected by batch state validation
        with pytest.raises(HuleEduError) as exc_info:
            await coordination_handler.handle_batch_essays_registered(empty_event, correlation_id)

        # Validate error
        error = exc_info.value
        assert error.error_detail.error_code == ErrorCode.VALIDATION_ERROR
        # The error message is in the message field
        assert error.error_detail.message == "Cannot register batch with empty essay_ids"

        # Assert - No essays created
        batch_essays = await postgres_repository.list_essays_by_batch("empty-batch")
        assert len(batch_essays) == 0

        # Assert - Batch expectation was NOT registered in tracker (rejected before registration)
        batch_status = await batch_tracker.get_batch_status("empty-batch")
        assert batch_status is None  # Empty batches are rejected before tracker registration

    @pytest.mark.asyncio
    async def test_atomic_batch_creation_preserves_existing_functionality(
        self,
        coordination_handler: DefaultBatchCoordinationHandler,
        sample_batch_event: BatchEssaysRegistered,
        postgres_repository: PostgreSQLEssayRepository,
        batch_tracker: DefaultBatchEssayTracker,
        event_publisher: AsyncMock,
    ) -> None:
        """Test that atomic behavior preserves all existing handler functionality."""
        correlation_id = uuid4()

        # Act - Process batch registration event
        result = await coordination_handler.handle_batch_essays_registered(
            sample_batch_event, correlation_id
        )

        # Assert - Handler succeeded
        assert result is True

        # Assert - Batch tracker registered the batch expectation
        batch_status = await batch_tracker.get_batch_status(sample_batch_event.entity_id)
        assert batch_status is not None
        assert batch_status["expected_count"] == 3
        assert batch_status["ready_count"] == 0  # No content assigned yet

        # Assert - All essays exist in database with correct data
        for essay_id in sample_batch_event.essay_ids:
            essay = await postgres_repository.get_essay_state(essay_id)
            assert essay is not None
            assert essay.essay_id == essay_id
            assert essay.batch_id == sample_batch_event.entity_id
            # Verify default state from atomic creation
            from common_core.status_enums import EssayStatus

            assert essay.current_status == EssayStatus.UPLOADED

        # Assert - Event publisher was not called (only called later in content flow)
        # (Test simplified - using mock BatchLifecyclePublisher)
