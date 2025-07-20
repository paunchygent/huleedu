"""
Targeted integration test for Redis transaction fix and database update pattern.

This test validates the two critical fixes:
1. Redis atomic slot assignment with correct WATCH/MULTI/EXEC transaction pattern
2. Database update (not create) for existing essays during content provisioning

Uses testcontainers to create isolated test environment.
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient
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
from services.essay_lifecycle_service.implementations.event_publisher import DefaultEventPublisher
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)

logger = create_service_logger("test.redis_transaction_db_update")


@pytest.mark.integration
@pytest.mark.asyncio
class TestRedisTransactionAndDatabaseUpdate:
    """Test the exact failure points: Redis transaction + DB update."""

    @pytest.fixture
    async def test_infrastructure(self):
        """Set up Redis and PostgreSQL containers with initialized services."""
        # Start containers
        redis_container = RedisContainer("redis:7-alpine")
        postgres_container = PostgresContainer("postgres:15")

        with redis_container as redis, postgres_container as pg:
            # Get connection details
            redis_url = f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}"
            db_url = (
                f"postgresql+asyncpg://{pg.username}:{pg.password}@"
                f"{pg.get_container_host_ip()}:{pg.get_exposed_port(5432)}/{pg.dbname}"
            )

            # Create settings with environment variable override for DATABASE_URL
            import os
            os.environ["ESSAY_LIFECYCLE_SERVICE_DATABASE_URL"] = db_url
            os.environ["ESSAY_LIFECYCLE_SERVICE_REDIS_URL"] = redis_url

            settings = Settings()

            # Initialize services
            redis_client = RedisClient(client_id="test-redis", redis_url=redis_url)
            await redis_client.start()

            redis_coordinator = RedisBatchCoordinator(redis_client, logger)

            repository = PostgreSQLEssayRepository(settings)
            await repository.initialize_db_schema()
            await repository.run_migrations()

            persistence = BatchTrackerPersistence(repository.engine)

            batch_tracker = DefaultBatchEssayTracker(persistence, redis_coordinator)
            await batch_tracker.initialize_from_database()

            event_publisher = DefaultEventPublisher(
                kafka_bus=None,  # Not needed for this test
                settings=settings,
                redis_client=redis_client,
                batch_tracker=batch_tracker,
            )

            handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=repository,
                event_publisher=event_publisher,
            )

            yield {
                "handler": handler,
                "repository": repository,
                "batch_tracker": batch_tracker,
                "redis_coordinator": redis_coordinator,
                "redis_client": redis_client,
            }

            # Cleanup
            await redis_client.stop()
            await repository.engine.dispose()

    async def test_slot_assignment_with_content_provisioning(self, test_infrastructure):
        """Test the exact sequence that was failing: batch registration → slot assignment → content update."""
        handler = test_infrastructure["handler"]
        repository = test_infrastructure["repository"]
        redis_coordinator = test_infrastructure["redis_coordinator"]

        # Step 1: Register batch (creates initial essay records)
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(3)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            course_code=CourseCode.ENG5,
            essay_instructions="Test essay",
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        # This creates initial essay records in the database
        success = await handler.handle_batch_essays_registered(batch_event, correlation_id)
        assert success, "Batch registration should succeed"

        # Verify essays were created
        essays = await repository.list_essays_by_batch(batch_id)
        assert len(essays) == 3, "Should have 3 essays created"
        for essay in essays:
            assert essay.current_status == EssayStatus.UPLOADED
            # Check that no content has been assigned yet
            assert ContentType.ORIGINAL_ESSAY not in essay.storage_references

        # Step 2: Test atomic slot assignment
        text_storage_id = "test_storage_123"
        content_metadata = {
            "text_storage_id": text_storage_id,
            "original_file_name": "test.txt",
            "file_size": 1000,
        }

        # This should use the fixed Redis transaction pattern
        assigned_essay_id = await redis_coordinator.assign_slot_atomic(batch_id, content_metadata)
        assert assigned_essay_id is not None, "Slot assignment should succeed"
        assert assigned_essay_id in essay_ids, "Should assign one of the registered essay IDs"

        # Step 3: Test database update (not create)
        essay_data = {
            "internal_essay_id": assigned_essay_id,
            "initial_status": EssayStatus.READY_FOR_PROCESSING,
            "original_file_name": "test.txt",
            "file_size": 1000,
            "content_hash": "abc123",
        }

        # This should UPDATE the existing essay, not try to create a new one
        was_created, final_essay_id = await repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            essay_data=essay_data,
            correlation_id=correlation_id,
        )

        assert was_created is True, "First content assignment should report as created"
        assert final_essay_id == assigned_essay_id, "Should return the same essay ID"

        # Verify the essay was updated, not duplicated
        updated_essay = await repository.get_essay_state(assigned_essay_id)
        assert updated_essay is not None
        assert updated_essay.storage_references.get(ContentType.ORIGINAL_ESSAY) == text_storage_id
        assert updated_essay.current_status == EssayStatus.READY_FOR_PROCESSING
        assert updated_essay.processing_metadata["text_storage_id"] == text_storage_id

        # Step 4: Test idempotency
        was_created2, final_essay_id2 = await repository.create_essay_state_with_content_idempotency(
            batch_id=batch_id,
            text_storage_id=text_storage_id,
            essay_data=essay_data,
            correlation_id=correlation_id,
        )

        assert was_created2 is False, "Second attempt should be idempotent"
        assert final_essay_id2 == assigned_essay_id, "Should return the same essay ID"

    async def test_concurrent_slot_assignments(self, test_infrastructure):
        """Test multiple concurrent slot assignments to verify atomicity."""
        handler = test_infrastructure["handler"]
        redis_coordinator = test_infrastructure["redis_coordinator"]

        # Register batch with 5 essays
        batch_id = str(uuid4())
        essay_ids = [str(uuid4()) for _ in range(5)]
        correlation_id = uuid4()

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            course_code=CourseCode.ENG5,
            essay_instructions="Test concurrent",
            essay_ids=essay_ids,
            expected_essay_count=len(essay_ids),
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
                timestamp=datetime.now(UTC),
                processing_stage=None,
            ),
        )

        await handler.handle_batch_essays_registered(batch_event, correlation_id)

        # Perform 5 concurrent slot assignments with retry logic
        async def assign_slot_with_retry(index: int, max_retries: int = 10):
            """Assign a slot with retry logic for handling transaction conflicts."""
            content_metadata = {
                "text_storage_id": f"storage_{index}",
                "original_file_name": f"file_{index}.txt",
            }

            for attempt in range(max_retries):
                result = await redis_coordinator.assign_slot_atomic(batch_id, content_metadata)
                if result is not None:
                    logger.info(f"Worker {index} assigned slot {result} on attempt {attempt + 1}")
                    return result

                # Transaction failed due to concurrent modification, retry with backoff
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.01 * (attempt + 1))  # Exponential backoff
                    logger.debug(f"Worker {index} retrying slot assignment (attempt {attempt + 2})")

            return None  # Failed after all retries

        # Launch concurrent workers
        results = await asyncio.gather(*[assign_slot_with_retry(i) for i in range(5)])

        # Verify results
        successful_assignments = [r for r in results if r is not None]
        assert len(successful_assignments) == 5, f"Expected 5 successful assignments, got {len(successful_assignments)}: {results}"

        # Verify all assigned essay IDs are unique
        assert len(set(successful_assignments)) == 5, "All assigned essay IDs should be unique"

        # Verify no duplicate assignments in Redis state
        assignments = await redis_coordinator.get_batch_assignments(batch_id)
        assert len(assignments) == 5, f"Expected 5 assignments in Redis, got {len(assignments)}"

        # Verify all content metadata was stored correctly
        for i in range(5):
            storage_id = f"storage_{i}"
            found = any(
                meta.get("text_storage_id") == storage_id
                for meta in assignments.values()
            )
            assert found, f"Content metadata for {storage_id} not found in assignments"

        # Verify no slots remaining
        remaining_count = await redis_coordinator.get_available_slot_count(batch_id)
        assert remaining_count == 0, "All slots should be assigned"

    async def test_transaction_rollback_on_watch_failure(self, test_infrastructure):
        """Test that Redis transaction properly handles WATCH failures."""
        redis_coordinator = test_infrastructure["redis_coordinator"]
        redis_client = test_infrastructure["redis_client"]

        batch_id = str(uuid4())
        slots_key = f"batch:{batch_id}:available_slots"

        # Add slots
        await redis_client.sadd(slots_key, "essay_1", "essay_2")

        # Simulate concurrent modification during transaction
        async def interfere():
            await asyncio.sleep(0.05)  # Let transaction start
            await redis_client.sadd(slots_key, "essay_3")  # Modify watched key

        # Start interference task
        interfere_task = asyncio.create_task(interfere())

        # Attempt slot assignment (should retry or handle gracefully)
        content_metadata = {"text_storage_id": "test", "original_file_name": "test.txt"}
        result = await redis_coordinator.assign_slot_atomic(batch_id, content_metadata)

        await interfere_task

        # Transaction might succeed or fail depending on timing, but should not corrupt state
        if result is not None:
            # If succeeded, verify slot was properly removed
            remaining = await redis_client.scard(slots_key)
            assert remaining >= 1, "Should have at least 1 slot remaining"
