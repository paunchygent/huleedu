"""
Redis queue performance tests using real infrastructure.

Tests Redis pipeline performance, queue throughput, and batch operations
with real Redis testcontainer infrastructure for meaningful performance data.
Uses mock LLM providers to avoid API costs.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Generator
from uuid import uuid4

import pytest
from common_core import Environment, QueueStatus
from dishka import Scope, make_async_container, provide
from testcontainers.redis import RedisContainer

from services.llm_provider_service.api_models import LLMComparisonRequest
from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider
from services.llm_provider_service.implementations.redis_queue_repository_impl import (
    RedisQueueRepositoryImpl,
)
from services.llm_provider_service.queue_models import QueuedRequest


class LLMProviderServiceTestProvider(LLMProviderServiceProvider):
    """Test-specific provider that allows settings injection."""

    def __init__(self, test_settings: Settings):
        super().__init__()
        self._test_settings = test_settings

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        return self._test_settings


@pytest.fixture(scope="class")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Provide a Redis container for testing."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="class")
def redis_performance_settings(redis_container: RedisContainer) -> Settings:
    """Settings configured for Redis performance testing."""
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    return Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.TESTING,
        LOG_LEVEL="INFO",
        USE_MOCK_LLM=True,  # Keep LLM mocked to avoid API costs
        REDIS_URL=redis_url,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",  # Not used in Redis tests
    )


@pytest.fixture
async def redis_di_container(redis_performance_settings: Settings) -> AsyncGenerator[Any, None]:
    """DI container with real Redis for performance testing."""
    test_provider = LLMProviderServiceTestProvider(redis_performance_settings)
    container = make_async_container(test_provider)

    try:
        yield container
    finally:
        # Cleanup Redis client
        async with container() as request_container:
            try:
                from huleedu_service_libs.queue_protocols import QueueRedisClientProtocol

                queue_redis_client = await request_container.get(QueueRedisClientProtocol)
                if hasattr(queue_redis_client, "stop"):
                    await queue_redis_client.stop()
            except Exception as e:
                print(f"⚠ Failed to stop queue Redis client: {e}")


class TestRedisPerformance:
    """Tests for Redis queue performance with real infrastructure."""

    @pytest.mark.asyncio
    async def test_redis_pipeline_performance(self, redis_di_container: Any) -> None:
        """Test Redis pipeline performance improvements with real infrastructure."""
        async with redis_di_container() as request_container:
            # Get real Redis queue repository from DI container
            queue_repo = await request_container.get(RedisQueueRepositoryImpl)

        # Test batch operations
        requests = []
        for i in range(10):
            request_data = LLMComparisonRequest(
                user_prompt="Compare these essays",
                essay_a=f"Essay A {i}",
                essay_b=f"Essay B {i}",
                callback_topic="test.callback.topic",
            )
            request = QueuedRequest(
                queue_id=uuid4(),
                request_data=request_data,
                queued_at=datetime.now(timezone.utc),
                ttl=timedelta(hours=4),
                priority=0,
                status=QueueStatus.QUEUED,
                retry_count=0,
                size_bytes=100,
                callback_topic="test.callback.topic",
            )
            requests.append(request)

        # Measure pipeline performance
        start_time = time.perf_counter()

        # Add requests using pipeline
        for request in requests:
            await queue_repo.add(request)

        pipeline_time = time.perf_counter() - start_time

        print(f"Real Redis pipeline performance: {pipeline_time:.4f}s for {len(requests)} requests")
        print(f"Average per request: {pipeline_time / len(requests):.4f}s")
        print("Infrastructure: Real Redis (testcontainer)")

        # Realistic performance assertions for Redis pipeline
        assert pipeline_time / len(requests) < 0.1  # Under 100ms per operation

    @pytest.mark.asyncio
    async def test_queue_throughput_performance(self, redis_di_container: Any) -> None:
        """Test queue processing throughput with real Redis."""
        async with redis_di_container() as request_container:
            queue_repo = await request_container.get(RedisQueueRepositoryImpl)

            # Add real test data to Redis queue
            test_requests = []
            for i in range(5):
                request_data = LLMComparisonRequest(
                    user_prompt="Compare these essays",
                    essay_a=f"Test essay A {i}",
                    essay_b=f"Test essay B {i}",
                    callback_topic="test.callback.topic",
                )
                request = QueuedRequest(
                    queue_id=uuid4(),
                    request_data=request_data,
                    queued_at=datetime.now(timezone.utc),
                    ttl=timedelta(hours=4),
                    priority=0,
                    status=QueueStatus.QUEUED,
                    retry_count=0,
                    size_bytes=100,
                    callback_topic="test.callback.topic",
                )
                test_requests.append(request)
                # Add to real Redis
                await queue_repo.add(request)

        # Test batch queue retrieval
        start_time = time.perf_counter()

        # Simulate multiple queue retrievals
        for _ in range(10):
            await queue_repo.get_next()

        retrieval_time = time.perf_counter() - start_time

        print(f"Real Redis queue throughput: 10 retrievals in {retrieval_time:.4f}s")
        print(f"Average per retrieval: {retrieval_time / 10:.4f}s")
        print("Infrastructure: Real Redis (testcontainer)")

        # Realistic performance assertions for Redis throughput
        assert retrieval_time / 10 < 0.2  # Under 200ms per retrieval

    @pytest.mark.asyncio
    async def test_redis_batch_operations_performance(self, redis_di_container: Any) -> None:
        """Test performance of Redis batch operations with real infrastructure."""
        async with redis_di_container() as request_container:
            queue_repo = await request_container.get(RedisQueueRepositoryImpl)

        # Create test requests
        requests = []
        for i in range(20):
            request_data = LLMComparisonRequest(
                user_prompt=f"Batch test prompt {i}",
                essay_a=f"Batch essay A {i}",
                essay_b=f"Batch essay B {i}",
                callback_topic="test.callback.topic",
            )
            request = QueuedRequest(
                queue_id=uuid4(),
                request_data=request_data,
                queued_at=datetime.now(timezone.utc),
                ttl=timedelta(hours=4),
                priority=i % 3,  # Varying priorities
                status=QueueStatus.QUEUED,
                retry_count=0,
                size_bytes=150 + i * 5,  # Varying sizes
                callback_topic="test.callback.topic",
            )
            requests.append(request)

        # Test batch addition
        batch_start_time = time.perf_counter()

        for request in requests:
            await queue_repo.add(request)

        batch_time = time.perf_counter() - batch_start_time

        print("Real Redis batch operations performance:")
        print(f"  Total requests: {len(requests)}")
        print(f"  Batch time: {batch_time:.4f}s")
        print(f"  Time per request: {batch_time / len(requests):.6f}s")
        print("  Infrastructure: Real Redis (testcontainer)")

        # Realistic performance assertions for Redis batch operations
        assert batch_time < 3.0  # Should complete within 3s
        assert batch_time / len(requests) < 0.15  # Under 150ms per request

    @pytest.mark.asyncio
    async def test_redis_memory_usage_tracking(self, redis_di_container: Any) -> None:
        """Test Redis memory usage tracking performance with real infrastructure."""
        async with redis_di_container() as request_container:
            queue_repo = await request_container.get(RedisQueueRepositoryImpl)

            # Add real test data to Redis
            for i in range(5):
                request_data = LLMComparisonRequest(
                    user_prompt="Memory test",
                    essay_a=f"Memory essay A {i}",
                    essay_b=f"Memory essay B {i}",
                    callback_topic="test.callback.topic",
                )
                request = QueuedRequest(
                    queue_id=uuid4(),
                    request_data=request_data,
                    queued_at=datetime.now(timezone.utc),
                    ttl=timedelta(hours=4),
                    priority=0,
                    status=QueueStatus.QUEUED,
                    retry_count=0,
                    size_bytes=1024,  # 1KB per request
                    callback_topic="test.callback.topic",
                )
                await queue_repo.add(request)

        # Test memory tracking performance
        memory_operations = 50
        start_time = time.perf_counter()

        for _ in range(memory_operations):
            # Simulate memory usage checks
            await queue_repo.get_memory_usage()

        memory_tracking_time = time.perf_counter() - start_time

        print("Real Redis memory tracking performance:")
        print(f"  Memory operations: {memory_operations}")
        print(f"  Total time: {memory_tracking_time:.4f}s")
        print(f"  Time per operation: {memory_tracking_time / memory_operations:.6f}s")
        print("  Infrastructure: Real Redis (testcontainer)")

        # Realistic performance assertions for Redis memory tracking
        assert memory_tracking_time < 5.0  # Should complete within 5s
        assert memory_tracking_time / memory_operations < 0.1  # Under 100ms per operation

    @pytest.mark.asyncio
    async def test_redis_concurrent_pipeline_operations(self, redis_di_container: Any) -> None:
        """Test concurrent Redis pipeline operations performance with real infrastructure."""
        import asyncio

        async with redis_di_container() as request_container:
            queue_repo = await request_container.get(RedisQueueRepositoryImpl)

        async def concurrent_add_operation(operation_id: int) -> float:
            """Perform concurrent add operation."""
            start_time = time.perf_counter()

            request_data = LLMComparisonRequest(
                user_prompt=f"Concurrent test {operation_id}",
                essay_a=f"Concurrent essay A {operation_id}",
                essay_b=f"Concurrent essay B {operation_id}",
                callback_topic="test.callback.topic",
            )
            request = QueuedRequest(
                queue_id=uuid4(),
                request_data=request_data,
                queued_at=datetime.now(timezone.utc),
                ttl=timedelta(hours=4),
                priority=0,
                status=QueueStatus.QUEUED,
                retry_count=0,
                size_bytes=100,
                callback_topic="test.callback.topic",
            )

            await queue_repo.add(request)
            return time.perf_counter() - start_time

        # Test concurrent operations
        concurrent_ops = 25
        start_time = time.perf_counter()

        tasks = [concurrent_add_operation(i) for i in range(concurrent_ops)]
        operation_times = await asyncio.gather(*tasks)

        total_time = time.perf_counter() - start_time

        # Analyze concurrent performance
        avg_operation_time = sum(operation_times) / len(operation_times)
        max_operation_time = max(operation_times)
        min_operation_time = min(operation_times)

        print("Concurrent real Redis pipeline performance:")
        print(f"  Concurrent operations: {concurrent_ops}")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Operations per second: {concurrent_ops / total_time:.2f}")
        print(f"  Average operation time: {avg_operation_time:.6f}s")
        print(f"  Min/Max operation time: {min_operation_time:.6f}s / {max_operation_time:.6f}s")
        print("  Infrastructure: Real Redis (testcontainer)")

        # Realistic performance assertions for Redis concurrency
        assert total_time < 5.0  # Should handle concurrency within 5s
        assert avg_operation_time < 0.2  # Under 200ms per operation

    @pytest.mark.asyncio
    async def test_redis_pipeline_error_resilience(self, redis_di_container: Any) -> None:
        """Test Redis pipeline resilience with real infrastructure."""
        import asyncio

        async with redis_di_container() as request_container:
            queue_repo = await request_container.get(RedisQueueRepositoryImpl)

        async def add_with_resilience_test(operation_id: int) -> tuple[float, bool]:
            """Test Redis resilience with real operations."""
            start_time = time.perf_counter()

            try:
                request_data = LLMComparisonRequest(
                    user_prompt=f"Resilience test {operation_id}",
                    essay_a=f"Resilience essay A {operation_id}",
                    essay_b=f"Resilience essay B {operation_id}",
                    callback_topic="test.callback.topic",
                )
                request = QueuedRequest(
                    queue_id=uuid4(),
                    request_data=request_data,
                    queued_at=datetime.now(timezone.utc),
                    ttl=timedelta(hours=4),
                    priority=0,
                    status=QueueStatus.QUEUED,
                    retry_count=0,
                    size_bytes=100,
                    callback_topic="test.callback.topic",
                )

                result = await queue_repo.add(request)
                operation_time = time.perf_counter() - start_time
                return operation_time, result

            except Exception:
                operation_time = time.perf_counter() - start_time
                return operation_time, False

        # Test resilience performance
        resilience_test_ops = 10
        start_time = time.perf_counter()

        tasks = [add_with_resilience_test(i) for i in range(resilience_test_ops)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_time = time.perf_counter() - start_time

        # Process results
        operation_times = []
        successes = 0

        for result in results:
            if isinstance(result, tuple):
                operation_times.append(result[0])
                if result[1]:
                    successes += 1
            else:
                # Exception occurred, estimate timing
                operation_times.append(0.001)

        avg_time = sum(operation_times) / len(operation_times)

        print("Real Redis resilience performance:")
        print(f"  Resilience test operations: {resilience_test_ops}")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Successful operations: {successes}")
        print(f"  Average time: {avg_time:.6f}s")
        print("  Infrastructure: Real Redis (testcontainer)")

        # Realistic performance assertions for Redis resilience
        assert total_time < 8.0  # Should complete within 8s
        assert avg_time < 0.5  # Under 500ms per operation
        assert successes >= resilience_test_ops * 0.90  # At least 90% success rate
