"""
Integration tests for atomic batch creation in Essay Lifecycle Service.

Tests the complete integration of BatchCoordinationHandler with real infrastructure
to verify that the atomic batch creation fixes the race condition issue.

Uses real PostgreSQL and Redis infrastructure with testcontainers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Any
from uuid import UUID, uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.error_enums import ErrorCode
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import (
    DefaultBatchCoordinationHandler,
)
from services.essay_lifecycle_service.implementations.batch_essay_tracker_impl import (
    DefaultBatchEssayTracker,
)
from services.essay_lifecycle_service.implementations.batch_tracker_persistence import (
    BatchTrackerPersistence,
)
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.protocols import EventPublisher


class MockEventPublisher(EventPublisher):
    """Minimal event publisher for testing without Kafka complexity."""

    def __init__(self) -> None:
        self.published_events: list[tuple[str, Any, Any]] = []

    async def publish_status_update(
        self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID
    ) -> None:
        """Record status update events for verification."""
        self.published_events.append(("status_update", (essay_ref, status), correlation_id))

    async def publish_batch_phase_progress(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
        total_essays_in_phase: int,
        correlation_id: UUID,
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
    ) -> None:
        """Record batch phase concluded events for verification."""
        self.published_events.append(
            (
                "batch_phase_concluded",
                {"batch_id": batch_id, "phase": phase, "status": status, "details": details},
                correlation_id,
            )
        )

    async def publish_batch_essays_ready(self, event_data: Any, correlation_id: UUID) -> None:
        """Record published events for verification."""
        self.published_events.append(("batch_essays_ready", event_data, correlation_id))

    async def publish_excess_content_provisioned(
        self, event_data: Any, correlation_id: UUID
    ) -> None:
        """Record published events for verification."""
        self.published_events.append(("excess_content_provisioned", event_data, correlation_id))

    async def publish_els_batch_phase_outcome(self, event_data: Any, correlation_id: UUID) -> None:
        """Record published events for verification."""
        self.published_events.append(("els_batch_phase_outcome", event_data, correlation_id))


class TestAtomicBatchCreationIntegration:
    """Integration tests for atomic batch creation behavior with real infrastructure."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, Any, None]:
        """Start PostgreSQL test container for integration tests."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    def redis_container(self) -> Generator[RedisContainer, Any, None]:
        """Start Redis test container for integration tests."""
        container = RedisContainer("redis:7-alpine")
        container.start()
        yield container
        container.stop()

    class IntegrationTestSettings(Settings):
        """Test settings that override both DATABASE_URL and REDIS_URL properties."""

        def __init__(self, database_url: str, redis_url: str) -> None:
            super().__init__()
            # Override DATABASE_URL using private attribute (property pattern)
            object.__setattr__(self, "_database_url", database_url)
            # Override REDIS_URL directly (simple field)
            self.REDIS_URL = redis_url
            self.DATABASE_POOL_SIZE = 2
            self.DATABASE_MAX_OVERFLOW = 1
            self.DATABASE_POOL_PRE_PING = True
            self.DATABASE_POOL_RECYCLE = 3600

        @property
        def DATABASE_URL(self) -> str:
            """Override to return test database URL."""
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def test_settings(
        self, postgres_container: PostgresContainer, redis_container: RedisContainer
    ) -> Settings:
        """Create test settings pointing to the test containers."""
        # Get PostgreSQL connection URL and ensure it uses asyncpg driver
        pg_connection_url = postgres_container.get_connection_url()
        if "+psycopg2://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("+psycopg2://", "+asyncpg://")
        elif "postgresql://" in pg_connection_url:
            pg_connection_url = pg_connection_url.replace("postgresql://", "postgresql+asyncpg://")

        # Get Redis connection URL
        redis_connection_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"

        return self.IntegrationTestSettings(
            database_url=pg_connection_url, redis_url=redis_connection_url
        )

    @pytest.fixture
    async def postgres_repository(self, test_settings: Settings) -> PostgreSQLEssayRepository:
        """Create PostgreSQL repository with test database."""
        repository = PostgreSQLEssayRepository(test_settings)
        await repository.initialize_db_schema()

        # Clean up any existing data to ensure test isolation
        async with repository.session() as session:
            from sqlalchemy import delete

            from services.essay_lifecycle_service.models_db import BatchEssayTracker, EssayStateDB

            await session.execute(delete(EssayStateDB))
            await session.execute(delete(BatchEssayTracker))
            await session.commit()

        return repository

    @pytest.fixture
    async def redis_client(self, test_settings: Settings) -> AsyncGenerator[Any, None]:
        """Create real Redis client for testing."""
        from huleedu_service_libs.redis_client import RedisClient

        client = RedisClient(client_id="test-els", redis_url=test_settings.REDIS_URL)
        await client.start()

        try:
            # Clear any existing data using underlying Redis client
            await client.client.flushdb()
            yield client
        finally:
            await client.stop()

    @pytest.fixture
    async def batch_tracker_persistence(
        self, test_settings: Settings, postgres_repository: PostgreSQLEssayRepository
    ) -> BatchTrackerPersistence:
        """Create real batch tracker persistence with PostgreSQL."""
        return BatchTrackerPersistence(postgres_repository.engine)

    @pytest.fixture
    async def batch_tracker(
        self,
        batch_tracker_persistence: BatchTrackerPersistence,
        redis_client: AtomicRedisClientProtocol,
    ) -> DefaultBatchEssayTracker:
        """Create real batch tracker with PostgreSQL persistence and Redis coordinator."""
        from services.essay_lifecycle_service.config import Settings
        from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
            RedisBatchCoordinator,
        )

        # Create settings mock
        settings = Settings()

        # Create Redis coordinator with real Redis client
        redis_coordinator = RedisBatchCoordinator(redis_client, settings)

        return DefaultBatchEssayTracker(
            persistence=batch_tracker_persistence, redis_coordinator=redis_coordinator
        )

    @pytest.fixture
    def event_publisher(self) -> MockEventPublisher:
        """Create minimal event publisher for testing (avoiding Kafka complexity)."""
        return MockEventPublisher()

    @pytest.fixture
    def sample_batch_event(self) -> BatchEssaysRegistered:
        """Create sample BatchEssaysRegistered event."""
        return BatchEssaysRegistered(
            batch_id="integration-test-batch",
            expected_essay_count=3,
            essay_ids=["essay_001", "essay_002", "essay_003"],
            course_code=CourseCode.ENG5,
            essay_instructions="Write a test essay",
            user_id="test_user_123",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id="integration-test-batch",
                    entity_type="batch",
                    parent_id=None,
                ),
            ),
        )

    @pytest.fixture
    async def coordination_handler(
        self,
        batch_tracker: DefaultBatchEssayTracker,
        postgres_repository: PostgreSQLEssayRepository,
        event_publisher: MockEventPublisher,
    ) -> DefaultBatchCoordinationHandler:
        """Create coordination handler with real components."""
        return DefaultBatchCoordinationHandler(
            batch_tracker=batch_tracker,
            repository=postgres_repository,
            event_publisher=event_publisher,
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
            assert essay.batch_id == sample_batch_event.batch_id
            # Verify all essays have the expected initial status
            from common_core.status_enums import EssayStatus

            assert essay.current_status == EssayStatus.UPLOADED

        # Assert - Batch listing returns all essays
        batch_essays = await postgres_repository.list_essays_by_batch(sample_batch_event.batch_id)
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
    ) -> None:
        """Test that database failure during batch creation rolls back all changes."""
        # Arrange - Create one essay manually to cause constraint violation
        from common_core.metadata_models import EntityReference

        existing_ref = EntityReference(
            entity_id="essay_001",  # Same as first essay in batch
            entity_type="essay",
            parent_id=sample_batch_event.batch_id,
        )
        await postgres_repository.create_essay_record(existing_ref)

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
        batch_essays = await postgres_repository.list_essays_by_batch(sample_batch_event.batch_id)
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
            batch_id="empty-batch",
            expected_essay_count=0,
            essay_ids=[],  # Empty list
            course_code=CourseCode.ENG5,
            essay_instructions="Test empty batch",
            user_id="test_user_123",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id="empty-batch",
                    entity_type="batch",
                    parent_id=None,
                ),
            ),
        )

        correlation_id = uuid4()

        # Act - Process empty batch event
        result = await coordination_handler.handle_batch_essays_registered(
            empty_event, correlation_id
        )

        # Assert - Handler succeeded
        assert result is True

        # Assert - No essays created
        batch_essays = await postgres_repository.list_essays_by_batch("empty-batch")
        assert len(batch_essays) == 0

        # Assert - Batch expectation was registered in tracker
        batch_status = await batch_tracker.get_batch_status("empty-batch")
        assert batch_status is not None
        assert batch_status["expected_count"] == 0

    @pytest.mark.asyncio
    async def test_atomic_batch_creation_preserves_existing_functionality(
        self,
        coordination_handler: DefaultBatchCoordinationHandler,
        sample_batch_event: BatchEssaysRegistered,
        postgres_repository: PostgreSQLEssayRepository,
        batch_tracker: DefaultBatchEssayTracker,
        event_publisher: MockEventPublisher,
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
        batch_status = await batch_tracker.get_batch_status(sample_batch_event.batch_id)
        assert batch_status is not None
        assert batch_status["expected_count"] == 3
        assert batch_status["ready_count"] == 0  # No content assigned yet

        # Assert - All essays exist in database with correct data
        for essay_id in sample_batch_event.essay_ids:
            essay = await postgres_repository.get_essay_state(essay_id)
            assert essay is not None
            assert essay.essay_id == essay_id
            assert essay.batch_id == sample_batch_event.batch_id
            # Verify default state from atomic creation
            from common_core.status_enums import EssayStatus

            assert essay.current_status == EssayStatus.UPLOADED

        # Assert - Event publisher was not called (only called later in content flow)
        assert len(event_publisher.published_events) == 0
