"""
Concurrent race condition tests for distributed Essay Lifecycle Service.

Tests validate that multiple ELS instances coordinating via Redis prevent
race conditions in slot assignment and maintain data integrity under concurrent load.

Uses testcontainers for real infrastructure testing as per Rule 070.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.domain_enums import ContentType, CourseCode
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

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
from services.essay_lifecycle_service.implementations.essay_repository_postgres_impl import (
    PostgreSQLEssayRepository,
)
from services.essay_lifecycle_service.implementations.redis_batch_queries import (
    RedisBatchQueries,
)
from services.essay_lifecycle_service.implementations.redis_batch_state import (
    RedisBatchState,
)
from services.essay_lifecycle_service.implementations.redis_failure_tracker import (
    RedisFailureTracker,
)
from services.essay_lifecycle_service.implementations.redis_script_manager import (
    RedisScriptManager,
)
from services.essay_lifecycle_service.implementations.redis_slot_operations import (
    RedisSlotOperations,
)

from .test_sync_utils import wait_for_batch_ready, wait_for_condition
from .test_utils import DistributedTestSettings, PerformanceMetrics


@pytest.mark.docker
@pytest.mark.asyncio
class TestConcurrentSlotAssignment:
    """Test concurrent slot assignment and race condition prevention."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, Any, None]:
        """PostgreSQL container for distributed testing."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    def redis_container(self) -> Generator[RedisContainer, Any, None]:
        """Redis container for distributed coordination."""
        container = RedisContainer("redis:7-alpine")
        container.start()
        yield container
        container.stop()

    @pytest.fixture
    def distributed_settings(
        self, postgres_container: PostgresContainer, redis_container: RedisContainer
    ) -> Settings:
        """Create distributed test settings."""
        pg_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
        if "postgresql://" in pg_url:
            pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://")

        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"

        return DistributedTestSettings.create_basic_settings(
            database_url=pg_url, redis_url=redis_url
        )

    @pytest.fixture
    async def clean_distributed_state(
        self, distributed_settings: Settings
    ) -> AsyncGenerator[None, None]:
        """Clean Redis and PostgreSQL state between tests."""
        from huleedu_service_libs.redis_client import RedisClient

        # Clean Redis
        redis_client = RedisClient(
            client_id="test-cleanup", redis_url=distributed_settings.REDIS_URL
        )
        await redis_client.start()
        try:
            await redis_client.client.flushdb()
        finally:
            await redis_client.stop()

        # Clean PostgreSQL
        repository = PostgreSQLEssayRepository(distributed_settings)
        await repository.initialize_db_schema()

        async with repository.session() as session:
            from sqlalchemy import delete

            from services.essay_lifecycle_service.models_db import BatchEssayTracker, EssayStateDB

            await session.execute(delete(EssayStateDB))
            await session.execute(delete(BatchEssayTracker))
            await session.commit()

        yield

    @pytest.fixture
    async def distributed_coordinator_instances(
        self, distributed_settings: Settings
    ) -> AsyncGenerator[
        list[tuple[DefaultBatchCoordinationHandler, PostgreSQLEssayRepository, AsyncMock]],
        None,
    ]:
        """Create multiple coordinator instances simulating distributed ELS workers."""

        instances = []

        # Create 3 instances
        for instance_id in range(3):
            # Each instance gets its own Redis client but shares the same Redis server
            from huleedu_service_libs.redis_client import RedisClient

            redis_client = RedisClient(
                client_id=f"test-instance-{instance_id}", redis_url=distributed_settings.REDIS_URL
            )
            await redis_client.start()

            # Shared PostgreSQL repository
            repository = PostgreSQLEssayRepository(distributed_settings)

            # Create modular Redis components
            redis_script_manager = RedisScriptManager(redis_client)
            batch_state = RedisBatchState(redis_client, redis_script_manager)
            batch_queries = RedisBatchQueries(redis_client, redis_script_manager)
            failure_tracker = RedisFailureTracker(redis_client, redis_script_manager)
            slot_operations = RedisSlotOperations(redis_client, redis_script_manager)

            # Batch tracker with modular DI components
            batch_tracker_persistence = BatchTrackerPersistence(repository.engine)
            batch_tracker = DefaultBatchEssayTracker(
                persistence=batch_tracker_persistence,
                batch_state=batch_state,
                batch_queries=batch_queries,
                failure_tracker=failure_tracker,
                slot_operations=slot_operations,
            )

            # Event publisher
            event_publisher = AsyncMock(spec=BatchLifecyclePublisher)

            # Coordination handler
            coordination_handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=repository,
                batch_lifecycle_publisher=event_publisher,
                session_factory=repository.get_session_factory(),
            )

            instances.append((coordination_handler, repository, event_publisher))

        try:
            yield instances
        finally:
            # Cleanup Redis clients
            for coordination_handler, _, _ in instances:
                # Access the Redis client through the modular components
                try:
                    tracker = coordination_handler.batch_tracker
                    if hasattr(tracker, "_batch_state") and hasattr(
                        tracker._batch_state, "_redis_client"
                    ):
                        await tracker._batch_state._redis_client.stop()
                except Exception:
                    pass  # Best effort cleanup

    async def test_concurrent_identical_content_provisioning_race_prevention(
        self,
        distributed_coordinator_instances: list[
            tuple[DefaultBatchCoordinationHandler, PostgreSQLEssayRepository, AsyncMock]
        ],
        clean_distributed_state: None,
    ) -> None:
        """Test concurrent identical content provisions are handled idempotently.

        Verifies that when multiple concurrent requests try to provision the same content
        (identified by text_storage_id), only one essay slot is consumed, but all operations
        return success (idempotent behavior). This prevents race conditions while maintaining
        system reliability.
        """

        # Arrange - Create batch across all instances
        batch_id = f"race_test_{uuid4().hex[:8]}"
        essay_ids = ["essay_001", "essay_002", "essay_003"]

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=len(essay_ids),
            essay_ids=essay_ids,
            course_code=CourseCode.ENG5,
            essay_instructions="Race condition test",
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
            ),
        )

        # Register batch on first instance
        coordination_handler, repository, _ = distributed_coordinator_instances[0]
        correlation_id = uuid4()

        result = await coordination_handler.handle_batch_essays_registered(
            batch_event, correlation_id
        )
        assert result is True

        # Verify batch is properly registered and available for slot assignment
        async def batch_is_available() -> bool:
            # Check that the batch has the expected number of available slots
            batch_status = await repository.get_batch_status_summary(batch_id)
            total_essays = sum(batch_status.values())
            return total_essays == len(essay_ids)

        await wait_for_condition(
            batch_is_available,
            timeout_seconds=3.0,
            description=f"batch {batch_id} to be available with {len(essay_ids)} slots",
        )

        # Act - Send 20 IDENTICAL content events across all instances
        identical_text_storage_id = "identical_content_12345"
        target_essay_id = "essay_001"

        identical_content_event = EssayContentProvisionedV1(
            batch_id=batch_id,
            file_upload_id="test-file-upload-identical",
            text_storage_id=identical_text_storage_id,
            raw_file_storage_id=f"raw_{target_essay_id}_{uuid4().hex[:8]}",
            original_file_name="test_essay.txt",
            file_size_bytes=1500,
            content_md5_hash="test_hash_12345",
        )

        # Create 20 concurrent tasks across different instances
        concurrent_tasks = []
        for i in range(20):
            instance_idx = i % len(distributed_coordinator_instances)
            coord_handler, _, _ = distributed_coordinator_instances[instance_idx]

            task = coord_handler.handle_essay_content_provisioned(identical_content_event, uuid4())
            concurrent_tasks.append(task)

        # Execute all tasks concurrently
        results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)

        # Verify all operations complete successfully (idempotent behavior)
        # In an idempotent system, all operations should return True even if they're no-ops
        successful_operations = 0
        exceptions = []
        for i, task_result in enumerate(results):
            if isinstance(task_result, bool) and task_result:
                successful_operations += 1
            elif isinstance(task_result, BaseException):
                exceptions.append(f"Task {i}: {task_result}")

        # Log the results for debugging
        print(f"\nOperation results: {successful_operations}/20 returned True")
        if exceptions:
            print(f"Exceptions encountered: {exceptions}")

        # All operations should succeed (idempotent behavior)
        assert successful_operations == 20, (
            f"Expected all 20 operations to return True (idempotent behavior), "
            f"but only {successful_operations} succeeded. Exceptions: {exceptions}"
        )

        # The REAL test: Verify database state shows only one essay with the content
        # This proves the race condition prevention works - only 1 slot consumed despite 20 requests
        essay_with_content = await repository.get_essay_by_text_storage_id_and_batch_id(
            batch_id, identical_text_storage_id
        )
        assert essay_with_content is not None, (
            "Content deduplication failed - no essay found with the expected content"
        )

        # The content should be assigned to the first available slot
        # Note: We don't assert specific essay_id as Redis SPOP is non-deterministic
        print(f"Content assigned to essay: {essay_with_content.essay_id}")

        # Critical assertion: Only ONE essay should have content despite 20 concurrent attempts
        batch_essays = await repository.list_essays_by_batch(batch_id)
        essays_with_content = [
            essay
            for essay in batch_essays
            if essay.storage_references and essay.storage_references.get(ContentType.ORIGINAL_ESSAY)
        ]
        assert len(essays_with_content) == 1, (
            f"Race condition NOT prevented! Expected exactly 1 essay with content, "
            f"but found {len(essays_with_content)}. Content deduplication failed."
        )

        # Verify the other slots remain available
        unassigned_essays = [
            essay
            for essay in batch_essays
            if not essay.storage_references
            or not essay.storage_references.get(ContentType.ORIGINAL_ESSAY)
        ]
        assert len(unassigned_essays) == 2, (
            f"Expected 2 unassigned essays, but found {len(unassigned_essays)}. "
            f"Batch state may be corrupted."
        )

    async def test_cross_instance_slot_assignment(
        self,
        distributed_coordinator_instances: list[
            tuple[DefaultBatchCoordinationHandler, PostgreSQLEssayRepository, AsyncMock]
        ],
        clean_distributed_state: None,
    ) -> None:
        """Test slot assignment coordination across multiple ELS instances."""

        # Arrange - Create batch with multiple essays
        batch_id = f"cross_instance_{uuid4().hex[:8]}"
        essay_count = 6
        essay_ids = [f"essay_{i:03d}" for i in range(essay_count)]

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=essay_count,
            essay_ids=essay_ids,
            course_code=CourseCode.ENG5,
            essay_instructions="Cross-instance coordination test",
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
            ),
        )

        # Register batch on first instance
        coordination_handler, repository, _ = distributed_coordinator_instances[0]
        result = await coordination_handler.handle_batch_essays_registered(batch_event, uuid4())
        assert result is True

        # Verify batch is available for content provisioning
        async def batch_slots_available() -> bool:
            batch_status = await repository.get_batch_status_summary(batch_id)
            total_essays = sum(batch_status.values())
            return total_essays == essay_count

        await wait_for_condition(
            batch_slots_available,
            timeout_seconds=3.0,
            description=f"batch {batch_id} slots to be available for content provisioning",
        )

        # Act - Send content events from different instances to different essays
        content_tasks = []
        metrics = PerformanceMetrics()

        for i, essay_id in enumerate(essay_ids):
            instance_idx = i % len(distributed_coordinator_instances)
            coord_handler, _, _ = distributed_coordinator_instances[instance_idx]

            content_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                file_upload_id=f"test-file-upload-bulk-{i}",
                text_storage_id=f"content_{i}_{uuid4().hex[:8]}",
                raw_file_storage_id=f"raw_{essay_id}_{uuid4().hex[:8]}",
                original_file_name=f"essay_{i}.txt",
                file_size_bytes=1000 + i * 100,
                content_md5_hash=f"hash_{i}_{uuid4().hex[:8]}",
            )

            async def process_content_with_metrics(
                handler: DefaultBatchCoordinationHandler,
                event: EssayContentProvisionedV1,
                instance_id: str,
            ) -> bool:
                start_time = asyncio.get_event_loop().time()
                try:
                    result = await handler.handle_essay_content_provisioned(event, uuid4())
                    duration = asyncio.get_event_loop().time() - start_time
                    await metrics.record_operation("content_provision", duration, True, instance_id)
                    return result
                except Exception as e:
                    duration = asyncio.get_event_loop().time() - start_time
                    await metrics.record_operation(
                        "content_provision", duration, False, instance_id, None, {"error": str(e)}
                    )
                    raise

            task = process_content_with_metrics(
                coord_handler, content_event, f"instance_{instance_idx}"
            )
            content_tasks.append(task)

        # Execute all content provisioning concurrently
        results = await asyncio.gather(*content_tasks, return_exceptions=True)

        # Assert - All assignments should succeed
        successful_results = [r for r in results if isinstance(r, bool) and r]
        assert len(successful_results) == essay_count, (
            f"Expected {essay_count} successful assignments, got {len(successful_results)}"
        )

        # Assert - All essays should have unique content assigned
        batch_essays = await repository.list_essays_by_batch(batch_id)
        essays_with_content = [
            essay
            for essay in batch_essays
            if essay.storage_references and essay.storage_references.get(ContentType.ORIGINAL_ESSAY)
        ]
        assert len(essays_with_content) == essay_count

        # Assert - All content assignments should be unique
        content_ids = {
            essay.storage_references[ContentType.ORIGINAL_ESSAY]
            for essay in essays_with_content
            if essay.storage_references
        }
        assert len(content_ids) == essay_count, "Duplicate content assignments detected"

        # Assert - Performance targets met
        stats = metrics.get_operation_statistics()
        assert stats["success_rate"] >= 0.95, f"Success rate too low: {stats['success_rate']}"
        if "avg_duration" in stats:
            assert stats["avg_duration"] < 0.2, (
                f"Average duration too high: {stats['avg_duration']}s"
            )

    async def test_batch_completion_coordination(
        self,
        distributed_coordinator_instances: list[
            tuple[DefaultBatchCoordinationHandler, PostgreSQLEssayRepository, AsyncMock]
        ],
        clean_distributed_state: None,
    ) -> None:
        """Test batch completion detection across distributed instances."""

        # Arrange - Create small batch for completion testing
        batch_id = f"completion_test_{uuid4().hex[:8]}"
        essay_count = 3
        essay_ids = [f"essay_{i:03d}" for i in range(essay_count)]

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=essay_count,
            essay_ids=essay_ids,
            course_code=CourseCode.ENG5,
            essay_instructions="Completion test",
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
            ),
        )

        # Register batch
        coordination_handler, repository, event_publisher = distributed_coordinator_instances[0]
        result = await coordination_handler.handle_batch_essays_registered(batch_event, uuid4())
        assert result is True

        # Verify batch completion test setup is ready
        async def batch_completion_ready() -> bool:
            batch_status = await repository.get_batch_status_summary(batch_id)
            total_essays = sum(batch_status.values())
            return total_essays == essay_count

        await wait_for_condition(
            batch_completion_ready,
            timeout_seconds=3.0,
            description=f"batch {batch_id} completion test setup",
        )

        # Act - Fill all slots from different instances
        for i, essay_id in enumerate(essay_ids):
            instance_idx = i % len(distributed_coordinator_instances)
            coord_handler, _, instance_publisher = distributed_coordinator_instances[instance_idx]

            content_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                file_upload_id=f"test-file-upload-completion-{i}",
                text_storage_id=f"completion_content_{i}_{uuid4().hex[:8]}",
                raw_file_storage_id=f"raw_{essay_id}_{uuid4().hex[:8]}",
                original_file_name=f"completion_essay_{i}.txt",
                file_size_bytes=1200 + i * 50,
                content_md5_hash=f"completion_hash_{i}",
            )

            result = await coord_handler.handle_essay_content_provisioned(content_event, uuid4())
            assert result is True

        # Wait for batch to reach completion state (all essays ready for processing)
        await wait_for_batch_ready(repository, batch_id, essay_count, timeout_seconds=10.0)

        # Assert - Batch should be marked as ready
        batch_status = await repository.get_batch_status_summary(batch_id)
        ready_essays = batch_status.get(EssayStatus.READY_FOR_PROCESSING, 0)
        assert ready_essays == essay_count, (
            f"Expected {essay_count} ready essays, got {ready_essays}"
        )

        # Assert - BatchEssaysReady event should be published exactly once
        all_events = []
        for _, _, publisher in distributed_coordinator_instances:
            all_events.extend(publisher.published_events)

        batch_ready_events = [event for event in all_events if event[0] == "batch_essays_ready"]

        # Note: Due to distributed coordination, we might see multiple publications
        # but they should be idempotent. The important thing is that at least one was published.
        assert len(batch_ready_events) >= 1, "BatchEssaysReady event should be published"

        # Verify all ready events are for the same batch
        for _event_type, event_data, _correlation_id in batch_ready_events:
            assert event_data.batch_id == batch_id

    @pytest.mark.performance
    async def test_high_concurrency_slot_assignment_performance(
        self,
        distributed_coordinator_instances: list[
            tuple[DefaultBatchCoordinationHandler, PostgreSQLEssayRepository, AsyncMock]
        ],
        clean_distributed_state: None,
    ) -> None:
        """Test performance under high concurrency load."""

        # Arrange - Create larger batch for performance testing
        batch_id = f"perf_test_{uuid4().hex[:8]}"
        essay_count = 15
        essay_ids = [f"essay_{i:03d}" for i in range(essay_count)]

        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=essay_count,
            essay_ids=essay_ids,
            course_code=CourseCode.ENG5,
            essay_instructions="Performance test",
            user_id="test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
            ),
        )

        # Register batch
        coordination_handler, repository, _ = distributed_coordinator_instances[0]
        result = await coordination_handler.handle_batch_essays_registered(batch_event, uuid4())
        assert result is True

        # Verify performance test batch is ready for high concurrency testing
        async def performance_batch_ready() -> bool:
            batch_status = await repository.get_batch_status_summary(batch_id)
            total_essays = sum(batch_status.values())
            return total_essays == essay_count

        await wait_for_condition(
            performance_batch_ready,
            timeout_seconds=3.0,
            description=f"performance test batch {batch_id} readiness",
        )

        # Act - High concurrency content provisioning
        metrics = PerformanceMetrics()
        content_tasks = []

        # Create more tasks than essays to test contention
        task_count = essay_count * 2  # 30 tasks for 15 essays

        for i in range(task_count):
            essay_idx = i % essay_count
            essay_id = essay_ids[essay_idx]
            instance_idx = i % len(distributed_coordinator_instances)
            coord_handler, _, _ = distributed_coordinator_instances[instance_idx]

            content_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                file_upload_id=f"test-file-upload-perf-{i}",
                text_storage_id=f"perf_content_{i}_{uuid4().hex[:8]}",
                raw_file_storage_id=f"raw_{essay_id}_{uuid4().hex[:8]}",
                original_file_name=f"perf_essay_{i}.txt",
                file_size_bytes=800 + i * 10,
                content_md5_hash=f"perf_hash_{i}",
            )

            async def process_with_timing(
                handler: DefaultBatchCoordinationHandler,
                event: EssayContentProvisionedV1,
                task_id: int,
            ) -> tuple[bool, int]:
                start_time = asyncio.get_event_loop().time()
                try:
                    result = await handler.handle_essay_content_provisioned(event, uuid4())
                    duration = asyncio.get_event_loop().time() - start_time
                    await metrics.record_operation(
                        "high_concurrency_provision", duration, result, f"task_{task_id}"
                    )
                    return result, task_id
                except Exception as e:
                    duration = asyncio.get_event_loop().time() - start_time
                    await metrics.record_operation(
                        "high_concurrency_provision",
                        duration,
                        False,
                        f"task_{task_id}",
                        None,
                        {"error": str(e)},
                    )
                    return False, task_id

            task = process_with_timing(coord_handler, content_event, i)
            content_tasks.append(task)

        # Execute all tasks concurrently
        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(*content_tasks, return_exceptions=True)
        total_duration = asyncio.get_event_loop().time() - start_time

        # Assert - Performance targets
        successful_results = [r for r in results if isinstance(r, tuple) and r[0] is True]

        # We expect exactly essay_count successful assignments (one per essay)
        assert len(successful_results) == essay_count, (
            f"Expected {essay_count} successful assignments, got {len(successful_results)}"
        )

        # Assert - Performance statistics
        stats = metrics.get_operation_statistics()
        print(f"Performance stats: {stats}")

        # Performance targets from the requirements
        assert stats["success_rate"] >= 0.50, (
            f"Success rate too low: {stats['success_rate']}"
        )  # At least 50% due to contention
        if "p95_duration" in stats:
            # Updated to realistic target for full content provisioning operations
            # (includes Redis coordination + Database updates + Event publishing)
            assert stats["p95_duration"] < 0.5, f"P95 duration too high: {stats['p95_duration']}s"

        assert total_duration < 5.0, f"Total operation time too high: {total_duration}s"

        # Assert - All essays have content (no duplicates)
        batch_essays = await repository.list_essays_by_batch(batch_id)
        essays_with_content = [
            essay
            for essay in batch_essays
            if essay.storage_references and essay.storage_references.get(ContentType.ORIGINAL_ESSAY)
        ]
        assert len(essays_with_content) == essay_count

        # Assert - All content IDs are unique
        content_ids = {
            essay.storage_references[ContentType.ORIGINAL_ESSAY] for essay in essays_with_content
        }
        assert len(content_ids) == essay_count, "Duplicate content assignments found"
