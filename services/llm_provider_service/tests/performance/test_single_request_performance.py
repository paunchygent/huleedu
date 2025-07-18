"""
Single request performance baseline tests using real infrastructure.

Tests individual request performance with real Redis and Kafka infrastructure
to establish meaningful baseline metrics. Uses mock LLM providers to avoid API costs.
"""

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
    """DI container with real infrastructure for single request performance testing."""
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


class TestSingleRequestPerformance:
    """Tests for single request performance baseline with real infrastructure."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.performance
    async def test_single_request_performance(self, infrastructure_di_container: Any) -> None:
        """Test single request performance baseline with real infrastructure."""
        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        # Measure single request performance
        start_time = time.perf_counter()

        result = await orchestrator.perform_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="Compare these essays",
            essay_a="Sample essay A content",
            essay_b="Sample essay B content",
            correlation_id=uuid4(),
            model="mock-model",
        )

        response_time = time.perf_counter() - start_time

        # Realistic assertions for single request with real infrastructure
        assert result is not None
        assert response_time < 2.0  # Should be under 2s for real infrastructure

        print(f"Single request performance (real infrastructure): {response_time:.4f}s")
        print("Infrastructure: Real Kafka + Redis (testcontainers)")

    @pytest.mark.asyncio
    async def test_multiple_sequential_requests(self, infrastructure_di_container: Any) -> None:
        """Test performance consistency across multiple sequential requests
        with real infrastructure."""
        request_count = 5  # Reduced for real infrastructure
        response_times = []

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        # Make sequential requests
        for i in range(request_count):
            start_time = time.perf_counter()

            result = await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,
                user_prompt="Compare these essays",
                essay_a=f"Sample essay A content {i}",
                essay_b=f"Sample essay B content {i}",
                correlation_id=uuid4(),
                model="mock-model",
            )

            response_time = time.perf_counter() - start_time
            response_times.append(response_time)

            # Verify each request succeeds
            assert result is not None

        # Analyze performance consistency
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        min_time = min(response_times)

        print("Sequential requests performance (real infrastructure):")
        print(f"  Requests: {request_count}")
        print(f"  Average: {avg_time:.4f}s")
        print(f"  Min: {min_time:.4f}s")
        print(f"  Max: {max_time:.4f}s")
        print(f"  Variance: {max_time - min_time:.4f}s")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Realistic assertions for consistency with real infrastructure
        assert avg_time < 2.5  # Average should be under 2.5s
        assert max_time < 5.0  # No request should take more than 5s
        assert (max_time - min_time) < 3.0  # Variance should be reasonable

    @pytest.mark.asyncio
    async def test_infrastructure_overhead_analysis(self, infrastructure_di_container: Any) -> None:
        """Analyze infrastructure overhead with real Redis and Kafka."""
        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

            # Warm up (eliminate cold start effects)
            await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,
                user_prompt="Warmup",
                essay_a="Warmup A",
                essay_b="Warmup B",
                correlation_id=uuid4(),
                model="mock-model",
            )

        # Measure minimal overhead
        overhead_measurements = []
        for _ in range(5):
            start_time = time.perf_counter()

            result = await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,
                user_prompt="Test",
                essay_a="A",
                essay_b="B",
                correlation_id=uuid4(),
                model="mock-model",
            )

            overhead_time = time.perf_counter() - start_time
            overhead_measurements.append(overhead_time)
            assert result is not None

        avg_overhead = sum(overhead_measurements) / len(overhead_measurements)
        min_overhead = min(overhead_measurements)

        print("Infrastructure overhead analysis (real infrastructure):")
        print(f"  Average overhead: {avg_overhead:.6f}s")
        print(f"  Minimum overhead: {min_overhead:.6f}s")
        print(f"  Overhead measurements: {[f'{t:.6f}' for t in overhead_measurements]}")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Realistic assertions for infrastructure overhead
        assert avg_overhead < 3.0  # Average overhead should be under 3s for real infrastructure
        assert min_overhead < 1.0  # Minimum should be under 1s
