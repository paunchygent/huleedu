"""
Consolidated test utilities for distributed Essay Lifecycle Service testing.

Provides shared MockEventPublisher, PerformanceMetrics, and Settings classes
to eliminate code duplication across distributed test files.

Follows Rule 070 testing patterns with proper resource cleanup and isolation.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any
from uuid import UUID

import psutil
from common_core.metadata_models import EntityReference
from common_core.status_enums import EssayStatus

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.protocols import EventPublisher


class MockEventPublisher(EventPublisher):
    """Mock event publisher that records published events for verification.

    Records full event data for detailed testing and validation.
    Thread-safe with async lock protection.
    """

    def __init__(self) -> None:
        self.published_events: list[tuple[str, Any, UUID | None]] = []
        self.lock = asyncio.Lock()

    async def publish_status_update(
        self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID
    ) -> None:
        """Record status update events."""
        async with self.lock:
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
        """Record batch phase progress events."""
        async with self.lock:
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
        """Record batch phase concluded events."""
        async with self.lock:
            self.published_events.append(
                (
                    "batch_phase_concluded",
                    {"batch_id": batch_id, "phase": phase, "status": status, "details": details},
                    correlation_id,
                )
            )

    async def publish_batch_essays_ready(self, event_data: Any, correlation_id: UUID) -> None:
        """Record batch essays ready events."""
        async with self.lock:
            self.published_events.append(("batch_essays_ready", event_data, correlation_id))

    async def publish_excess_content_provisioned(
        self, event_data: Any, correlation_id: UUID
    ) -> None:
        """Record excess content events."""
        async with self.lock:
            self.published_events.append(("excess_content_provisioned", event_data, correlation_id))

    async def publish_els_batch_phase_outcome(self, event_data: Any, correlation_id: UUID) -> None:
        """Record ELS batch phase outcome events."""
        async with self.lock:
            self.published_events.append(("els_batch_phase_outcome", event_data, correlation_id))

    async def publish_essay_slot_assigned(self, event_data: Any, correlation_id: UUID) -> None:
        """Record essay slot assigned events with validation."""
        async with self.lock:
            # Validate event data structure
            assert hasattr(event_data, "batch_id"), "EssaySlotAssignedV1 must have batch_id"
            assert hasattr(event_data, "essay_id"), "EssaySlotAssignedV1 must have essay_id"
            assert hasattr(event_data, "file_upload_id"), (
                "EssaySlotAssignedV1 must have file_upload_id"
            )
            assert hasattr(event_data, "text_storage_id"), (
                "EssaySlotAssignedV1 must have text_storage_id"
            )

            # Validate field values
            assert event_data.batch_id, "batch_id must not be empty"
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
    ) -> None:
        """Mock outbox publishing - records event for testing."""
        async with self.lock:
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


class PerformanceMetrics:
    """Comprehensive performance metrics collection and analysis.

    Tracks operation timings, memory usage, and throughput patterns
    for distributed system performance testing.
    """

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
        # Find baseline memory (when no essays are processed)
        baseline_memory = min(rss_values)  # Minimum memory is closest to baseline

        # For memory efficiency, only use "final" samples or samples after full processing
        # This avoids intermediate samples that show partial memory allocation
        relevant_samples = [
            s
            for s in self.memory_samples
            if "final" in s["context"] or "after_full_processing" in s["context"]
        ]

        memory_per_essay = []
        for sample in relevant_samples:
            if sample["total_essays"] > 0:
                # Calculate memory above baseline per essay
                memory_above_baseline = sample["rss_mb"] - baseline_memory
                memory_per_essay.append(memory_above_baseline / sample["total_essays"])

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


class DistributedTestSettings(Settings):
    """Configurable test settings for distributed infrastructure testing.

    Provides optimized database pool settings and configuration options
    suitable for both concurrent testing and performance evaluation.
    """

    def __init__(
        self,
        database_url: str,
        redis_url: str,
        pool_size: int = 20,
        max_overflow: int = 60,
        enable_optimizations: bool = True,
    ) -> None:
        """Initialize distributed test settings.

        Args:
            database_url: PostgreSQL connection URL
            redis_url: Redis connection URL
            pool_size: Base database connection pool size
            max_overflow: Maximum overflow connections
            enable_optimizations: Enable performance optimizations (pre_ping, recycle)
        """
        super().__init__()
        object.__setattr__(self, "_database_url", database_url)
        self.REDIS_URL = redis_url

        # Configurable pool settings for different test scenarios
        self.DATABASE_POOL_SIZE = pool_size
        self.DATABASE_MAX_OVERFLOW = max_overflow

        # Performance optimizations (can be disabled for basic tests)
        if enable_optimizations:
            self.DATABASE_POOL_PRE_PING = True
            self.DATABASE_POOL_RECYCLE = 1800

    @property
    def DATABASE_URL(self) -> str:
        """Get the database connection URL."""
        return str(object.__getattribute__(self, "_database_url"))

    @classmethod
    def create_basic_settings(cls, database_url: str, redis_url: str) -> DistributedTestSettings:
        """Create basic settings for simple concurrent testing."""
        return cls(
            database_url=database_url,
            redis_url=redis_url,
            pool_size=5,
            max_overflow=10,
            enable_optimizations=False,
        )

    @classmethod
    def create_performance_settings(
        cls, database_url: str, redis_url: str
    ) -> DistributedTestSettings:
        """Create optimized settings for performance testing."""
        return cls(
            database_url=database_url,
            redis_url=redis_url,
            pool_size=20,
            max_overflow=60,
            enable_optimizations=True,
        )
