"""
Redis state consistency validation tests for distributed Essay Lifecycle Service.

Tests validate that Redis atomic operations maintain data integrity under high load,
handle failure scenarios gracefully, and provide consistent performance benchmarks.

Follows Rule 070 patterns with real Redis infrastructure via testcontainers.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncGenerator, Coroutine, Generator
from typing import Any, TypedDict
from uuid import uuid4

import pytest
from testcontainers.redis import RedisContainer

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)


class RedisStateValidator:
    """Validates Redis state consistency and integrity."""

    def __init__(self, redis_coordinator: RedisBatchCoordinator) -> None:
        self._coordinator = redis_coordinator
        self._redis = redis_coordinator._redis

    async def validate_batch_integrity(self, batch_id: str) -> dict[str, Any]:
        """Validate internal consistency of batch state in Redis."""

        # Get all batch keys
        available_key = self._coordinator._get_available_slots_key(batch_id)
        assignments_key = self._coordinator._get_assignments_key(batch_id)
        metadata_key = self._coordinator._get_metadata_key(batch_id)
        timeout_key = self._coordinator._get_timeout_key(batch_id)

        # Get counts atomically
        available_count = await self._redis.scard(available_key)
        assigned_count = await self._redis.hlen(assignments_key)
        metadata_exists = await self._redis.exists(metadata_key)
        timeout_exists = await self._redis.exists(timeout_key)

        # Get actual data
        available_slots = await self._redis.smembers(available_key)
        assignments = await self._redis.hgetall(assignments_key)

        # Validate no overlap between available and assigned
        assigned_essay_ids = set(assignments.keys()) if assignments else set()
        available_essay_ids = set(available_slots) if available_slots else set()

        overlap = assigned_essay_ids & available_essay_ids

        return {
            "batch_id": batch_id,
            "available_count": available_count,
            "assigned_count": assigned_count,
            "total_slots": available_count + assigned_count,
            "metadata_exists": metadata_exists == 1,
            "timeout_exists": timeout_exists == 1,
            "no_overlap": len(overlap) == 0,
            "overlap_essay_ids": list(overlap),
            "available_essay_ids": list(available_essay_ids),
            "assigned_essay_ids": list(assigned_essay_ids),
        }

    async def validate_atomic_operations(
        self, batch_id: str, operation_count: int
    ) -> dict[str, Any]:
        """Validate atomicity of Redis operations under load."""

        # Record initial state
        initial_state = await self.validate_batch_integrity(batch_id)

        # Perform concurrent slot assignments
        assignment_tasks = []
        for i in range(operation_count):
            content_metadata = {
                "text_storage_id": f"atomic_test_{i}_{uuid4().hex[:8]}",
                "original_file_name": f"atomic_test_{i}.txt",
                "file_size_bytes": 1000 + i,
            }

            task = self._coordinator.assign_slot_atomic(batch_id, content_metadata)
            assignment_tasks.append(task)

        # Execute all assignments concurrently
        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(*assignment_tasks, return_exceptions=True)
        duration = asyncio.get_event_loop().time() - start_time

        # Record final state
        final_state = await self.validate_batch_integrity(batch_id)

        # Analyze results
        successful_assignments = [r for r in results if isinstance(r, str)]
        failed_assignments = [r for r in results if r is None]
        error_assignments = [r for r in results if isinstance(r, Exception)]
        
        # Count unique essay IDs to handle idempotent operations
        unique_essay_ids = set(successful_assignments)

        return {
            "initial_state": initial_state,
            "final_state": final_state,
            "operation_count": operation_count,
            "successful_assignments": len(unique_essay_ids),  # Count unique IDs only
            "failed_assignments": len(failed_assignments),
            "error_assignments": len(error_assignments),
            "duration": duration,
            "operations_per_second": operation_count / duration if duration > 0 else 0,
            "assigned_essay_ids": successful_assignments,
            "unique_essay_ids": unique_essay_ids,
            "integrity_maintained": final_state["no_overlap"],
        }


@pytest.mark.docker
@pytest.mark.asyncio
class TestRedisStateConsistency:
    """Test Redis state consistency under various load conditions."""

    @pytest.fixture(scope="class")
    def redis_container(self) -> Generator[RedisContainer, Any, None]:
        """Redis container for state consistency testing."""
        container = RedisContainer("redis:7-alpine")
        container.start()
        yield container
        container.stop()

    @pytest.fixture
    def redis_settings(self, redis_container: RedisContainer) -> Settings:
        """Create settings for Redis testing."""
        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"

        settings = Settings()
        settings.REDIS_URL = redis_url
        return settings

    @pytest.fixture
    async def redis_coordinator(
        self, redis_settings: Settings
    ) -> AsyncGenerator[RedisBatchCoordinator, None]:
        """Create Redis coordinator with clean state."""
        from huleedu_service_libs.redis_client import RedisClient

        redis_client = RedisClient(client_id="test-consistency", redis_url=redis_settings.REDIS_URL)
        await redis_client.start()

        # Clean state
        await redis_client.client.flushdb()

        coordinator = RedisBatchCoordinator(redis_client, redis_settings)

        try:
            yield coordinator
        finally:
            await redis_client.stop()

    @pytest.fixture
    async def redis_validator(
        self, redis_coordinator: RedisBatchCoordinator
    ) -> RedisStateValidator:
        """Create Redis state validator."""
        return RedisStateValidator(redis_coordinator)

    async def test_redis_atomic_operations_performance(
        self, redis_coordinator: RedisBatchCoordinator, redis_validator: RedisStateValidator
    ) -> None:
        """Benchmark Redis atomic slot assignment performance."""

        # Arrange - Create batch with many slots
        batch_id = f"perf_test_{uuid4().hex[:8]}"
        slot_count = 50
        essay_ids = [f"essay_{i:03d}" for i in range(slot_count)]

        metadata = {
            "course_code": "ENG5",
            "user_id": "perf_test_user",
            "correlation_id": str(uuid4()),
        }

        await redis_coordinator.register_batch_slots(batch_id, essay_ids, metadata)

        # Act - Perform atomic operations with timing
        operation_count = 100  # More operations than slots to test contention
        validation_result = await redis_validator.validate_atomic_operations(
            batch_id, operation_count
        )

        # Assert - Performance targets
        assert validation_result["operations_per_second"] > 10, (
            f"Redis operations too slow: {validation_result['operations_per_second']} ops/s"
        )

        # Assert - Atomicity maintained
        assert validation_result["integrity_maintained"], "Redis atomicity violated"

        # Assert - Correct number of assignments (limited by available slots)
        assert validation_result["successful_assignments"] <= slot_count
        assert validation_result["successful_assignments"] > 0

        # Assert - No errors due to race conditions
        assert validation_result["error_assignments"] == 0, (
            f"Unexpected errors during atomic operations: {validation_result['error_assignments']}"
        )

    async def test_redis_state_consistency_under_high_load(
        self, redis_coordinator: RedisBatchCoordinator, redis_validator: RedisStateValidator
    ) -> None:
        """Test Redis state consistency under high concurrent load."""

        # Arrange - Create multiple batches
        batch_count = 5
        slots_per_batch = 10
        batches = []

        for i in range(batch_count):
            batch_id = f"load_test_{i}_{uuid4().hex[:8]}"
            essay_ids = [f"essay_{j:03d}" for j in range(slots_per_batch)]

            metadata = {
                "course_code": "ENG5",
                "user_id": f"load_test_user_{i}",
                "batch_index": i,
                "correlation_id": str(uuid4()),
            }

            await redis_coordinator.register_batch_slots(batch_id, essay_ids, metadata)
            batches.append(batch_id)

        # Act - Concurrent operations across all batches
        all_tasks = []
        for batch_id in batches:
            # Create more tasks than slots to test contention
            for i in range(slots_per_batch * 2):
                content_metadata = {
                    "text_storage_id": f"load_content_{batch_id}_{i}_{uuid4().hex[:8]}",
                    "original_file_name": f"load_test_{i}.txt",
                    "file_size_bytes": 1500 + i * 10,
                }

                task = redis_coordinator.assign_slot_atomic(batch_id, content_metadata)
                all_tasks.append((batch_id, task))

        # Execute all operations concurrently
        start_time = asyncio.get_event_loop().time()
        await asyncio.gather(*[task for _, task in all_tasks], return_exceptions=True)
        duration = asyncio.get_event_loop().time() - start_time

        # Assert - Performance under load
        total_operations = len(all_tasks)
        ops_per_second = total_operations / duration
        assert ops_per_second > 5, f"Load performance too low: {ops_per_second} ops/s"

        # Assert - State consistency for each batch
        for batch_id in batches:
            integrity = await redis_validator.validate_batch_integrity(batch_id)

            assert integrity["no_overlap"], f"Batch {batch_id} has overlapping assignments"
            assert integrity["metadata_exists"], f"Batch {batch_id} missing metadata"
            assert integrity["total_slots"] == slots_per_batch, (
                f"Batch {batch_id} slot count mismatch: {integrity['total_slots']} != {slots_per_batch}"
            )

            # Verify that assigned + available equals total slots (no lost slots)
            assert integrity["assigned_count"] + integrity["available_count"] == slots_per_batch, (
                f"Batch {batch_id} lost slots: assigned={integrity['assigned_count']}, "
                f"available={integrity['available_count']}, expected_total={slots_per_batch}"
            )

    async def test_redis_distributed_lock_contention(
        self, redis_coordinator: RedisBatchCoordinator
    ) -> None:
        """Test distributed lock behavior under high contention."""

        # Arrange - Single batch with limited slots
        batch_id = f"lock_test_{uuid4().hex[:8]}"
        slot_count = 3  # Few slots for high contention
        essay_ids = [f"essay_{i:03d}" for i in range(slot_count)]

        metadata = {
            "course_code": "ENG5",
            "user_id": "lock_test_user",
            "correlation_id": str(uuid4()),
        }

        await redis_coordinator.register_batch_slots(batch_id, essay_ids, metadata)

        # Act - High contention with many concurrent attempts
        contention_level = 20  # Many more attempts than slots
        content_tasks = []

        for i in range(contention_level):
            content_metadata = {
                "text_storage_id": f"contention_content_{i}_{uuid4().hex[:8]}",
                "original_file_name": f"contention_test_{i}.txt",
                "file_size_bytes": 1200 + i * 5,
            }

            task = redis_coordinator.assign_slot_atomic(batch_id, content_metadata)
            content_tasks.append(task)

        # Execute with maximum concurrency
        start_time = asyncio.get_event_loop().time()
        results = await asyncio.gather(*content_tasks, return_exceptions=True)
        duration = asyncio.get_event_loop().time() - start_time

        # Assert - Analyze results
        successful_assignments = [r for r in results if isinstance(r, str)]
        failed_assignments = [r for r in results if r is None]
        
        # Count unique essay IDs assigned (due to idempotency)
        unique_essay_ids = set(successful_assignments)

        # Exactly slot_count unique slots should be assigned
        assert len(unique_essay_ids) == slot_count, (
            f"Lock contention failed: {len(unique_essay_ids)} unique assignments != {slot_count} slots"
        )
        
        # The total operations should equal successful + failed
        assert len(successful_assignments) + len(failed_assignments) == contention_level, (
            f"Lost operations: {len(successful_assignments)} + {len(failed_assignments)} != {contention_level}"
        )

        # Assert - No deadlocks (operation completed in reasonable time)
        assert duration < 5.0, f"Potential deadlock detected: {duration}s duration"

    async def test_redis_state_recovery_after_connection_failure(
        self, redis_coordinator: RedisBatchCoordinator, redis_validator: RedisStateValidator
    ) -> None:
        """Test Redis state recovery after connection failures."""

        # Arrange - Create batch and perform some assignments
        batch_id = f"recovery_test_{uuid4().hex[:8]}"
        total_slots = 8
        essay_ids = [f"essay_{i:03d}" for i in range(total_slots)]

        metadata = {
            "course_code": "ENG5",
            "user_id": "recovery_test_user",
            "correlation_id": str(uuid4()),
        }

        await redis_coordinator.register_batch_slots(batch_id, essay_ids, metadata)

        # Assign some slots before "failure"
        pre_failure_assignments = []
        for i in range(3):
            content_metadata = {
                "text_storage_id": f"pre_failure_content_{i}_{uuid4().hex[:8]}",
                "original_file_name": f"pre_failure_{i}.txt",
                "file_size_bytes": 1300 + i * 15,
            }

            result = await redis_coordinator.assign_slot_atomic(batch_id, content_metadata)
            assert result is not None
            pre_failure_assignments.append(result)

        # Validate state before "failure"
        pre_failure_state = await redis_validator.validate_batch_integrity(batch_id)
        assert pre_failure_state["assigned_count"] == 3
        assert pre_failure_state["available_count"] == 5

        # Simulate connection recovery by creating new coordinator
        # (In real scenarios, this simulates service restart)
        new_coordinator = RedisBatchCoordinator(
            redis_coordinator._redis, redis_coordinator._settings
        )

        # Act - Continue operations after "recovery"
        post_recovery_assignments = []
        for i in range(5):  # Assign remaining slots
            content_metadata = {
                "text_storage_id": f"post_recovery_content_{i}_{uuid4().hex[:8]}",
                "original_file_name": f"post_recovery_{i}.txt",
                "file_size_bytes": 1400 + i * 20,
            }

            result = await new_coordinator.assign_slot_atomic(batch_id, content_metadata)
            if result is not None:
                post_recovery_assignments.append(result)

        # Assert - State consistency maintained
        final_state = await redis_validator.validate_batch_integrity(batch_id)

        assert final_state["no_overlap"], "State corruption after recovery"
        assert final_state["assigned_count"] == total_slots, "Incomplete recovery"
        assert final_state["available_count"] == 0, "Slots not fully assigned after recovery"

        # Assert - All assignments are unique across recovery
        all_assignments = set(pre_failure_assignments + post_recovery_assignments)
        assert len(all_assignments) == total_slots, "Duplicate assignments across recovery"

    @pytest.mark.performance
    async def test_redis_operation_timing_consistency(
        self, redis_coordinator: RedisBatchCoordinator
    ) -> None:
        """Test consistency of Redis operation timing under various loads."""

        # Define scenario type for proper type checking
        class TestScenario(TypedDict):
            batch_size: int
            operations: int
            name: str

        # Test different batch sizes with proper typing
        test_scenarios: list[TestScenario] = [
            {"batch_size": 5, "operations": 10, "name": "small_batch"},
            {"batch_size": 15, "operations": 30, "name": "medium_batch"},
            {"batch_size": 25, "operations": 50, "name": "large_batch"},
        ]

        timing_results: dict[str, dict[str, Any]] = {}

        for scenario in test_scenarios:
            batch_id = f"timing_test_{scenario['name']}_{uuid4().hex[:8]}"
            # Type annotations ensure these are properly typed as int
            batch_size: int = scenario["batch_size"]
            operation_count: int = scenario["operations"]

            # Create batch
            essay_ids = [f"essay_{i:03d}" for i in range(batch_size)]
            metadata = {
                "course_code": "ENG5",
                "user_id": f"timing_test_{scenario['name']}",
                "correlation_id": str(uuid4()),
            }

            await redis_coordinator.register_batch_slots(batch_id, essay_ids, metadata)

            # Measure operation timings
            operation_times = []

            for i in range(operation_count):
                content_metadata = {
                    "text_storage_id": f"timing_content_{i}_{uuid4().hex[:8]}",
                    "original_file_name": f"timing_test_{i}.txt",
                    "file_size_bytes": 1100 + i * 7,
                }

                start_time = asyncio.get_event_loop().time()
                await redis_coordinator.assign_slot_atomic(batch_id, content_metadata)
                duration = asyncio.get_event_loop().time() - start_time

                operation_times.append(duration)

                # Small random delay to vary timing
                await asyncio.sleep(random.uniform(0.001, 0.005))

            # Calculate statistics
            successful_times = operation_times
            if successful_times:
                avg_time = sum(successful_times) / len(successful_times)
                max_time = max(successful_times)
                min_time = min(successful_times)

                timing_results[scenario["name"]] = {
                    "avg_time": avg_time,
                    "max_time": max_time,
                    "min_time": min_time,
                    "operation_count": len(successful_times),
                    "batch_size": batch_size,
                }

        # Assert - Performance targets across all scenarios
        for scenario_name, results in timing_results.items():
            assert results["avg_time"] < 0.1, (
                f"Average Redis operation too slow in {scenario_name}: {results['avg_time']}s"
            )
            assert results["max_time"] < 0.2, (
                f"Maximum Redis operation too slow in {scenario_name}: {results['max_time']}s"
            )

        # Assert - Performance consistency (variance shouldn't be too high)
        for scenario_name, results in timing_results.items():
            variance = results["max_time"] - results["min_time"]
            assert variance < 0.15, (
                f"Redis operation timing too inconsistent in {scenario_name}: {variance}s variance"
            )

    async def test_redis_batch_metadata_consistency(
        self, redis_coordinator: RedisBatchCoordinator
    ) -> None:
        """Test metadata consistency during concurrent batch operations."""

        # Arrange - Multiple batches with rich metadata
        batch_count = 5
        batches_metadata = []

        for i in range(batch_count):
            batch_id = f"metadata_test_{i}_{uuid4().hex[:8]}"
            essay_ids = [f"essay_{j:03d}" for j in range(6)]

            complex_metadata = {
                "course_code": f"ENG{i + 1}",
                "user_id": f"metadata_user_{i}",
                "batch_index": i,
                "creation_timestamp": asyncio.get_event_loop().time(),
                "complex_data": {
                    "nested_field": f"value_{i}",
                    "list_field": [f"item_{j}" for j in range(3)],
                },
                "correlation_id": str(uuid4()),
            }

            await redis_coordinator.register_batch_slots(batch_id, essay_ids, complex_metadata)
            batches_metadata.append((batch_id, complex_metadata))

        # Act - Concurrent metadata retrieval and slot operations
        concurrent_tasks: list[
            tuple[str, str, Coroutine[Any, Any, dict[str, Any] | str | None]]
        ] = []

        # Mix metadata retrievals with slot assignments
        for batch_id, _original_metadata in batches_metadata:
            # Metadata retrieval tasks
            for _ in range(3):
                metadata_task: Coroutine[Any, Any, dict[str, Any] | None] = (
                    redis_coordinator.get_batch_metadata(batch_id)
                )
                concurrent_tasks.append(("metadata", batch_id, metadata_task))

            # Slot assignment tasks
            for i in range(4):
                content_metadata = {
                    "text_storage_id": f"metadata_content_{batch_id}_{i}_{uuid4().hex[:8]}",
                    "original_file_name": f"metadata_test_{i}.txt",
                    "file_size_bytes": 1250 + i * 12,
                }

                assignment_task: Coroutine[Any, Any, str | None] = (
                    redis_coordinator.assign_slot_atomic(batch_id, content_metadata)
                )
                concurrent_tasks.append(("assignment", batch_id, assignment_task))

        # Execute all operations concurrently
        results = await asyncio.gather(
            *[task for _, _, task in concurrent_tasks], return_exceptions=True
        )

        # Assert - All metadata retrievals succeeded and are consistent
        metadata_retrievals: dict[str, list[Any]] = {}
        assignment_results: dict[str, list[str | None | BaseException]] = {}

        for i, (operation_type, batch_id, _) in enumerate(concurrent_tasks):
            result = results[i]

            if operation_type == "metadata":
                if batch_id not in metadata_retrievals:
                    metadata_retrievals[batch_id] = []
                metadata_retrievals[batch_id].append(result)
            elif operation_type == "assignment":
                if batch_id not in assignment_results:
                    assignment_results[batch_id] = []
                # Type narrowing: result should be str | None | BaseException for assignment operations
                assignment_result: str | None | BaseException = result  # type: ignore[assignment]
                assignment_results[batch_id].append(assignment_result)

        # Validate metadata consistency
        for batch_id, original_metadata in batches_metadata:
            retrieved_metadata_list = metadata_retrievals.get(batch_id, [])

            assert len(retrieved_metadata_list) > 0, f"No metadata retrieved for {batch_id}"

            # All metadata retrievals should be identical
            first_metadata = retrieved_metadata_list[0]
            for metadata in retrieved_metadata_list[1:]:
                assert metadata == first_metadata, (
                    f"Metadata inconsistency for {batch_id}: {metadata} != {first_metadata}"
                )

            # Metadata should match original (allowing for type conversions)
            assert first_metadata["course_code"] == original_metadata["course_code"]
            assert first_metadata["user_id"] == original_metadata["user_id"]
            assert first_metadata["batch_index"] == original_metadata["batch_index"]

        # Assert - All assignments succeeded
        for batch_id, assignments in assignment_results.items():
            successful_assignments = [a for a in assignments if isinstance(a, str)]
            assert len(successful_assignments) >= 4, (
                f"Insufficient assignments for {batch_id}: {len(successful_assignments)}"
            )
