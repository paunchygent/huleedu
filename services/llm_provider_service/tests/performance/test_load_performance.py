"""
Load testing for LLM Provider Service.

Tests performance optimizations and validates sub-500ms 95th percentile target.

IMPORTANT: All tests use MOCK providers to avoid API costs.
- USE_MOCK_LLM=True forces mock provider usage
- No real API calls are made during performance testing
- Tests validate infrastructure performance, not provider API performance
"""

import asyncio
import statistics
import time
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from dishka import make_async_container

from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider
from services.llm_provider_service.implementations.connection_pool_manager_impl import (
    ConnectionPoolManagerImpl,
)
from services.llm_provider_service.implementations.redis_queue_repository_impl import (
    RedisQueueRepositoryImpl,
)


class LoadTestClient:
    """Test client for load testing LLM Provider Service."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "LoadTestClient":
        connector = aiohttp.TCPConnector(
            limit=100,  # High connection limit for load testing
            limit_per_host=50,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30),
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.session:
            await self.session.close()

    async def make_comparison_request(
        self,
        essay_a: str = "Sample essay A content",
        essay_b: str = "Sample essay B content",
        provider: str = "mock",
    ) -> Tuple[int, float, Dict[str, Any]]:
        """Make a comparison request and return status, response time, and data."""
        if not self.session:
            raise RuntimeError("Session not initialized")

        start_time = time.perf_counter()

        payload = {
            "essay_a": essay_a,
            "essay_b": essay_b,
            "provider": provider,
            "model": "mock-model",
        }

        async with self.session.post(
            f"{self.base_url}/api/v1/comparison", json=payload
        ) as response:
            response_time = time.perf_counter() - start_time
            data = await response.json()
            return response.status, response_time, data


class PerformanceMetrics:
    """Collects and analyzes performance metrics."""

    def __init__(self) -> None:
        self.response_times: List[float] = []
        self.status_codes: List[int] = []
        self.errors: List[str] = []

    def add_measurement(
        self, response_time: float, status_code: int, error: Optional[str] = None
    ) -> None:
        """Add a performance measurement."""
        self.response_times.append(response_time)
        self.status_codes.append(status_code)
        if error:
            self.errors.append(error)

    def get_percentile(self, percentile: float) -> float:
        """Calculate response time percentile."""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * percentile / 100)
        return sorted_times[min(index, len(sorted_times) - 1)]

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        if not self.response_times:
            return {}

        return {
            "total_requests": len(self.response_times),
            "successful_requests": sum(1 for code in self.status_codes if code < 400),
            "failed_requests": sum(1 for code in self.status_codes if code >= 400),
            "error_rate": len(self.errors) / len(self.response_times) * 100,
            "response_times": {
                "min": min(self.response_times),
                "max": max(self.response_times),
                "mean": statistics.mean(self.response_times),
                "median": statistics.median(self.response_times),
                "p95": self.get_percentile(95),
                "p99": self.get_percentile(99),
            },
            "status_codes": {
                "200": sum(1 for code in self.status_codes if code == 200),
                "202": sum(1 for code in self.status_codes if code == 202),
                "4xx": sum(1 for code in self.status_codes if 400 <= code < 500),
                "5xx": sum(1 for code in self.status_codes if code >= 500),
            },
        }


# Settings fixtures are now in conftest.py


@pytest.fixture
async def mock_connection_pool() -> AsyncMock:
    """Mock connection pool manager for testing."""
    pool_manager = AsyncMock(spec=ConnectionPoolManagerImpl)

    # Mock session that responds quickly
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json.return_value = {
        "winner": "Essay A",
        "justification": "Essay A is better structured",
        "confidence": 4.2,
    }
    mock_session.post.return_value.__aenter__.return_value = mock_response

    pool_manager.get_session.return_value = mock_session
    return pool_manager


@pytest.fixture
async def mock_redis_queue() -> AsyncMock:
    """Mock Redis queue repository for testing."""
    return AsyncMock(spec=RedisQueueRepositoryImpl)


class TestLoadPerformance:
    """Load testing for LLM Provider Service performance validation."""

    @pytest.mark.asyncio
    async def test_single_request_performance(self, mock_only_settings: Settings) -> None:
        """Test single request performance baseline."""
        with patch("services.llm_provider_service.implementations.mock_provider_impl.MockProviderImpl") as mock_provider:
            # Configure mock to respond quickly
            mock_provider.return_value.generate_comparison.return_value = (
                {
                    "winner": "Essay A",
                    "justification": "Essay A is better structured",
                    "confidence": 4.2,
                },
                None,
            )

            # Create DI container
            container = make_async_container(LLMProviderServiceProvider())

            async with container() as request_container:
                from services.llm_provider_service.protocols import LLMOrchestratorProtocol

                orchestrator = await request_container.get(LLMOrchestratorProtocol)

                # Measure single request performance
                start_time = time.perf_counter()

                result, error = await orchestrator.process_comparison_request(
                    essay_a="Sample essay A content",
                    essay_b="Sample essay B content",
                    provider="mock",
                    model="mock-model",
                    correlation_id="test-correlation-id",
                )

                response_time = time.perf_counter() - start_time

                # Assertions
                assert error is None
                assert result is not None
                assert response_time < 0.1  # Should be under 100ms for mock

                print(f"Single request performance: {response_time:.4f}s")

    @pytest.mark.asyncio
    async def test_concurrent_requests_performance(self, load_test_settings: Settings) -> None:
        """Test concurrent request performance."""
        concurrent_requests = 50

        with patch("services.llm_provider_service.implementations.mock_provider_impl.MockProviderImpl") as mock_provider:
            # Configure mock to respond quickly
            mock_provider.return_value.generate_comparison.return_value = (
                {
                    "winner": "Essay A",
                    "justification": "Essay A is better structured",
                    "confidence": 4.2,
                },
                None,
            )

            container = make_async_container(LLMProviderServiceProvider())

            async with container() as request_container:
                from services.llm_provider_service.protocols import LLMOrchestratorProtocol

                orchestrator = await request_container.get(LLMOrchestratorProtocol)

                async def make_request(request_id: int) -> Tuple[float, bool]:
                    """Make a single request and return response time and success."""
                    start_time = time.perf_counter()

                    try:
                        result, error = await orchestrator.process_comparison_request(
                            essay_a=f"Sample essay A content {request_id}",
                            essay_b=f"Sample essay B content {request_id}",
                            provider="mock",
                            model="mock-model",
                            correlation_id=f"test-correlation-{request_id}",
                        )

                        response_time = time.perf_counter() - start_time
                        return response_time, error is None
                    except Exception:
                        response_time = time.perf_counter() - start_time
                        return response_time, False

                # Run concurrent requests
                start_time = time.perf_counter()

                tasks = [make_request(i) for i in range(concurrent_requests)]
                results = await asyncio.gather(*tasks)

                total_time = time.perf_counter() - start_time

                # Analyze results
                response_times = [r[0] for r in results]
                successes = [r[1] for r in results]

                p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
                success_rate = sum(successes) / len(successes) * 100

                print("Concurrent requests performance:")
                print(f"  Total requests: {concurrent_requests}")
                print(f"  Total time: {total_time:.4f}s")
                print(f"  Requests per second: {concurrent_requests / total_time:.2f}")
                print(f"  Success rate: {success_rate:.1f}%")
                print(f"  P95 response time: {p95_time:.4f}s")
                print(f"  Mean response time: {statistics.mean(response_times):.4f}s")

                # Assertions
                assert success_rate >= 95  # At least 95% success rate
                assert p95_time < 0.5  # P95 should be under 500ms
                assert statistics.mean(response_times) < 0.2  # Mean should be under 200ms

    @pytest.mark.asyncio
    async def test_connection_pool_efficiency(self, load_test_settings: Settings) -> None:
        """Test connection pool efficiency and reuse."""
        pool_manager = ConnectionPoolManagerImpl(load_test_settings)

        try:
            # Test connection pool creation
            session1 = await pool_manager.get_session("mock")
            session2 = await pool_manager.get_session("mock")

            # Should reuse the same session
            assert session1 is session2

            # Test different providers get different sessions
            openai_session = await pool_manager.get_session("openai")
            assert openai_session is not session1

            # Test connection statistics
            stats = await pool_manager.get_connection_stats("mock")
            assert "pool_size" in stats
            assert "total_connections" in stats

            # Test health check
            health_status = await pool_manager.health_check_connections()
            assert "mock" in health_status

            print(f"Connection pool stats: {stats}")
            print(f"Health status: {health_status}")

        finally:
            await pool_manager.cleanup()

    @pytest.mark.asyncio
    async def test_redis_pipeline_performance(self, load_test_settings: Settings) -> None:
        """Test Redis pipeline performance improvements."""
        # Mock Redis client for testing
        mock_redis = AsyncMock()
        mock_pipeline = AsyncMock()
        mock_redis.client.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True, True, True]

        queue_repo = RedisQueueRepositoryImpl(mock_redis, load_test_settings)

        # Test batch operations
        from datetime import datetime, timedelta, timezone
        from uuid import uuid4

        from services.llm_provider_service.queue_models import QueuedRequest
        from services.llm_provider_service.api_models import LLMComparisonRequest
        from common_core import QueueStatus

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
    async def test_queue_throughput_performance(self, load_test_settings: Settings) -> None:
        """Test queue processing throughput."""
        mock_redis = AsyncMock()
        mock_pipeline = AsyncMock()
        mock_redis.client.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True, True, True]

        # Mock successful queue operations
        mock_redis.client.zrange.return_value = [f"queue-{i}" for i in range(5)]
        mock_redis.client.hmget.return_value = [
            '{"queue_id": "queue-0", "status": "QUEUED", "priority": 0}',
            '{"queue_id": "queue-1", "status": "QUEUED", "priority": 0}',
            '{"queue_id": "queue-2", "status": "QUEUED", "priority": 0}',
            '{"queue_id": "queue-3", "status": "QUEUED", "priority": 0}',
            '{"queue_id": "queue-4", "status": "QUEUED", "priority": 0}',
        ]

        queue_repo = RedisQueueRepositoryImpl(mock_redis, load_test_settings)

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
    async def test_end_to_end_load_scenario(self, load_test_settings: Settings) -> None:
        """Test complete end-to-end load scenario."""
        metrics = PerformanceMetrics()

        # Simulate realistic load pattern
        request_batches = [
            (10, 0.1),  # 10 requests with 0.1s intervals
            (20, 0.05),  # 20 requests with 0.05s intervals (higher load)
            (5, 0.2),   # 5 requests with 0.2s intervals (cooldown)
        ]

        with patch("services.llm_provider_service.implementations.mock_provider_impl.MockProviderImpl") as mock_provider:
            # Configure mock with realistic response times
            mock_provider.return_value.generate_comparison.return_value = (
                {
                    "winner": "Essay A",
                    "justification": "Essay A is better structured",
                    "confidence": 4.2,
                },
                None,
            )

            container = make_async_container(LLMProviderServiceProvider())

            async with container() as request_container:
                from services.llm_provider_service.protocols import LLMOrchestratorProtocol

                orchestrator = await request_container.get(LLMOrchestratorProtocol)

                # Run load test batches
                total_requests = 0

                for batch_size, interval in request_batches:
                    batch_tasks = []

                    for i in range(batch_size):
                        async def make_request(request_id: int) -> None:
                            start_time = time.perf_counter()

                            try:
                                result, error = await orchestrator.process_comparison_request(
                                    essay_a=f"Load test essay A {request_id}",
                                    essay_b=f"Load test essay B {request_id}",
                                    provider="mock",
                                    model="mock-model",
                                    correlation_id=f"load-test-{request_id}",
                                )

                                response_time = time.perf_counter() - start_time
                                status_code = 200 if error is None else 500

                                metrics.add_measurement(response_time, status_code)

                            except Exception as e:
                                response_time = time.perf_counter() - start_time
                                metrics.add_measurement(response_time, 500, str(e))

                        batch_tasks.append(make_request(total_requests + i))

                        # Add interval between requests
                        if i < batch_size - 1:
                            await asyncio.sleep(interval)

                    # Wait for batch to complete
                    await asyncio.gather(*batch_tasks)
                    total_requests += batch_size

                    # Brief pause between batches
                    await asyncio.sleep(0.5)

                # Analyze results
                stats = metrics.get_statistics()

                print("End-to-end load test results:")
                print(f"  Total requests: {stats['total_requests']}")
                print(f"  Success rate: {stats['successful_requests'] / stats['total_requests'] * 100:.1f}%")
                print(f"  Error rate: {stats['error_rate']:.1f}%")
                print("  Response times:")
                print(f"    Mean: {stats['response_times']['mean']:.4f}s")
                print(f"    Median: {stats['response_times']['median']:.4f}s")
                print(f"    P95: {stats['response_times']['p95']:.4f}s")
                print(f"    P99: {stats['response_times']['p99']:.4f}s")
                print(f"  Status codes: {stats['status_codes']}")

                # Validate performance targets
                assert stats['response_times']['p95'] < 0.5  # P95 under 500ms
                assert stats['successful_requests'] / stats['total_requests'] >= 0.95  # 95% success rate
                assert stats['error_rate'] < 5  # Less than 5% error rate
