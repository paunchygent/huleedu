"""
Redis queue performance tests.

Tests Redis pipeline performance, queue throughput, and batch operations
for optimized queue management.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from common_core import QueueStatus
from services.llm_provider_service.api_models import LLMComparisonRequest
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.redis_queue_repository_impl import (
    RedisQueueRepositoryImpl,
)
from services.llm_provider_service.queue_models import QueuedRequest


class TestRedisPerformance:
    """Tests for Redis queue performance and optimization."""

    @pytest.mark.asyncio
    async def test_redis_pipeline_performance(self, mock_only_settings: Settings) -> None:
        """Test Redis pipeline performance improvements."""
        # Mock Redis client for testing
        mock_redis = AsyncMock()
        mock_client = Mock()  # Regular Mock for the client
        mock_pipeline = Mock()  # Regular Mock for the pipeline

        mock_redis.client = mock_client
        mock_client.pipeline.return_value = mock_pipeline
        mock_pipeline.execute = AsyncMock(return_value=[True, True, True])

        queue_repo = RedisQueueRepositoryImpl(mock_redis, mock_only_settings)

        # Test batch operations
        requests = []
        for i in range(10):
            request_data = LLMComparisonRequest(
                user_prompt="Compare these essays",
                essay_a=f"Essay A {i}",
                essay_b=f"Essay B {i}",
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
            )
            requests.append(request)

        # Measure pipeline performance
        start_time = time.perf_counter()

        # Add requests using pipeline
        for request in requests:
            await queue_repo.add(request)

        pipeline_time = time.perf_counter() - start_time

        # Verify pipeline was used
        assert mock_redis.client.pipeline.called
        assert mock_pipeline.execute.called

        print(f"Redis pipeline performance: {pipeline_time:.4f}s for {len(requests)} requests")
        print(f"Average per request: {pipeline_time / len(requests):.4f}s")

    @pytest.mark.asyncio
    async def test_queue_throughput_performance(self, mock_only_settings: Settings) -> None:
        """Test queue processing throughput."""
        mock_redis = AsyncMock()
        mock_client = Mock()  # Regular Mock for the client
        mock_pipeline = Mock()  # Regular Mock for the pipeline

        mock_redis.client = mock_client
        mock_client.pipeline.return_value = mock_pipeline
        mock_pipeline.execute = AsyncMock(return_value=[True, True, True])

        # Generate proper UUIDs for test data
        test_queue_ids = [str(uuid4()) for _ in range(5)]

        # Create valid QueuedRequest JSON data
        def create_valid_queue_request(queue_id: str) -> str:
            return json.dumps(
                {
                    "queue_id": queue_id,
                    "request_data": {
                        "user_prompt": "Compare these essays",
                        "essay_a": "Test essay A",
                        "essay_b": "Test essay B",
                    },
                    "queued_at": datetime.now(timezone.utc).isoformat(),
                    "ttl": 14400,  # 4 hours in seconds
                    "priority": 0,
                    "status": "queued",  # lowercase, not QUEUED
                    "retry_count": 0,
                    "size_bytes": 100,
                }
            )

        # Mock successful queue operations
        mock_client.zrange = AsyncMock(return_value=test_queue_ids)
        mock_client.hmget = AsyncMock(
            return_value=[
                create_valid_queue_request(test_queue_ids[0]),
                create_valid_queue_request(test_queue_ids[1]),
                create_valid_queue_request(test_queue_ids[2]),
                create_valid_queue_request(test_queue_ids[3]),
                create_valid_queue_request(test_queue_ids[4]),
            ]
        )

        # Mock hget for individual retrievals
        mock_client.hget = AsyncMock(
            side_effect=lambda key, queue_id: create_valid_queue_request(queue_id)
            if queue_id in test_queue_ids
            else None
        )

        queue_repo = RedisQueueRepositoryImpl(mock_redis, mock_only_settings)

        # Test batch queue retrieval
        start_time = time.perf_counter()

        # Simulate multiple queue retrievals
        for _ in range(10):
            await queue_repo.get_next()

        retrieval_time = time.perf_counter() - start_time

        print(f"Queue throughput: 10 retrievals in {retrieval_time:.4f}s")
        print(f"Average per retrieval: {retrieval_time / 10:.4f}s")

        # Verify batch operations were used
        assert mock_redis.client.zrange.called
        assert mock_redis.client.hmget.called

    @pytest.mark.asyncio
    async def test_redis_batch_operations_performance(self, mock_only_settings: Settings) -> None:
        """Test performance of Redis batch operations vs individual operations."""
        mock_redis = AsyncMock()
        mock_client = Mock()
        mock_pipeline = Mock()

        mock_redis.client = mock_client
        mock_client.pipeline.return_value = mock_pipeline
        mock_pipeline.execute = AsyncMock(return_value=[True] * 20)

        queue_repo = RedisQueueRepositoryImpl(mock_redis, mock_only_settings)

        # Create test requests
        requests = []
        for i in range(20):
            request_data = LLMComparisonRequest(
                user_prompt=f"Batch test prompt {i}",
                essay_a=f"Batch essay A {i}",
                essay_b=f"Batch essay B {i}",
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
            )
            requests.append(request)

        # Test batch addition
        batch_start_time = time.perf_counter()

        for request in requests:
            await queue_repo.add(request)

        batch_time = time.perf_counter() - batch_start_time

        # Verify pipeline usage for batch operations
        assert mock_redis.client.pipeline.call_count > 0
        pipeline_calls = mock_redis.client.pipeline.call_count
        execute_calls = mock_pipeline.execute.call_count

        print("Redis batch operations performance:")
        print(f"  Total requests: {len(requests)}")
        print(f"  Batch time: {batch_time:.4f}s")
        print(f"  Time per request: {batch_time / len(requests):.6f}s")
        print(f"  Pipeline calls: {pipeline_calls}")
        print(f"  Execute calls: {execute_calls}")

        # Performance assertions
        assert batch_time < 0.5  # Should complete quickly with mocked Redis
        assert batch_time / len(requests) < 0.01  # Each request should be very fast

    @pytest.mark.asyncio
    async def test_redis_memory_usage_tracking(self, mock_only_settings: Settings) -> None:
        """Test Redis memory usage tracking performance."""
        mock_redis = AsyncMock()
        mock_client = Mock()

        # Mock memory tracking operations
        mock_client.memory_usage = AsyncMock(return_value=1024)  # 1KB per key
        mock_client.dbsize = AsyncMock(return_value=100)  # 100 keys
        mock_client.info = AsyncMock(
            return_value={
                "used_memory": 1048576,  # 1MB
                "used_memory_human": "1.00M",
            }
        )

        mock_redis.client = mock_client

        queue_repo = RedisQueueRepositoryImpl(mock_redis, mock_only_settings)

        # Test memory tracking performance
        memory_operations = 50
        start_time = time.perf_counter()

        for _ in range(memory_operations):
            # Simulate memory usage checks
            await queue_repo.get_memory_usage()

        memory_tracking_time = time.perf_counter() - start_time

        print("Redis memory tracking performance:")
        print(f"  Memory operations: {memory_operations}")
        print(f"  Total time: {memory_tracking_time:.4f}s")
        print(f"  Time per operation: {memory_tracking_time / memory_operations:.6f}s")

        # Verify Redis operations were called
        assert mock_client.info.called

        # Performance assertions
        assert memory_tracking_time < 1.0  # Should be fast with mocked Redis
        assert memory_tracking_time / memory_operations < 0.01  # Each operation fast

    @pytest.mark.asyncio
    async def test_redis_concurrent_pipeline_operations(self, mock_only_settings: Settings) -> None:
        """Test concurrent Redis pipeline operations performance."""
        import asyncio

        mock_redis = AsyncMock()
        mock_client = Mock()
        mock_pipeline = Mock()

        mock_redis.client = mock_client
        mock_client.pipeline.return_value = mock_pipeline
        mock_pipeline.execute = AsyncMock(return_value=[True, True, True])

        queue_repo = RedisQueueRepositoryImpl(mock_redis, mock_only_settings)

        async def concurrent_add_operation(operation_id: int) -> float:
            """Perform concurrent add operation."""
            start_time = time.perf_counter()

            request_data = LLMComparisonRequest(
                user_prompt=f"Concurrent test {operation_id}",
                essay_a=f"Concurrent essay A {operation_id}",
                essay_b=f"Concurrent essay B {operation_id}",
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

        print("Concurrent Redis pipeline performance:")
        print(f"  Concurrent operations: {concurrent_ops}")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Operations per second: {concurrent_ops / total_time:.2f}")
        print(f"  Average operation time: {avg_operation_time:.6f}s")
        print(f"  Min/Max operation time: {min_operation_time:.6f}s / {max_operation_time:.6f}s")

        # Verify pipeline was used for concurrent operations
        assert mock_redis.client.pipeline.called
        assert mock_pipeline.execute.called

        # Performance assertions
        assert total_time < 2.0  # Should handle concurrency well
        assert avg_operation_time < 0.05  # Each operation should be fast

    @pytest.mark.asyncio
    async def test_redis_pipeline_error_handling_performance(
        self, mock_only_settings: Settings
    ) -> None:
        """Test performance impact of error handling in Redis pipelines."""
        import asyncio

        mock_redis = AsyncMock()
        mock_client = Mock()
        mock_pipeline = Mock()

        mock_redis.client = mock_client
        mock_client.pipeline.return_value = mock_pipeline

        # Simulate some operations succeeding and some failing
        mock_pipeline.execute = AsyncMock(
            side_effect=[
                [True, True, Exception("Redis error")],  # Mixed success/failure
                [True, True, True],  # All success
                [Exception("Pipeline error")],  # Pipeline failure
                [True, True, True],  # Recovery
            ]
        )

        queue_repo = RedisQueueRepositoryImpl(mock_redis, mock_only_settings)

        async def add_with_error_handling(operation_id: int) -> tuple[float, bool]:
            """Add operation with error handling timing."""
            start_time = time.perf_counter()

            try:
                request_data = LLMComparisonRequest(
                    user_prompt=f"Error test {operation_id}",
                    essay_a=f"Error essay A {operation_id}",
                    essay_b=f"Error essay B {operation_id}",
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
                )

                result = await queue_repo.add(request)
                operation_time = time.perf_counter() - start_time
                return operation_time, result

            except Exception:
                operation_time = time.perf_counter() - start_time
                return operation_time, False

        # Test error handling performance
        error_test_ops = 10
        start_time = time.perf_counter()

        tasks = [add_with_error_handling(i) for i in range(error_test_ops)]
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

        avg_time_with_errors = sum(operation_times) / len(operation_times)

        print("Redis error handling performance:")
        print(f"  Operations with errors: {error_test_ops}")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Successful operations: {successes}")
        print(f"  Average time with errors: {avg_time_with_errors:.6f}s")

        # Verify error handling doesn't severely impact performance
        assert total_time < 3.0  # Should handle errors reasonably fast
        assert avg_time_with_errors < 0.1  # Error handling overhead should be minimal
