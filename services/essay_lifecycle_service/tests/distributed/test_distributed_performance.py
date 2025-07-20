"""
Performance and load testing for distributed Essay Lifecycle Service.

Tests validate horizontal scaling benefits, memory usage independence from batch size,
and performance targets under realistic distributed workloads.

Follows Rule 070 performance testing patterns with real infrastructure.
"""

from __future__ import annotations

import asyncio
import gc
import statistics
import time
from collections.abc import AsyncGenerator, Generator
from typing import Any
from uuid import UUID, uuid4

import psutil
import pytest
from common_core.domain_enums import CourseCode
from common_core.status_enums import EssayStatus
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.file_events import EssayContentProvisionedV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
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
from services.essay_lifecycle_service.implementations.redis_batch_coordinator import (
    RedisBatchCoordinator,
)
from services.essay_lifecycle_service.protocols import EventPublisher


class PerformanceMetrics:
    """Comprehensive performance metrics collection and analysis."""

    def __init__(self) -> None:
        self.operation_timings: list[dict[str, Any]] = []
        self.memory_samples: list[dict[str, Any]] = []
        self.throughput_samples: list[dict[str, Any]] = []
        self.lock = asyncio.Lock()
        self.process = psutil.Process()

    async def record_operation(
        self,
        operation_type: str,
        duration: float,
        success: bool,
        instance_id: str | None = None,
        batch_size: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record individual operation timing."""
        async with self.lock:
            self.operation_timings.append(
                {
                    "operation_type": operation_type,
                    "duration": duration,
                    "success": success,
                    "instance_id": instance_id,
                    "batch_size": batch_size,
                    "timestamp": time.time(),
                    "details": details or {},
                }
            )

    async def sample_memory_usage(
        self, context: str, batch_count: int = 0, total_essays: int = 0
    ) -> None:
        """Sample current memory usage."""
        memory_info = self.process.memory_info()
        async with self.lock:
            self.memory_samples.append(
                {
                    "context": context,
                    "rss_mb": memory_info.rss / 1024 / 1024,
                    "vms_mb": memory_info.vms / 1024 / 1024,
                    "batch_count": batch_count,
                    "total_essays": total_essays,
                    "timestamp": time.time(),
                }
            )

    async def record_throughput(
        self,
        operation_type: str,
        operations_completed: int,
        duration: float,
        instance_count: int = 1,
    ) -> None:
        """Record throughput measurement."""
        async with self.lock:
            self.throughput_samples.append(
                {
                    "operation_type": operation_type,
                    "operations_completed": operations_completed,
                    "duration": duration,
                    "ops_per_second": operations_completed / duration if duration > 0 else 0,
                    "instance_count": instance_count,
                    "timestamp": time.time(),
                }
            )

    def get_operation_statistics(self, operation_type: str | None = None) -> dict[str, Any]:
        """Get comprehensive operation statistics."""
        operations = self.operation_timings
        if operation_type:
            operations = [op for op in operations if op["operation_type"] == operation_type]

        if not operations:
            return {"operation_count": 0}

        successful_ops = [op for op in operations if op["success"]]
        failed_ops = [op for op in operations if not op["success"]]

        if successful_ops:
            durations = [op["duration"] for op in successful_ops]
            durations.sort()

            return {
                "operation_count": len(operations),
                "success_count": len(successful_ops),
                "failure_count": len(failed_ops),
                "success_rate": len(successful_ops) / len(operations),
                "avg_duration": statistics.mean(durations),
                "median_duration": statistics.median(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "p95_duration": durations[int(0.95 * len(durations))]
                if len(durations) > 20
                else max(durations),
                "p99_duration": durations[int(0.99 * len(durations))]
                if len(durations) > 100
                else max(durations),
                "std_dev": statistics.stdev(durations) if len(durations) > 1 else 0,
            }
        else:
            return {
                "operation_count": len(operations),
                "success_count": 0,
                "failure_count": len(failed_ops),
                "success_rate": 0.0,
            }

    def get_memory_analysis(self) -> dict[str, Any]:
        """Analyze memory usage patterns."""
        if not self.memory_samples:
            return {"sample_count": 0}

        rss_values = [sample["rss_mb"] for sample in self.memory_samples]
        essay_counts = [sample["total_essays"] for sample in self.memory_samples]

        # Calculate memory efficiency
        memory_per_essay = []
        for sample in self.memory_samples:
            if sample["total_essays"] > 0:
                memory_per_essay.append(sample["rss_mb"] / sample["total_essays"])

        return {
            "sample_count": len(self.memory_samples),
            "min_memory_mb": min(rss_values),
            "max_memory_mb": max(rss_values),
            "avg_memory_mb": statistics.mean(rss_values),
            "memory_growth": max(rss_values) - min(rss_values),
            "max_essays_tracked": max(essay_counts) if essay_counts else 0,
            "avg_memory_per_essay": statistics.mean(memory_per_essay) if memory_per_essay else 0,
            "memory_efficiency_consistent": statistics.stdev(memory_per_essay) < 0.1
            if len(memory_per_essay) > 1
            else True,
        }

    def get_throughput_analysis(self) -> dict[str, Any]:
        """Analyze throughput patterns."""
        if not self.throughput_samples:
            return {"sample_count": 0}

        throughputs = [sample["ops_per_second"] for sample in self.throughput_samples]

        return {
            "sample_count": len(self.throughput_samples),
            "min_throughput": min(throughputs),
            "max_throughput": max(throughputs),
            "avg_throughput": statistics.mean(throughputs),
            "throughput_consistency": statistics.stdev(throughputs) if len(throughputs) > 1 else 0,
        }


class MockEventPublisher(EventPublisher):
    """Performance-optimized mock event publisher."""

    def __init__(self) -> None:
        self.event_count = 0
        self.lock = asyncio.Lock()

    async def publish_status_update(
        self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID
    ) -> None:
        async with self.lock:
            self.event_count += 1

    async def publish_batch_phase_progress(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
        total_essays_in_phase: int,
        correlation_id: UUID,
    ) -> None:
        async with self.lock:
            self.event_count += 1

    async def publish_batch_phase_concluded(
        self,
        batch_id: str,
        phase: str,
        status: str,
        details: dict[str, Any],
        correlation_id: UUID,
    ) -> None:
        async with self.lock:
            self.event_count += 1

    async def publish_batch_essays_ready(self, event_data: Any, correlation_id: UUID) -> None:
        async with self.lock:
            self.event_count += 1

    async def publish_excess_content_provisioned(self, event_data: Any, correlation_id: UUID) -> None:
        async with self.lock:
            self.event_count += 1

    async def publish_els_batch_phase_outcome(self, event_data: Any, correlation_id: UUID) -> None:
        async with self.lock:
            self.event_count += 1


@pytest.mark.performance
@pytest.mark.docker
@pytest.mark.asyncio
class TestDistributedPerformance:
    """Performance and load testing for distributed ELS coordination."""

    @pytest.fixture(scope="class")
    def postgres_container(self) -> Generator[PostgresContainer, Any, None]:
        """PostgreSQL for performance testing."""
        container = PostgresContainer("postgres:15")
        container.start()
        yield container
        container.stop()

    @pytest.fixture(scope="class")
    def redis_container(self) -> Generator[RedisContainer, Any, None]:
        """Redis for performance testing."""
        container = RedisContainer("redis:7-alpine")
        container.start()
        yield container
        container.stop()

    class PerformanceTestSettings(Settings):
        """Optimized settings for performance testing."""

        def __init__(self, database_url: str, redis_url: str) -> None:
            super().__init__()
            object.__setattr__(self, "_database_url", database_url)
            self.REDIS_URL = redis_url
            # Optimized for performance testing
            self.DATABASE_POOL_SIZE = 10
            self.DATABASE_MAX_OVERFLOW = 20
            self.DATABASE_POOL_PRE_PING = True
            self.DATABASE_POOL_RECYCLE = 1800

        @property
        def DATABASE_URL(self) -> str:
            return str(object.__getattribute__(self, "_database_url"))

    @pytest.fixture
    def performance_settings(
        self, postgres_container: PostgresContainer, redis_container: RedisContainer
    ) -> Settings:
        """Optimized settings for performance tests."""
        pg_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
        if "postgresql://" in pg_url:
            pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://")

        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"

        return self.PerformanceTestSettings(database_url=pg_url, redis_url=redis_url)

    @pytest.fixture
    async def performance_infrastructure(
        self, performance_settings: Settings
    ) -> AsyncGenerator[tuple[list[DefaultBatchCoordinationHandler], PerformanceMetrics], None]:
        """Create performance testing infrastructure with multiple instances."""

        # Clean infrastructure state
        from huleedu_service_libs.redis_client import RedisClient

        redis_client = RedisClient(
            client_id="perf-cleanup", redis_url=performance_settings.REDIS_URL
        )
        await redis_client.start()
        await redis_client.client.flushdb()
        await redis_client.stop()

        # Clean PostgreSQL
        repository = PostgreSQLEssayRepository(performance_settings)
        await repository.initialize_db_schema()

        async with repository.session() as session:
            from sqlalchemy import delete

            from services.essay_lifecycle_service.models_db import BatchEssayTracker, EssayStateDB

            await session.execute(delete(EssayStateDB))
            await session.execute(delete(BatchEssayTracker))
            await session.commit()

        # Create multiple instances for performance testing
        instances = []
        metrics = PerformanceMetrics()

        for instance_id in range(5):  # 5 instances for scaling tests
            redis_client = RedisClient(
                client_id=f"perf-instance-{instance_id}", redis_url=performance_settings.REDIS_URL
            )
            await redis_client.start()

            repo = PostgreSQLEssayRepository(performance_settings)
            redis_coordinator = RedisBatchCoordinator(redis_client, performance_settings)
            batch_tracker_persistence = BatchTrackerPersistence(repo.engine)
            batch_tracker = DefaultBatchEssayTracker(
                persistence=batch_tracker_persistence, redis_coordinator=redis_coordinator
            )

            event_publisher = MockEventPublisher()
            coordination_handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=repo,
                event_publisher=event_publisher,
            )

            instances.append(coordination_handler)

        try:
            # Initial memory baseline
            await metrics.sample_memory_usage("baseline", 0, 0)
            yield instances, metrics
        finally:
            # Cleanup Redis clients
            for handler in instances:
                try:
                    # Best effort cleanup
                    tracker = handler.batch_tracker
                    if hasattr(tracker, "_redis_coordinator") and hasattr(
                        tracker._redis_coordinator, "_redis"
                    ):
                        await tracker._redis_coordinator._redis.stop()
                except Exception:
                    pass

    async def test_horizontal_scaling_performance(
        self,
        performance_infrastructure: tuple[
            list[DefaultBatchCoordinationHandler], PerformanceMetrics
        ],
    ) -> None:
        """Test performance improvement with multiple instances."""

        handlers, metrics = performance_infrastructure

        # Test with different instance counts: 1, 3, 5
        scaling_results = {}

        for instance_count in [1, 3, 5]:
            test_handlers = handlers[:instance_count]
            batch_id = f"scaling_test_{instance_count}_{uuid4().hex[:8]}"
            essay_count = 20

            # Create batch
            batch_event = BatchEssaysRegistered(
                batch_id=batch_id,
                expected_essay_count=essay_count,
                essay_ids=[f"essay_{i:03d}" for i in range(essay_count)],
                course_code=CourseCode.ENG5,
                essay_instructions=f"Scaling test with {instance_count} instances",
                user_id="scaling_test_user",
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                    ),
                ),
            )

            # Register batch on first instance
            result = await test_handlers[0].handle_batch_essays_registered(batch_event, uuid4())
            assert result is True

            await asyncio.sleep(0.1)

            # Distribute content provisioning across instances
            content_tasks = []
            start_time = time.time()

            for i in range(essay_count):
                handler_idx = i % len(test_handlers)
                handler = test_handlers[handler_idx]

                content_event = EssayContentProvisionedV1(
                    batch_id=batch_id,
                    text_storage_id=f"scaling_content_{i}_{uuid4().hex[:8]}",
                    raw_file_storage_id=f"raw_essay_{i:03d}_{uuid4().hex[:8]}",
                    original_file_name=f"scaling_test_{i}.txt",
                    file_size_bytes=1000 + i * 10,
                    content_md5_hash=f"scaling_hash_{i}",
                )

                async def process_with_metrics(h: DefaultBatchCoordinationHandler, event: EssayContentProvisionedV1, iid: str) -> bool:
                    op_start = time.time()
                    try:
                        result = await h.handle_essay_content_provisioned(event, uuid4())
                        duration = time.time() - op_start
                        await metrics.record_operation(
                            "scaling_content_provision", duration, result, f"instance_{iid}"
                        )
                        return result
                    except Exception as e:
                        duration = time.time() - op_start
                        await metrics.record_operation(
                            "scaling_content_provision",
                            duration,
                            False,
                            f"instance_{iid}",
                            details={"error": str(e)},
                        )
                        raise

                task = process_with_metrics(handler, content_event, str(handler_idx))
                content_tasks.append(task)

            # Execute all operations
            results = await asyncio.gather(*content_tasks, return_exceptions=True)
            total_duration = time.time() - start_time

            # Record throughput
            successful_ops = len([r for r in results if r is True])
            await metrics.record_throughput(
                "batch_processing", successful_ops, total_duration, instance_count
            )

            scaling_results[instance_count] = {
                "total_duration": total_duration,
                "throughput": successful_ops / total_duration,
                "successful_operations": successful_ops,
                "instance_count": instance_count,
            }

            await metrics.sample_memory_usage(f"scaling_{instance_count}_instances", 1, essay_count)

        # Assert scaling benefits
        single_instance_throughput = scaling_results[1]["throughput"]
        three_instance_throughput = scaling_results[3]["throughput"]
        five_instance_throughput = scaling_results[5]["throughput"]

        # Should see performance improvement with more instances
        assert three_instance_throughput > single_instance_throughput * 1.5, (
            f"3 instances should be >1.5x faster: {three_instance_throughput} vs {single_instance_throughput}"
        )

        assert five_instance_throughput > single_instance_throughput * 2.0, (
            f"5 instances should be >2x faster: {five_instance_throughput} vs {single_instance_throughput}"
        )

        # Performance targets
        assert five_instance_throughput > 50, (
            f"5-instance throughput too low: {five_instance_throughput} ops/s"
        )

    async def test_memory_usage_independence(
        self,
        performance_infrastructure: tuple[
            list[DefaultBatchCoordinationHandler], PerformanceMetrics
        ],
    ) -> None:
        """Test memory usage remains constant regardless of batch size."""

        handlers, metrics = performance_infrastructure
        handler = handlers[0]  # Use single instance for memory testing

        # Test different batch sizes
        batch_sizes = [10, 50, 100, 200]

        for batch_size in batch_sizes:
            # Force garbage collection before each test
            gc.collect()
            await asyncio.sleep(0.1)

            batch_id = f"memory_test_{batch_size}_{uuid4().hex[:8]}"
            essay_ids = [f"essay_{i:03d}" for i in range(batch_size)]

            # Sample memory before batch creation
            await metrics.sample_memory_usage(f"before_batch_{batch_size}", 0, 0)

            # Create batch
            batch_event = BatchEssaysRegistered(
                batch_id=batch_id,
                expected_essay_count=batch_size,
                essay_ids=essay_ids,
                course_code=CourseCode.ENG5,
                essay_instructions=f"Memory test with {batch_size} essays",
                user_id="memory_test_user",
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                    ),
                ),
            )

            result = await handler.handle_batch_essays_registered(batch_event, uuid4())
            assert result is True

            # Sample memory after batch creation
            await metrics.sample_memory_usage(f"after_batch_creation_{batch_size}", 1, batch_size)

            # Process all essays for this batch
            for i in range(batch_size):
                content_event = EssayContentProvisionedV1(
                    batch_id=batch_id,
                    text_storage_id=f"memory_content_{i}_{uuid4().hex[:8]}",
                    raw_file_storage_id=f"raw_essay_{i:03d}_{uuid4().hex[:8]}",
                    original_file_name=f"memory_test_{i}.txt",
                    file_size_bytes=1200,
                    content_md5_hash=f"memory_hash_{i}",
                )

                await handler.handle_essay_content_provisioned(content_event, uuid4())

            # Sample memory after full batch processing
            await metrics.sample_memory_usage(f"after_full_processing_{batch_size}", 1, batch_size)

            # Small delay for memory stabilization
            await asyncio.sleep(0.5)

            # Sample final memory usage for this batch size
            await metrics.sample_memory_usage(f"final_{batch_size}", 1, batch_size)

        # Analyze memory independence
        memory_analysis = metrics.get_memory_analysis()

        # Memory growth should be minimal regardless of batch size
        max_memory_growth = memory_analysis["memory_growth"]
        assert max_memory_growth < 50, f"Memory growth too high: {max_memory_growth} MB"

        # Memory per essay should be consistent (Redis-based coordination should scale)
        assert memory_analysis["memory_efficiency_consistent"], (
            "Memory usage per essay not consistent across batch sizes"
        )

    async def test_performance_targets(
        self,
        performance_infrastructure: tuple[
            list[DefaultBatchCoordinationHandler], PerformanceMetrics
        ],
    ) -> None:
        """Validate performance targets are met."""

        handlers, metrics = performance_infrastructure

        # Test comprehensive workload
        batch_count = 5
        essays_per_batch = 15
        total_essays = batch_count * essays_per_batch

        # Create multiple batches
        batch_creation_tasks = []
        for i in range(batch_count):
            batch_id = f"perf_target_{i}_{uuid4().hex[:8]}"
            essay_ids = [f"essay_{j:03d}" for j in range(essays_per_batch)]

            batch_event = BatchEssaysRegistered(
                batch_id=batch_id,
                expected_essay_count=essays_per_batch,
                essay_ids=essay_ids,
                course_code=CourseCode.ENG5,
                essay_instructions=f"Performance target test batch {i}",
                user_id="perf_target_user",
                metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_id,
                        entity_type="batch",
                        parent_id=None,
                    ),
                ),
            )

            # Rotate through handlers
            handler = handlers[i % len(handlers)]
            task = handler.handle_batch_essays_registered(batch_event, uuid4())
            batch_creation_tasks.append((batch_id, task))

        # Create all batches
        batch_ids = []
        for batch_id, task in batch_creation_tasks:
            result = await task
            assert result is True
            batch_ids.append(batch_id)

        await asyncio.sleep(0.2)

        # Process content for all batches with comprehensive timing
        all_content_tasks = []

        for batch_idx, batch_id in enumerate(batch_ids):
            for essay_idx in range(essays_per_batch):
                handler = handlers[(batch_idx * essays_per_batch + essay_idx) % len(handlers)]

                content_event = EssayContentProvisionedV1(
                    batch_id=batch_id,
                    text_storage_id=f"target_content_{batch_idx}_{essay_idx}_{uuid4().hex[:8]}",
                    raw_file_storage_id=f"raw_essay_{essay_idx:03d}_{uuid4().hex[:8]}",
                    original_file_name=f"target_test_{batch_idx}_{essay_idx}.txt",
                    file_size_bytes=1100 + essay_idx * 5,
                    content_md5_hash=f"target_hash_{batch_idx}_{essay_idx}",
                )

                async def timed_content_processing(h: DefaultBatchCoordinationHandler, event: EssayContentProvisionedV1) -> bool:
                    start_time = time.time()
                    try:
                        result = await h.handle_essay_content_provisioned(event, uuid4())
                        duration = time.time() - start_time
                        await metrics.record_operation("performance_target", duration, result)
                        return result
                    except Exception as e:
                        duration = time.time() - start_time
                        await metrics.record_operation(
                            "performance_target", duration, False, details={"error": str(e)}
                        )
                        raise

                task = timed_content_processing(handler, content_event)
                all_content_tasks.append(task)

        # Execute all content operations
        overall_start = time.time()
        results = await asyncio.gather(*all_content_tasks, return_exceptions=True)
        overall_duration = time.time() - overall_start

        # Record overall throughput
        successful_operations = len([r for r in results if r is True])
        await metrics.record_throughput(
            "overall_performance", successful_operations, overall_duration, len(handlers)
        )

        # Validate performance targets
        operation_stats = metrics.get_operation_statistics("performance_target")
        throughput_stats = metrics.get_throughput_analysis()

        # Target: Redis operations < 0.1s
        assert operation_stats["p95_duration"] < 0.1, (
            f"P95 Redis operation duration too high: {operation_stats['p95_duration']}s"
        )

        # Target: Database operations < 0.2s
        assert operation_stats["avg_duration"] < 0.2, (
            f"Average database operation duration too high: {operation_stats['avg_duration']}s"
        )

        # Target: Batch coordination < 1s (overall per-operation average)
        assert operation_stats["max_duration"] < 1.0, (
            f"Maximum operation duration too high: {operation_stats['max_duration']}s"
        )

        # Target: High success rate
        assert operation_stats["success_rate"] > 0.95, (
            f"Success rate too low: {operation_stats['success_rate']}"
        )

        # Target: Good overall throughput with multiple instances
        assert throughput_stats["avg_throughput"] > 30, (
            f"Overall throughput too low: {throughput_stats['avg_throughput']} ops/s"
        )

    async def test_sustained_load_endurance(
        self,
        performance_infrastructure: tuple[
            list[DefaultBatchCoordinationHandler], PerformanceMetrics
        ],
    ) -> None:
        """Test performance under sustained load over time."""

        handlers, metrics = performance_infrastructure

        # Run sustained load for a reasonable test duration
        test_duration = 30  # 30 seconds of sustained load
        operation_interval = 0.1  # 100ms between operations

        batch_id = f"endurance_test_{uuid4().hex[:8]}"
        essay_count = 100  # Large batch for endurance testing

        # Create large batch
        batch_event = BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=essay_count,
            essay_ids=[f"essay_{i:03d}" for i in range(essay_count)],
            course_code=CourseCode.ENG5,
            essay_instructions="Endurance test",
            user_id="endurance_test_user",
            metadata=SystemProcessingMetadata(
                entity=EntityReference(
                    entity_id=batch_id,
                    entity_type="batch",
                    parent_id=None,
                ),
            ),
        )

        result = await handlers[0].handle_batch_essays_registered(batch_event, uuid4())
        assert result is True

        await asyncio.sleep(0.2)

        # Sustained load processing
        start_time = time.time()
        operation_count = 0

        while time.time() - start_time < test_duration and operation_count < essay_count:
            handler = handlers[operation_count % len(handlers)]

            content_event = EssayContentProvisionedV1(
                batch_id=batch_id,
                text_storage_id=f"endurance_content_{operation_count}_{uuid4().hex[:8]}",
                raw_file_storage_id=f"raw_essay_{operation_count:03d}_{uuid4().hex[:8]}",
                original_file_name=f"endurance_test_{operation_count}.txt",
                file_size_bytes=1300 + operation_count * 3,
                content_md5_hash=f"endurance_hash_{operation_count}",
            )

            op_start = time.time()
            try:
                op_result = await handler.handle_essay_content_provisioned(content_event, uuid4())
                duration = time.time() - op_start
                await metrics.record_operation("endurance_test", duration, op_result)
            except Exception as e:
                duration = time.time() - op_start
                await metrics.record_operation(
                    "endurance_test", duration, False, details={"error": str(e)}
                )

            operation_count += 1

            # Sample memory periodically
            if operation_count % 20 == 0:
                await metrics.sample_memory_usage(
                    f"endurance_op_{operation_count}", 1, operation_count
                )

            # Maintain operation interval
            await asyncio.sleep(operation_interval)

        total_duration = time.time() - start_time
        await metrics.record_throughput(
            "endurance_overall", operation_count, total_duration, len(handlers)
        )

        # Analyze endurance performance
        endurance_stats = metrics.get_operation_statistics("endurance_test")
        memory_analysis = metrics.get_memory_analysis()

        # Performance should remain consistent over time
        assert endurance_stats["success_rate"] > 0.90, (
            f"Endurance success rate degraded: {endurance_stats['success_rate']}"
        )

        # No significant performance degradation
        assert endurance_stats["p95_duration"] < 0.15, (
            f"P95 duration degraded during endurance test: {endurance_stats['p95_duration']}s"
        )

        # Memory should remain stable
        assert memory_analysis["memory_growth"] < 100, (
            f"Memory growth during endurance test: {memory_analysis['memory_growth']} MB"
        )

        # Sustained throughput
        throughput_stats = metrics.get_throughput_analysis()
        assert throughput_stats["avg_throughput"] > 5, (
            f"Sustained throughput too low: {throughput_stats['avg_throughput']} ops/s"
        )
