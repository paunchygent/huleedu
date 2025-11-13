"""
Single request performance baseline tests using real infrastructure.

Tests individual request performance with real Redis and Kafka infrastructure
to establish meaningful baseline metrics. Uses mock LLM providers to avoid API costs.
"""

from __future__ import annotations

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
from services.llm_provider_service.internal_models import LLMQueuedResult
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
        """Test single request queue acceptance performance baseline with real infrastructure.

        Measures the performance of successfully queuing a request, not end-to-end processing.
        Success criteria: request is accepted and queued with proper LLMQueuedResult response.
        """
        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        # Measure queue acceptance performance
        start_time = time.perf_counter()

        result = await orchestrator.perform_comparison(
            provider=LLMProviderType.MOCK,
            user_prompt="""Compare these essays

**Essay A (ID: test_a):**
Sample essay A content

**Essay B (ID: test_b):**
Sample essay B content""",
            correlation_id=uuid4(),
            callback_topic="test_callback_topic",
            model="mock-model",
        )

        response_time = time.perf_counter() - start_time

        # Assert successful queueing (async-only architecture)
        assert isinstance(result, LLMQueuedResult)
        assert result.status == "queued"
        assert result.queue_id is not None
        assert result.correlation_id is not None
        assert result.provider == LLMProviderType.MOCK

        # Performance assertions for queue acceptance
        assert response_time < 2.0  # Queue acceptance should be under 2s

        print(f"Queue acceptance performance (real infrastructure): {response_time:.4f}s")
        print(f"Queued with ID: {result.queue_id}")
        print("Infrastructure: Real Kafka + Redis (testcontainers)")

    @pytest.mark.asyncio
    async def test_multiple_sequential_requests(self, infrastructure_di_container: Any) -> None:
        """Test queue acceptance consistency across multiple sequential requests.

        Measures the performance of successfully queuing multiple requests sequentially.
        Success criteria: all requests are accepted and queued with consistent timing.
        """
        request_count = 5  # Reduced for real infrastructure
        response_times = []
        queued_results = []

        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

        # Make sequential requests and measure queue acceptance
        for i in range(request_count):
            start_time = time.perf_counter()

            result = await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,
                user_prompt=f"""Compare these essays

**Essay A (ID: test_a_{i}):**
Sample essay A content {i}

**Essay B (ID: test_b_{i}):**
Sample essay B content {i}""",
                correlation_id=uuid4(),
                callback_topic=f"test_callback_topic_{i}",
                model="mock-model",
            )

            response_time = time.perf_counter() - start_time
            response_times.append(response_time)
            queued_results.append(result)

            # Verify each request is successfully queued
            assert isinstance(result, LLMQueuedResult)
            assert result.status == "queued"
            assert result.queue_id is not None
            assert result.provider == LLMProviderType.MOCK

        # Analyze queue acceptance performance consistency
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        success_rate = len([r for r in queued_results if r.status == "queued"]) / request_count

        print("Sequential queue acceptance performance (real infrastructure):")
        print(f"  Requests: {request_count}")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Average: {avg_time:.4f}s")
        print(f"  Min: {min_time:.4f}s")
        print(f"  Max: {max_time:.4f}s")
        print(f"  Variance: {max_time - min_time:.4f}s")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Performance assertions for queue acceptance consistency
        assert success_rate == 1.0  # All requests should be successfully queued
        assert avg_time < 2.5  # Average queue acceptance should be under 2.5s
        assert max_time < 5.0  # No queue acceptance should take more than 5s
        assert (max_time - min_time) < 3.0  # Variance should be reasonable

    @pytest.mark.asyncio
    async def test_infrastructure_overhead_analysis(self, infrastructure_di_container: Any) -> None:
        """Analyze infrastructure overhead for queue acceptance with real Redis and Kafka.

        Measures the minimal overhead of queue acceptance operations after warmup.
        Success criteria: consistent queue acceptance with minimal infrastructure overhead.
        """
        async with infrastructure_di_container() as request_container:
            orchestrator = await request_container.get(LLMOrchestratorProtocol)

            # Warm up (eliminate cold start effects)
            warmup_result = await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,
                user_prompt="""Warmup

**Essay A (ID: warmup_a):**
Warmup A

**Essay B (ID: warmup_b):**
Warmup B""",
                correlation_id=uuid4(),
                callback_topic="warmup_topic",
                model="mock-model",
            )
            # Verify warmup succeeded
            assert isinstance(warmup_result, LLMQueuedResult)
            assert warmup_result.status == "queued"

        # Measure minimal queue acceptance overhead
        overhead_measurements = []
        queued_results = []

        for _ in range(5):
            start_time = time.perf_counter()

            result = await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,
                user_prompt="""Test

**Essay A (ID: test_a):**
A

**Essay B (ID: test_b):**
B""",
                correlation_id=uuid4(),
                callback_topic="overhead_test_topic",
                model="mock-model",
            )

            overhead_time = time.perf_counter() - start_time
            overhead_measurements.append(overhead_time)
            queued_results.append(result)

            # Verify successful queueing
            assert isinstance(result, LLMQueuedResult)
            assert result.status == "queued"

        avg_overhead = sum(overhead_measurements) / len(overhead_measurements)
        min_overhead = min(overhead_measurements)
        success_rate = len([r for r in queued_results if r.status == "queued"]) / len(
            queued_results
        )

        print("Infrastructure overhead analysis for queue acceptance (real infrastructure):")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Average overhead: {avg_overhead:.6f}s")
        print(f"  Minimum overhead: {min_overhead:.6f}s")
        print(f"  Overhead measurements: {[f'{t:.6f}' for t in overhead_measurements]}")
        print("  Infrastructure: Real Kafka + Redis (testcontainers)")

        # Performance assertions for queue acceptance overhead
        assert success_rate == 1.0  # All requests should be successfully queued
        assert avg_overhead < 3.0  # Average queue acceptance overhead should be under 3s
        assert min_overhead < 1.0  # Minimum queue acceptance should be under 1s
