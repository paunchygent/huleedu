"""
End-to-end performance tests using real infrastructure.

Tests complete pipeline performance under realistic load patterns with real
Redis and Kafka infrastructure. Uses mock LLM providers to avoid API costs
while providing meaningful infrastructure performance data.
"""

import asyncio
import time
from typing import Any, AsyncGenerator, Dict, Generator
from uuid import uuid4

import pytest
from common_core import Environment, LLMProviderType
from dishka import Scope, make_async_container, provide
from huleedu_service_libs.resilience import CircuitBreakerRegistry
from testcontainers.kafka import KafkaContainer
from testcontainers.redis import RedisContainer

from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider
from services.llm_provider_service.exceptions import HuleEduError
from services.llm_provider_service.implementations.connection_pool_manager_impl import (
    ConnectionPoolManagerImpl,
)
from services.llm_provider_service.internal_models import (
    LLMOrchestratorResponse,
    LLMQueuedResult,
)
from services.llm_provider_service.protocols import (
    LLMOrchestratorProtocol,
    LLMProviderProtocol,
    LLMRetryManagerProtocol,
)

from .conftest import PerformanceMetrics


class LLMProviderServiceTestProvider(LLMProviderServiceProvider):
    """Test-specific provider that allows settings injection."""

    def __init__(self, test_settings: Settings):
        super().__init__()
        self._test_settings = test_settings

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        return self._test_settings

    @provide(scope=Scope.APP)
    async def provide_llm_provider_map(
        self,
        settings: Settings,
        pool_manager: ConnectionPoolManagerImpl,
        retry_manager: LLMRetryManagerProtocol,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> Dict[LLMProviderType, LLMProviderProtocol]:
        """Provide dictionary of performance-optimized mock providers."""
        # Always use performance-optimized mock providers for performance tests
        from services.llm_provider_service.implementations.mock_provider_impl import (
            MockProviderImpl,
        )

        mock_provider = MockProviderImpl(settings=settings, seed=42, performance_mode=True)
        return {
            LLMProviderType.MOCK: mock_provider,
            LLMProviderType.ANTHROPIC: mock_provider,
            LLMProviderType.OPENAI: mock_provider,
            LLMProviderType.GOOGLE: mock_provider,
            LLMProviderType.OPENROUTER: mock_provider,
        }


@pytest.fixture(scope="class")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Provide a Redis container for testing."""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="class")
def kafka_container() -> Generator[KafkaContainer, None, None]:
    """Provide a Kafka container for testing."""
    with KafkaContainer("confluentinc/cp-kafka:7.4.0") as container:
        yield container


@pytest.fixture(scope="class")
def infrastructure_settings(
    redis_container: RedisContainer, kafka_container: KafkaContainer
) -> Settings:
    """Settings configured for testcontainer infrastructure."""
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    return Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.TESTING,
        LOG_LEVEL="INFO",
        USE_MOCK_LLM=True,  # Keep LLM mocked to avoid API costs
        REDIS_URL=redis_url,
        KAFKA_BOOTSTRAP_SERVERS=kafka_container.get_bootstrap_server(),
        # Performance test configurations
        CIRCUIT_BREAKER_ENABLED=True,
    )


@pytest.fixture
async def infrastructure_di_container(
    infrastructure_settings: Settings,
) -> AsyncGenerator[Any, None]:
    """DI container with real infrastructure for end-to-end performance testing."""
    test_provider = LLMProviderServiceTestProvider(infrastructure_settings)
    container = make_async_container(test_provider)

    try:
        yield container
    finally:
        # Cleanup all infrastructure components
        async with container() as request_container:
            try:
                from huleedu_service_libs.kafka_client import KafkaBus

                kafka_bus = await request_container.get(KafkaBus)
                if hasattr(kafka_bus, "stop"):
                    await kafka_bus.stop()
            except Exception as e:
                print(f"⚠ Failed to stop Kafka bus: {e}")

            try:
                from huleedu_service_libs.queue_protocols import QueueRedisClientProtocol

                queue_redis_client = await request_container.get(QueueRedisClientProtocol)
                if hasattr(queue_redis_client, "stop"):
                    await queue_redis_client.stop()
            except Exception as e:
                print(f"⚠ Failed to stop queue Redis client: {e}")

            try:
                from huleedu_service_libs.protocols import RedisClientProtocol

                redis_client = await request_container.get(RedisClientProtocol)
                if hasattr(redis_client, "stop"):
                    await redis_client.stop()
            except Exception as e:
                print(f"⚠ Failed to stop Redis client: {e}")


class TestEndToEndPerformance:
    """Tests for complete end-to-end pipeline performance with real infrastructure."""

    @pytest.mark.asyncio
    async def test_end_to_end_load_scenario(self, infrastructure_di_container: Any) -> None:
        """Test complete end-to-end load scenario with real infrastructure."""
        metrics = PerformanceMetrics()

        # Simulate realistic load pattern
        request_batches = [
            (5, 0.2),  # 5 requests with 0.2s intervals
            (8, 0.15),  # 8 requests with 0.15s intervals (higher load)
            (3, 0.3),  # 3 requests with 0.3s intervals (cooldown)
        ]

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        # Run load test batches
        total_requests = 0

        for batch_size, interval in request_batches:
            batch_tasks = []

            for i in range(batch_size):

                async def make_request(request_id: int) -> None:
                    start_time = time.perf_counter()

                    try:
                        result = await orchestrator.perform_comparison(
                            provider=LLMProviderType.MOCK,  # Mock to avoid API costs
                            user_prompt="Compare these essays",
                            essay_a=f"Load test essay A {request_id}",
                            essay_b=f"Load test essay B {request_id}",
                            correlation_id=uuid4(),
                            model="mock-model",
                        )

                        response_time = time.perf_counter() - start_time

                        # Granular status codes based on response type
                        if isinstance(result, LLMQueuedResult):
                            status_code = 202  # Accepted (queued)
                        elif isinstance(result, LLMOrchestratorResponse):
                            status_code = 200  # Success (immediate response)
                        else:
                            status_code = 500  # Unexpected response type

                        metrics.add_measurement(response_time, status_code)

                    except HuleEduError as e:
                        # Application-level errors (rate limits, auth, validation, etc.)
                        response_time = time.perf_counter() - start_time
                        metrics.add_measurement(response_time, 400, str(e))
                    except Exception as e:
                        # Infrastructure errors (network, timeout, etc.)
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

        print("End-to-end load test results (real infrastructure):")
        print(f"  Total requests: {stats['total_requests']}")
        success_rate = stats["successful_requests"] / stats["total_requests"] * 100
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  Error rate: {stats['error_rate']:.1f}%")
        print("  Response times:")
        print(f"    Mean: {stats['response_times']['mean']:.4f}s")
        print(f"    Median: {stats['response_times']['median']:.4f}s")
        print(f"    P95: {stats['response_times']['p95']:.4f}s")
        print(f"    P99: {stats['response_times']['p99']:.4f}s")
        print(f"  Status codes: {stats['status_codes']}")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")
        print("  LLM Provider: Mock (no API costs)")

        # Realistic performance targets for real infrastructure
        assert stats["response_times"]["p95"] < 5.0  # P95 under 5s
        assert stats["successful_requests"] / stats["total_requests"] >= 0.90  # 90% success rate
        assert stats["error_rate"] < 10  # Less than 10% error rate

    @pytest.mark.asyncio
    async def test_mixed_workload_performance(self, infrastructure_di_container: Any) -> None:
        """Test performance under mixed workload with real infrastructure."""
        metrics = PerformanceMetrics()

        # Define different workload types (reduced for real infrastructure)
        workloads = [
            ("quick", 5, 0.1, "Quick comparison"),
            ("detailed", 4, 0.2, "Detailed analysis comparison"),
            ("batch", 3, 0.3, "Batch processing comparison"),
        ]

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        async def execute_workload(
            workload_name: str, count: int, delay: float, prompt: str
        ) -> Dict[str, Any]:
            """Execute a specific workload type."""
            workload_metrics = PerformanceMetrics()
            tasks = []

            async def workload_request(request_id: int) -> None:
                start_time = time.perf_counter()
                try:
                    result = await orchestrator.perform_comparison(
                        provider=LLMProviderType.MOCK,
                        user_prompt=prompt,
                        essay_a=f"{workload_name} essay A {request_id}",
                        essay_b=f"{workload_name} essay B {request_id}",
                        correlation_id=uuid4(),
                        model="mock-model",
                    )
                    response_time = time.perf_counter() - start_time

                    # Granular status codes based on response type
                    if isinstance(result, LLMQueuedResult):
                        status_code = 202  # Accepted (queued)
                    elif isinstance(result, LLMOrchestratorResponse):
                        status_code = 200  # Success (immediate response)
                    else:
                        status_code = 500  # Unexpected response type

                    workload_metrics.add_measurement(response_time, status_code)
                    metrics.add_measurement(response_time, status_code)
                except HuleEduError as e:
                    # Application-level errors (rate limits, auth, validation, etc.)
                    response_time = time.perf_counter() - start_time
                    workload_metrics.add_measurement(response_time, 400, str(e))
                    metrics.add_measurement(response_time, 400, str(e))
                except Exception as e:
                    # Infrastructure errors (network, timeout, etc.)
                    response_time = time.perf_counter() - start_time
                    workload_metrics.add_measurement(response_time, 500, str(e))
                    metrics.add_measurement(response_time, 500, str(e))

            # Create tasks with delays
            for i in range(count):
                tasks.append(workload_request(i))
                if i < count - 1:
                    await asyncio.sleep(delay)

            await asyncio.gather(*tasks)
            return workload_metrics.get_statistics()

        # Execute all workloads concurrently
        workload_results = {}
        workload_tasks = []

        for workload_name, count, delay, prompt in workloads:
            task = execute_workload(workload_name, count, delay, prompt)
            workload_tasks.append((workload_name, task))

        # Run all workloads
        for workload_name, task in workload_tasks:
            workload_results[workload_name] = await task

        # Analyze overall mixed workload results
        overall_stats = metrics.get_statistics()

        print("Mixed workload performance results (real infrastructure):")
        print(f"  Total requests: {overall_stats['total_requests']}")
        overall_success_rate = (
            overall_stats["successful_requests"] / overall_stats["total_requests"] * 100
        )
        print(f"  Overall success rate: {overall_success_rate:.1f}%")
        print(f"  Overall P95: {overall_stats['response_times']['p95']:.4f}s")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Per-workload analysis
        for workload_name, stats in workload_results.items():
            if stats:  # Check if stats is not empty
                print(f"  {workload_name.capitalize()} workload:")
                print(f"    Requests: {stats['total_requests']}")
                workload_success_rate = stats["successful_requests"] / stats["total_requests"] * 100
                print(f"    Success rate: {workload_success_rate:.1f}%")
                print(f"    Mean time: {stats['response_times']['mean']:.4f}s")

        # Realistic mixed workload performance targets
        assert overall_stats["response_times"]["p95"] < 6.0  # P95 under 6s for mixed load
        assert (
            overall_stats["successful_requests"] / overall_stats["total_requests"] >= 0.85
        )  # 85% success rate

    @pytest.mark.slow
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_sustained_load_performance(self, infrastructure_di_container: Any) -> None:
        """Test performance under sustained load with real infrastructure."""
        duration_seconds = 15  # Reduced for real infrastructure
        requests_per_second = 2  # Reduced rate for real infrastructure

        metrics = PerformanceMetrics()

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        async def sustained_request_generator() -> None:
            """Generate requests at sustained rate."""
            request_id = 0
            start_time = time.perf_counter()

            while time.perf_counter() - start_time < duration_seconds:

                async def make_sustained_request(req_id: int) -> None:
                    req_start = time.perf_counter()
                    try:
                        result = await orchestrator.perform_comparison(
                            provider=LLMProviderType.MOCK,
                            user_prompt="Sustained load test",
                            essay_a=f"Sustained essay A {req_id}",
                            essay_b=f"Sustained essay B {req_id}",
                            correlation_id=uuid4(),
                            model="mock-model",
                        )
                        response_time = time.perf_counter() - req_start

                        # Granular status codes based on response type
                        if isinstance(result, LLMQueuedResult):
                            status_code = 202  # Accepted (queued)
                        elif isinstance(result, LLMOrchestratorResponse):
                            status_code = 200  # Success (immediate response)
                        else:
                            status_code = 500  # Unexpected response type

                        metrics.add_measurement(response_time, status_code)
                    except HuleEduError as e:
                        # Application-level errors (rate limits, auth, validation, etc.)
                        response_time = time.perf_counter() - req_start
                        metrics.add_measurement(response_time, 400, str(e))
                    except Exception as e:
                        # Infrastructure errors (network, timeout, etc.)
                        response_time = time.perf_counter() - req_start
                        metrics.add_measurement(response_time, 500, str(e))

                # Start request without waiting for completion
                asyncio.create_task(make_sustained_request(request_id))
                request_id += 1

                # Wait for next request interval
                await asyncio.sleep(1.0 / requests_per_second)

        # Run sustained load test
        print(f"Starting sustained load test: {requests_per_second} req/s for {duration_seconds}s")
        await sustained_request_generator()

        # Wait a bit for remaining requests to complete
        await asyncio.sleep(2.0)

        # Analyze sustained load results
        stats = metrics.get_statistics()

        print("Sustained load test results (real infrastructure):")
        print(f"  Duration: {duration_seconds}s")
        print(f"  Target rate: {requests_per_second} req/s")
        print(f"  Actual requests: {stats['total_requests']}")
        actual_rate = stats["total_requests"] / duration_seconds
        print(f"  Actual rate: {actual_rate:.2f} req/s")
        sustained_success_rate = stats["successful_requests"] / stats["total_requests"] * 100
        print(f"  Success rate: {sustained_success_rate:.1f}%")
        print("  Response times:")
        print(f"    Mean: {stats['response_times']['mean']:.4f}s")
        print(f"    P95: {stats['response_times']['p95']:.4f}s")
        print(f"    P99: {stats['response_times']['p99']:.4f}s")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Realistic sustained performance targets
        actual_rate = stats["total_requests"] / duration_seconds
        assert actual_rate >= requests_per_second * 0.80  # At least 80% of target rate
        assert stats["response_times"]["p95"] < 8.0  # P95 under 8 seconds
        assert stats["successful_requests"] / stats["total_requests"] >= 0.85  # 85% success rate
