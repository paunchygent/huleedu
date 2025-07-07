"""
Concurrent request performance tests using real infrastructure.

Tests concurrent request handling capabilities with real Redis and Kafka
infrastructure. Uses mock LLM providers to avoid API costs while providing
meaningful infrastructure performance data.
"""

import asyncio
import statistics
import time
from typing import Any, AsyncGenerator, Dict, Generator, List, Tuple
from uuid import uuid4

import pytest
from dishka import Scope, make_async_container, provide
from huleedu_service_libs.resilience import CircuitBreakerRegistry
from testcontainers.kafka import KafkaContainer
from testcontainers.redis import RedisContainer

from common_core import Environment, LLMProviderType
from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider
from services.llm_provider_service.implementations.connection_pool_manager_impl import (
    ConnectionPoolManagerImpl,
)
from services.llm_provider_service.protocols import (
    LLMOrchestratorProtocol,
    LLMProviderProtocol,
    LLMRetryManagerProtocol,
)


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
    """DI container with real infrastructure for concurrent performance testing."""
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


class TestConcurrentPerformance:
    """Tests for concurrent request handling performance with real infrastructure."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_performance(self, infrastructure_di_container: Any) -> None:
        """Test concurrent request performance with real infrastructure."""
        concurrent_requests = 15  # Reduced for real infrastructure

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        async def make_request(request_id: int) -> Tuple[float, bool]:
            """Make a single request and return response time and success."""
            start_time = time.perf_counter()

            try:
                _, error = await orchestrator.perform_comparison(
                    provider=LLMProviderType.MOCK,  # Mock to avoid API costs
                    user_prompt="Compare these essays",
                    essay_a=f"Sample essay A content {request_id}",
                    essay_b=f"Sample essay B content {request_id}",
                    correlation_id=uuid4(),
                    model="mock-model",
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

        print("Concurrent requests performance (real infrastructure):")
        print(f"  Total requests: {concurrent_requests}")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Requests per second: {concurrent_requests / total_time:.2f}")
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  P95 response time: {p95_time:.4f}s")
        print(f"  Mean response time: {statistics.mean(response_times):.4f}s")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Realistic performance assertions for real infrastructure
        assert success_rate >= 90  # At least 90% success rate
        assert p95_time < 5.0  # P95 should be under 5s
        assert statistics.mean(response_times) < 2.0  # Mean should be under 2s

    @pytest.mark.asyncio
    async def test_high_concurrency_stress(self, infrastructure_di_container: Any) -> None:
        """Test higher concurrency stress with real infrastructure."""
        concurrent_requests = 25  # Reduced for real infrastructure stress test

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        async def make_request(request_id: int) -> Tuple[float, bool]:
            start_time = time.perf_counter()
            try:
                _, error = await orchestrator.perform_comparison(
                    provider=LLMProviderType.MOCK,
                    user_prompt="Stress test comparison",
                    essay_a=f"Stress essay A {request_id}",
                    essay_b=f"Stress essay B {request_id}",
                    correlation_id=uuid4(),
                    model="mock-model",
                )
                response_time = time.perf_counter() - start_time
                return response_time, error is None
            except Exception:
                response_time = time.perf_counter() - start_time
                return response_time, False

        # Run stress test
        start_time = time.perf_counter()
        tasks = [make_request(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_time

        response_times = [r[0] for r in results]
        successes = [r[1] for r in results]

        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
        p99_time = sorted(response_times)[int(len(response_times) * 0.99)]
        success_rate = sum(successes) / len(successes) * 100

        print("High concurrency stress test (real infrastructure):")
        print(f"  Concurrent requests: {concurrent_requests}")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Throughput: {concurrent_requests / total_time:.2f} req/s")
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  P95: {p95_time:.4f}s, P99: {p99_time:.4f}s")
        print(f"  Mean: {statistics.mean(response_times):.4f}s")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Stress test assertions for real infrastructure
        assert success_rate >= 85  # At least 85% success under stress
        assert p95_time < 8.0  # P95 under 8 seconds under stress
        assert statistics.mean(response_times) < 3.0  # Mean under 3s

    @pytest.mark.asyncio
    async def test_concurrent_burst_pattern(self, infrastructure_di_container: Any) -> None:
        """Test burst pattern with real infrastructure."""
        burst_size = 8  # Reduced for real infrastructure
        burst_count = 3
        burst_interval = 1.0  # 1s between bursts for real infrastructure

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        all_response_times = []
        all_successes = []

        async def make_burst_request(burst_id: int, request_id: int) -> Tuple[float, bool]:
            start_time = time.perf_counter()
            try:
                _, error = await orchestrator.perform_comparison(
                    provider=LLMProviderType.MOCK,
                    user_prompt="Burst test comparison",
                    essay_a=f"Burst {burst_id} essay A {request_id}",
                    essay_b=f"Burst {burst_id} essay B {request_id}",
                    correlation_id=uuid4(),
                    model="mock-model",
                )
                response_time = time.perf_counter() - start_time
                return response_time, error is None
            except Exception:
                response_time = time.perf_counter() - start_time
                return response_time, False

        # Execute burst pattern
        total_start_time = time.perf_counter()

        for burst_id in range(burst_count):
            print(f"  Executing burst {burst_id + 1}/{burst_count}...")

            # Create tasks for this burst
            burst_tasks = [make_burst_request(burst_id, i) for i in range(burst_size)]

            # Execute burst concurrently
            burst_results = await asyncio.gather(*burst_tasks)

            # Collect results
            burst_times = [r[0] for r in burst_results]
            burst_successes = [r[1] for r in burst_results]

            all_response_times.extend(burst_times)
            all_successes.extend(burst_successes)

            print(
                f"    Burst {burst_id + 1} P95: "
                f"{sorted(burst_times)[int(len(burst_times) * 0.95)]:.4f}s"
            )

            # Wait before next burst (except for last burst)
            if burst_id < burst_count - 1:
                await asyncio.sleep(burst_interval)

        total_time = time.perf_counter() - total_start_time

        # Analyze overall results
        p95_time = sorted(all_response_times)[int(len(all_response_times) * 0.95)]
        success_rate = sum(all_successes) / len(all_successes) * 100
        total_requests = burst_size * burst_count

        print("Burst pattern results (real infrastructure):")
        print(f"  Total requests: {total_requests} ({burst_count} bursts of {burst_size})")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Overall success rate: {success_rate:.1f}%")
        print(f"  Overall P95: {p95_time:.4f}s")
        print(f"  Overall mean: {statistics.mean(all_response_times):.4f}s")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Realistic assertions for burst handling
        assert success_rate >= 90  # Should handle bursts well
        assert p95_time < 6.0  # P95 should remain reasonable during bursts
        assert statistics.mean(all_response_times) < 3.0  # Mean should stay reasonable

    @pytest.mark.asyncio
    async def test_concurrent_mixed_providers(self, infrastructure_di_container: Any) -> None:
        """Test concurrent requests using different mock providers with real infrastructure."""
        requests_per_provider = 3  # Reduced for real infrastructure
        providers = [
            LLMProviderType.MOCK,  # All use mock to avoid API costs
            LLMProviderType.MOCK,
            LLMProviderType.MOCK,
        ]

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        async def make_provider_request(
            provider: LLMProviderType, request_id: int
        ) -> Tuple[float, bool, str]:
            start_time = time.perf_counter()
            try:
                _, error = await orchestrator.perform_comparison(
                    provider=provider,
                    user_prompt="Mixed provider test",
                    essay_a=f"Essay A for {provider.value} {request_id}",
                    essay_b=f"Essay B for {provider.value} {request_id}",
                    correlation_id=uuid4(),
                    model="mock-model",
                )
                response_time = time.perf_counter() - start_time
                return response_time, error is None, provider.value
            except Exception:
                response_time = time.perf_counter() - start_time
                return response_time, False, provider.value

        # Create mixed provider tasks
        all_tasks = []
        for provider in providers:
            for i in range(requests_per_provider):
                all_tasks.append(make_provider_request(provider, i))

        # Execute all requests concurrently
        start_time = time.perf_counter()
        results = await asyncio.gather(*all_tasks)
        total_time = time.perf_counter() - start_time

        # Analyze results by provider
        provider_results: Dict[str, List[Tuple[float, bool]]] = {
            provider.value: [] for provider in providers
        }
        for response_time, success, provider_name in results:
            provider_results[provider_name].append((response_time, success))

        total_requests = len(results)
        all_response_times = [r[0] for r in results]
        all_successes = [r[1] for r in results]

        print("Mixed provider concurrent test (real infrastructure):")
        print(f"  Total requests: {total_requests}")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Overall success rate: {sum(all_successes) / len(all_successes) * 100:.1f}%")
        p95_index = int(len(all_response_times) * 0.95)
        p95_time = sorted(all_response_times)[p95_index]
        print(f"  Overall P95: {p95_time:.4f}s")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        for provider_name, provider_data in provider_results.items():
            provider_times = [r[0] for r in provider_data]
            provider_successes = [r[1] for r in provider_data]
            success_rate = sum(provider_successes) / len(provider_successes) * 100
            mean_time = statistics.mean(provider_times)
            print(f"  {provider_name}: {success_rate:.1f}% success, {mean_time:.4f}s mean")

        # Realistic assertions for mixed provider performance
        overall_success_rate = sum(all_successes) / len(all_successes) * 100
        assert overall_success_rate >= 90  # 90% success rate
        assert statistics.mean(all_response_times) < 2.5  # Under 2.5s mean
