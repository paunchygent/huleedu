"""
Distributed test fixtures and infrastructure utilities for Essay Lifecycle Service.

Provides comprehensive testing infrastructure for multi-instance coordination,
Docker Compose orchestration, and performance measurement utilities.

Follows Rule 070 testing patterns with proper resource cleanup and isolation.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from typing import Any

import pytest
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
from testcontainers.compose import DockerCompose
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


class DistributedTestMetrics:
    """Comprehensive metrics collection for distributed testing."""

    def __init__(self) -> None:
        self.operation_timings: list[dict[str, Any]] = []
        self.coordination_events: list[dict[str, Any]] = []
        self.redis_operations: list[dict[str, Any]] = []
        self.database_operations: list[dict[str, Any]] = []
        self.lock = asyncio.Lock()

    async def record_coordination_event(
        self,
        event_type: str,
        instance_id: str,
        batch_id: str,
        essay_id: str | None = None,
        success: bool = True,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record distributed coordination events."""
        async with self.lock:
            self.coordination_events.append({
                "event_type": event_type,
                "instance_id": instance_id,
                "batch_id": batch_id,
                "essay_id": essay_id,
                "success": success,
                "timestamp": time.time(),
                "details": details or {},
            })

    async def record_redis_operation(
        self,
        operation: str,
        duration: float,
        success: bool,
        key_type: str | None = None,
        instance_id: str | None = None,
    ) -> None:
        """Record Redis operation performance."""
        async with self.lock:
            self.redis_operations.append({
                "operation": operation,
                "duration": duration,
                "success": success,
                "key_type": key_type,
                "instance_id": instance_id,
                "timestamp": time.time(),
            })

    async def record_database_operation(
        self,
        operation: str,
        duration: float,
        success: bool,
        table: str | None = None,
        instance_id: str | None = None,
    ) -> None:
        """Record database operation performance."""
        async with self.lock:
            self.database_operations.append({
                "operation": operation,
                "duration": duration,
                "success": success,
                "table": table,
                "instance_id": instance_id,
                "timestamp": time.time(),
            })

    def get_coordination_analysis(self) -> dict[str, Any]:
        """Analyze coordination event patterns."""
        if not self.coordination_events:
            return {"event_count": 0}

        # Group by event type
        by_event_type = {}
        for event in self.coordination_events:
            event_type = event["event_type"]
            if event_type not in by_event_type:
                by_event_type[event_type] = []
            by_event_type[event_type].append(event)

        # Group by instance
        by_instance = {}
        for event in self.coordination_events:
            instance_id = event["instance_id"]
            if instance_id not in by_instance:
                by_instance[instance_id] = []
            by_instance[instance_id].append(event)

        return {
            "total_events": len(self.coordination_events),
            "event_types": list(by_event_type.keys()),
            "instance_distribution": {k: len(v) for k, v in by_instance.items()},
            "success_rate": len([e for e in self.coordination_events if e["success"]]) / len(self.coordination_events),
            "events_by_type": {k: len(v) for k, v in by_event_type.items()},
        }

    def get_redis_performance_analysis(self) -> dict[str, Any]:
        """Analyze Redis operation performance."""
        if not self.redis_operations:
            return {"operation_count": 0}

        successful_ops = [op for op in self.redis_operations if op["success"]]
        durations = [op["duration"] for op in successful_ops]

        if durations:
            durations.sort()
            return {
                "operation_count": len(self.redis_operations),
                "success_count": len(successful_ops),
                "success_rate": len(successful_ops) / len(self.redis_operations),
                "avg_duration": sum(durations) / len(durations),
                "p95_duration": durations[int(0.95 * len(durations))] if len(durations) > 20 else max(durations),
                "max_duration": max(durations),
                "min_duration": min(durations),
            }
        else:
            return {
                "operation_count": len(self.redis_operations),
                "success_count": 0,
                "success_rate": 0.0,
            }

    def get_database_performance_analysis(self) -> dict[str, Any]:
        """Analyze database operation performance."""
        if not self.database_operations:
            return {"operation_count": 0}

        successful_ops = [op for op in self.database_operations if op["success"]]
        durations = [op["duration"] for op in successful_ops]

        if durations:
            durations.sort()
            return {
                "operation_count": len(self.database_operations),
                "success_count": len(successful_ops),
                "success_rate": len(successful_ops) / len(self.database_operations),
                "avg_duration": sum(durations) / len(durations),
                "p95_duration": durations[int(0.95 * len(durations))] if len(durations) > 20 else max(durations),
                "max_duration": max(durations),
                "min_duration": min(durations),
            }
        else:
            return {
                "operation_count": len(self.database_operations),
                "success_count": 0,
                "success_rate": 0.0,
            }


class DistributedTestEventPublisher(EventPublisher):
    """Event publisher that records events for distributed testing analysis."""

    def __init__(self, instance_id: str, metrics: DistributedTestMetrics) -> None:
        self.instance_id = instance_id
        self.metrics = metrics
        self.published_events: list[tuple[str, Any, Any]] = []
        self.lock = asyncio.Lock()

    async def publish_status_update(self, essay_ref, status, correlation_id) -> None:
        """Record status update events."""
        async with self.lock:
            self.published_events.append(("status_update", (essay_ref, status), correlation_id))
        
        await self.metrics.record_coordination_event(
            "status_update", self.instance_id, essay_ref.parent_id or "unknown", essay_ref.entity_id
        )

    async def publish_batch_phase_progress(self, batch_id, phase, completed_count, failed_count, total_essays_in_phase, correlation_id) -> None:
        """Record batch phase progress events."""
        async with self.lock:
            self.published_events.append(
                ("batch_phase_progress", {
                    "batch_id": batch_id,
                    "phase": phase,
                    "completed_count": completed_count,
                    "failed_count": failed_count,
                    "total_essays_in_phase": total_essays_in_phase,
                }, correlation_id)
            )
        
        await self.metrics.record_coordination_event(
            "batch_phase_progress", self.instance_id, batch_id,
            details={"phase": phase, "completed": completed_count, "failed": failed_count}
        )

    async def publish_batch_phase_concluded(self, batch_id, phase, status, details, correlation_id) -> None:
        """Record batch phase concluded events."""
        async with self.lock:
            self.published_events.append(
                ("batch_phase_concluded", {
                    "batch_id": batch_id, 
                    "phase": phase, 
                    "status": status, 
                    "details": details
                }, correlation_id)
            )
        
        await self.metrics.record_coordination_event(
            "batch_phase_concluded", self.instance_id, batch_id,
            details={"phase": phase, "status": status}
        )

    async def publish_batch_essays_ready(self, event_data, correlation_id) -> None:
        """Record batch essays ready events."""
        async with self.lock:
            self.published_events.append(("batch_essays_ready", event_data, correlation_id))
        
        await self.metrics.record_coordination_event(
            "batch_essays_ready", self.instance_id, event_data.batch_id
        )

    async def publish_excess_content_provisioned(self, event_data, correlation_id) -> None:
        """Record excess content events."""
        async with self.lock:
            self.published_events.append(("excess_content_provisioned", event_data, correlation_id))
        
        await self.metrics.record_coordination_event(
            "excess_content_provisioned", self.instance_id, event_data.batch_id
        )

    async def publish_els_batch_phase_outcome(self, event_data, correlation_id) -> None:
        """Record ELS batch phase outcome events."""
        async with self.lock:
            self.published_events.append(("els_batch_phase_outcome", event_data, correlation_id))
        
        await self.metrics.record_coordination_event(
            "els_batch_phase_outcome", self.instance_id, event_data.batch_id
        )


class DistributedTestOrchestrator:
    """Orchestrates Docker Compose-based distributed testing infrastructure."""

    def __init__(self, compose_file_path: str) -> None:
        self.compose_file_path = compose_file_path
        self.compose: DockerCompose | None = None

    async def start_infrastructure(self) -> dict[str, Any]:
        """Start distributed testing infrastructure."""
        compose_dir = os.path.dirname(self.compose_file_path)
        compose_file = os.path.basename(self.compose_file_path)
        
        self.compose = DockerCompose(compose_dir, compose_file)
        self.compose.start()
        
        # Wait for services to be ready
        await self._wait_for_services()
        
        return {
            "postgres_url": self._get_postgres_url(),
            "redis_url": self._get_redis_url(),
            "kafka_url": self._get_kafka_url(),
            "els_workers": self._get_els_worker_urls(),
        }

    async def stop_infrastructure(self) -> None:
        """Stop and clean up infrastructure."""
        if self.compose:
            self.compose.stop()

    def _get_postgres_url(self) -> str:
        """Get PostgreSQL connection URL."""
        postgres_host = self.compose.get_service_host("postgres", 5432)
        postgres_port = self.compose.get_service_port("postgres", 5432)
        return f"postgresql+asyncpg://testuser:testpass@{postgres_host}:{postgres_port}/els_distributed_test"

    def _get_redis_url(self) -> str:
        """Get Redis connection URL."""
        redis_host = self.compose.get_service_host("redis", 6379)
        redis_port = self.compose.get_service_port("redis", 6379)
        return f"redis://{redis_host}:{redis_port}"

    def _get_kafka_url(self) -> str:
        """Get Kafka connection URL."""
        kafka_host = self.compose.get_service_host("kafka", 9092)
        kafka_port = self.compose.get_service_port("kafka", 9092)
        return f"{kafka_host}:{kafka_port}"

    def _get_els_worker_urls(self) -> list[str]:
        """Get ELS worker URLs."""
        workers = []
        for i in range(1, 4):  # 3 workers
            worker_host = self.compose.get_service_host(f"els_worker_{i}", 6000)
            worker_port = self.compose.get_service_port(f"els_worker_{i}", 6000)
            workers.append(f"http://{worker_host}:{worker_port}")
        return workers

    async def _wait_for_services(self, timeout: int = 120) -> None:
        """Wait for all services to be ready."""
        import httpx
        
        start_time = time.time()
        
        # Services to check
        service_checks = [
            ("postgres", lambda: self._check_postgres()),
            ("redis", lambda: self._check_redis()),
            ("kafka", lambda: self._check_kafka()),
        ]
        
        while time.time() - start_time < timeout:
            all_ready = True
            
            for service_name, check_func in service_checks:
                try:
                    if not await check_func():
                        all_ready = False
                        break
                except Exception:
                    all_ready = False
                    break
            
            if all_ready:
                return
            
            await asyncio.sleep(2)
        
        raise TimeoutError("Services did not become ready within timeout")

    async def _check_postgres(self) -> bool:
        """Check PostgreSQL readiness."""
        try:
            import asyncpg
            conn = await asyncpg.connect(self._get_postgres_url())
            await conn.execute("SELECT 1")
            await conn.close()
            return True
        except Exception:
            return False

    async def _check_redis(self) -> bool:
        """Check Redis readiness."""
        try:
            from huleedu_service_libs.redis_client import RedisClient
            client = RedisClient(client_id="health-check", redis_url=self._get_redis_url())
            await client.start()
            await client.client.ping()
            await client.stop()
            return True
        except Exception:
            return False

    async def _check_kafka(self) -> bool:
        """Check Kafka readiness."""
        try:
            # Simple socket connection check
            import socket
            kafka_url = self._get_kafka_url()
            host, port = kafka_url.split(":")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex((host, int(port)))
            sock.close()
            return result == 0
        except Exception:
            return False


# Pytest Fixtures

@pytest.fixture(scope="session")
def distributed_test_metrics() -> DistributedTestMetrics:
    """Provide metrics collection for distributed tests."""
    return DistributedTestMetrics()


@pytest.fixture(scope="class") 
def docker_compose_infrastructure() -> Generator[DistributedTestOrchestrator, Any, None]:
    """Start Docker Compose infrastructure for distributed testing."""
    compose_file = os.path.join(os.path.dirname(__file__), "docker-compose.distributed-test.yml")
    orchestrator = DistributedTestOrchestrator(compose_file)
    
    # Note: This is a placeholder - real Docker Compose integration would need
    # proper async handling in pytest fixtures
    yield orchestrator


@pytest.fixture
async def distributed_infrastructure(
    distributed_test_metrics: DistributedTestMetrics,
) -> AsyncGenerator[dict[str, Any], None]:
    """Setup distributed testing infrastructure with testcontainers."""
    
    # Use testcontainers for reliable distributed testing
    postgres_container = PostgresContainer("postgres:15")
    redis_container = RedisContainer("redis:7-alpine")
    
    postgres_container.start()
    redis_container.start()
    
    try:
        # Get connection details
        pg_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
        if "postgresql://" in pg_url:
            pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://")
        
        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
        
        # Clean state
        from huleedu_service_libs.redis_client import RedisClient
        redis_client = RedisClient(client_id="test-setup", redis_url=redis_url)
        await redis_client.start()
        await redis_client.client.flushdb()
        await redis_client.stop()
        
        # Setup PostgreSQL
        class DistributedTestSettings(Settings):
            def __init__(self, database_url: str, redis_url: str) -> None:
                super().__init__()
                object.__setattr__(self, "_database_url", database_url)
                self.REDIS_URL = redis_url
                self.DATABASE_POOL_SIZE = 8
                self.DATABASE_MAX_OVERFLOW = 15

            @property
            def DATABASE_URL(self) -> str:
                return str(object.__getattribute__(self, "_database_url"))
        
        settings = DistributedTestSettings(database_url=pg_url, redis_url=redis_url)
        
        # Initialize database schema
        repository = PostgreSQLEssayRepository(settings)
        await repository.initialize_db_schema()
        
        # Clean existing data
        async with repository.session() as session:
            from services.essay_lifecycle_service.models_db import BatchEssayTracker, EssayStateDB
            from sqlalchemy import delete
            
            await session.execute(delete(EssayStateDB))
            await session.execute(delete(BatchEssayTracker))
            await session.commit()
        
        yield {
            "settings": settings,
            "postgres_url": pg_url,
            "redis_url": redis_url,
            "metrics": distributed_test_metrics,
        }
        
    finally:
        postgres_container.stop()
        redis_container.stop()


@pytest.fixture
async def distributed_coordinator_instances(
    distributed_infrastructure: dict[str, Any],
) -> AsyncGenerator[list[DefaultBatchCoordinationHandler], None]:
    """Create multiple coordinator instances for distributed testing."""
    
    infrastructure = distributed_infrastructure
    settings = infrastructure["settings"]
    metrics = infrastructure["metrics"]
    
    instances = []
    redis_clients = []
    
    try:
        # Create multiple instances
        for instance_id in range(3):
            from huleedu_service_libs.redis_client import RedisClient
            
            redis_client = RedisClient(
                client_id=f"test-instance-{instance_id}",
                redis_url=settings.REDIS_URL
            )
            await redis_client.start()
            redis_clients.append(redis_client)
            
            # Repository (shared database)
            repository = PostgreSQLEssayRepository(settings)
            
            # Redis coordinator
            redis_coordinator = RedisBatchCoordinator(redis_client, settings)
            
            # Batch tracker
            batch_tracker_persistence = BatchTrackerPersistence(repository.engine)
            batch_tracker = DefaultBatchEssayTracker(
                persistence=batch_tracker_persistence,
                redis_coordinator=redis_coordinator
            )
            
            # Event publisher with metrics
            event_publisher = DistributedTestEventPublisher(f"instance_{instance_id}", metrics)
            
            # Coordination handler
            coordination_handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=repository,
                event_publisher=event_publisher,
            )
            
            instances.append(coordination_handler)
        
        yield instances
        
    finally:
        # Cleanup Redis clients
        for client in redis_clients:
            try:
                await client.stop()
            except Exception:
                pass  # Best effort cleanup


@asynccontextmanager
async def distributed_test_context(
    instance_count: int = 3,
    clean_state: bool = True,
) -> AsyncGenerator[tuple[list[DefaultBatchCoordinationHandler], DistributedTestMetrics], None]:
    """Context manager for distributed testing with configurable instances."""
    
    # Create containers
    postgres_container = PostgresContainer("postgres:15")
    redis_container = RedisContainer("redis:7-alpine")
    
    postgres_container.start()
    redis_container.start()
    
    try:
        # Setup infrastructure
        pg_url = postgres_container.get_connection_url().replace("psycopg2", "asyncpg")
        if "postgresql://" in pg_url:
            pg_url = pg_url.replace("postgresql://", "postgresql+asyncpg://")
        
        redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}"
        
        # Settings
        class TestSettings(Settings):
            def __init__(self, database_url: str, redis_url: str) -> None:
                super().__init__()
                object.__setattr__(self, "_database_url", database_url)
                self.REDIS_URL = redis_url
                self.DATABASE_POOL_SIZE = max(instance_count * 2, 5)
                self.DATABASE_MAX_OVERFLOW = max(instance_count * 3, 10)

            @property
            def DATABASE_URL(self) -> str:
                return str(object.__getattribute__(self, "_database_url"))
        
        settings = TestSettings(database_url=pg_url, redis_url=redis_url)
        metrics = DistributedTestMetrics()
        
        # Clean state if requested
        if clean_state:
            from huleedu_service_libs.redis_client import RedisClient
            redis_client = RedisClient(client_id="context-cleanup", redis_url=redis_url)
            await redis_client.start()
            await redis_client.client.flushdb()
            await redis_client.stop()
            
            repository = PostgreSQLEssayRepository(settings)
            await repository.initialize_db_schema()
            
            async with repository.session() as session:
                from services.essay_lifecycle_service.models_db import BatchEssayTracker, EssayStateDB
                from sqlalchemy import delete
                
                await session.execute(delete(EssayStateDB))
                await session.execute(delete(BatchEssayTracker))
                await session.commit()
        
        # Create instances
        instances = []
        redis_clients = []
        
        for instance_id in range(instance_count):
            from huleedu_service_libs.redis_client import RedisClient
            
            redis_client = RedisClient(
                client_id=f"context-instance-{instance_id}",
                redis_url=settings.REDIS_URL
            )
            await redis_client.start()
            redis_clients.append(redis_client)
            
            repository = PostgreSQLEssayRepository(settings)
            redis_coordinator = RedisBatchCoordinator(redis_client, settings)
            batch_tracker_persistence = BatchTrackerPersistence(repository.engine)
            batch_tracker = DefaultBatchEssayTracker(
                persistence=batch_tracker_persistence,
                redis_coordinator=redis_coordinator
            )
            
            event_publisher = DistributedTestEventPublisher(f"context_instance_{instance_id}", metrics)
            coordination_handler = DefaultBatchCoordinationHandler(
                batch_tracker=batch_tracker,
                repository=repository,
                event_publisher=event_publisher,
            )
            
            instances.append(coordination_handler)
        
        yield instances, metrics
        
        # Cleanup
        for client in redis_clients:
            try:
                await client.stop()
            except Exception:
                pass
        
    finally:
        postgres_container.stop()
        redis_container.stop()


# Performance measurement utilities

def assert_performance_targets(
    metrics: DistributedTestMetrics,
    redis_target: float = 0.1,
    database_target: float = 0.2,
    success_rate_target: float = 0.95,
) -> None:
    """Assert that performance targets are met."""
    
    redis_stats = metrics.get_redis_performance_analysis()
    db_stats = metrics.get_database_performance_analysis()
    
    if redis_stats["operation_count"] > 0:
        assert redis_stats["p95_duration"] < redis_target, (
            f"Redis P95 duration too high: {redis_stats['p95_duration']}s > {redis_target}s"
        )
        assert redis_stats["success_rate"] >= success_rate_target, (
            f"Redis success rate too low: {redis_stats['success_rate']} < {success_rate_target}"
        )
    
    if db_stats["operation_count"] > 0:
        assert db_stats["p95_duration"] < database_target, (
            f"Database P95 duration too high: {db_stats['p95_duration']}s > {database_target}s"
        )
        assert db_stats["success_rate"] >= success_rate_target, (
            f"Database success rate too low: {db_stats['success_rate']} < {success_rate_target}"
        )


def assert_coordination_integrity(metrics: DistributedTestMetrics) -> None:
    """Assert distributed coordination integrity."""
    
    coordination_stats = metrics.get_coordination_analysis()
    
    assert coordination_stats["success_rate"] >= 0.95, (
        f"Coordination success rate too low: {coordination_stats['success_rate']}"
    )
    
    # Events should be distributed across instances
    instance_distribution = coordination_stats["instance_distribution"]
    if len(instance_distribution) > 1:
        min_events = min(instance_distribution.values())
        max_events = max(instance_distribution.values())
        
        # No single instance should handle more than 70% of events (reasonable distribution)
        total_events = sum(instance_distribution.values())
        max_percentage = max_events / total_events if total_events > 0 else 0
        
        assert max_percentage < 0.7, (
            f"Poor event distribution - single instance handling {max_percentage:.1%} of events"
        )