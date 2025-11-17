"""
Infrastructure performance tests using testcontainers.

Tests realistic performance with controlled Redis and Kafka infrastructure while keeping
LLM providers mocked to avoid API costs. Uses testcontainers for deterministic,
isolated infrastructure testing.

Focuses on infrastructure capacity metrics: queue acceptance rates, Redis/Kafka throughput,
and concurrent request handling capacity rather than end-to-end processing completion.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Any, AsyncGenerator, Dict, Generator, Tuple
from uuid import UUID, uuid4

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
        # Always use performance-optimized mock providers for infrastructure performance tests
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
    # Construct Redis URL from container host and exposed port
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
    """DI container with proper lifecycle management for infrastructure testing."""
    # Create test provider with infrastructure settings
    test_provider = LLMProviderServiceTestProvider(infrastructure_settings)

    # Create container
    container = make_async_container(test_provider)

    try:
        yield container
    finally:
        # Explicitly close all app-scoped dependencies to prevent resource leaks
        async with container() as request_container:
            try:
                # Get and cleanup Kafka bus (the actual implementation behind the protocol)
                from huleedu_service_libs.kafka_client import KafkaBus

                kafka_bus = await request_container.get(KafkaBus)
                if hasattr(kafka_bus, "stop"):
                    await kafka_bus.stop()
                    print("✓ Kafka bus stopped cleanly")
            except Exception as e:
                print(f"⚠ Failed to stop Kafka bus: {e}")

            try:
                # Get and cleanup queue Redis client
                from huleedu_service_libs.queue_protocols import QueueRedisClientProtocol

                queue_redis_client = await request_container.get(QueueRedisClientProtocol)
                if hasattr(queue_redis_client, "stop"):
                    await queue_redis_client.stop()
                    print("✓ Queue Redis client stopped cleanly")
            except Exception as e:
                print(f"⚠ Failed to stop queue Redis client: {e}")

            try:
                # Get and cleanup general Redis client
                from huleedu_service_libs.protocols import RedisClientProtocol

                redis_client = await request_container.get(RedisClientProtocol)
                if hasattr(redis_client, "stop"):
                    await redis_client.stop()
                    print("✓ Redis client stopped cleanly")
            except Exception as e:
                print(f"⚠ Failed to stop Redis client: {e}")

            try:
                # Get and cleanup connection pool manager
                from services.llm_provider_service.implementations.connection_pool_manager_impl import (  # noqa: E501
                    ConnectionPoolManagerImpl,
                )

                pool_manager = await request_container.get(ConnectionPoolManagerImpl)
                if hasattr(pool_manager, "cleanup"):
                    await pool_manager.cleanup()
                    print("✓ Connection pool manager cleaned up")
            except Exception as e:
                print(f"⚠ Failed to cleanup connection pool manager: {e}")


class TestInfrastructurePerformance:
    """Performance tests with real infrastructure containers using testcontainers."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.performance
    async def test_realistic_single_request_performance(
        self, infrastructure_di_container: Any
    ) -> None:
        """Test single request queue acceptance performance with real Redis and Kafka.

        Measures infrastructure overhead for queue acceptance using controlled testcontainers.
        Success criteria: request is accepted and queued with proper LLMQueuedResult response.
        """
        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import LLMOrchestratorProtocol

            orchestrator = await request_container.get(LLMOrchestratorProtocol)

            # Measure queue acceptance performance with real infrastructure
            start_time = time.perf_counter()

            result = await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,  # Mock provider to avoid API costs
                user_prompt="""Compare these two essays for infrastructure testing

**Essay A (ID: test_a):**
Sample essay A content for infrastructure testing

**Essay B (ID: test_b):**
Sample essay B content for infrastructure testing""",
                correlation_id=uuid4(),
                callback_topic="test.callback.topic",
                model="mock-model",
            )

            response_time = time.perf_counter() - start_time

            # Assert successful queueing (async-only architecture)
            assert isinstance(result, LLMQueuedResult)
            assert result.status == "queued"
            assert result.queue_id is not None
            assert result.correlation_id is not None
            assert result.provider == LLMProviderType.MOCK

            # Performance targets for real infrastructure queue acceptance
            assert response_time < 2.0  # Queue acceptance should be under 2 seconds

            print(f"Infrastructure queue acceptance performance: {response_time:.4f}s")
            print(f"Queued with ID: {result.queue_id}")
            print("  Infrastructure: Real Kafka + Redis (testcontainers)")
            print("  Provider: Mock (no API costs)")

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.performance
    async def test_realistic_concurrent_requests_performance(
        self, infrastructure_di_container: Any
    ) -> None:
        """Test concurrent queue acceptance performance with real Redis and Kafka infrastructure.

        Tests realistic concurrent load on infrastructure capacity with controlled testcontainers.
        Success criteria: measures infrastructure queue acceptance rates under concurrent load.
        """
        concurrent_requests = 20  # Appropriate load for real infrastructure

        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import LLMOrchestratorProtocol

            orchestrator = await request_container.get(LLMOrchestratorProtocol)

            async def make_request(request_id: int) -> Tuple[float, bool, LLMQueuedResult | None]:
                """Make a single request and return response time, success, and queue result."""
                start_time = time.perf_counter()

                try:
                    result = await orchestrator.perform_comparison(
                        provider=LLMProviderType.MOCK,  # Mock to avoid API costs
                        user_prompt=f"""Compare these essays for infrastructure test {request_id}

**Essay A (ID: test_a_{request_id}):**
Infrastructure test essay A {request_id}

**Essay B (ID: test_b_{request_id}):**
Infrastructure test essay B {request_id}""",
                        correlation_id=uuid4(),
                        callback_topic=f"test.callback.topic.{request_id}",
                        model="mock-model",
                    )

                    response_time = time.perf_counter() - start_time
                    is_success = isinstance(result, LLMQueuedResult) and result.status == "queued"
                    return response_time, is_success, result if is_success else None
                except Exception:
                    response_time = time.perf_counter() - start_time
                    return response_time, False, None

            # Run concurrent requests
            start_time = time.perf_counter()

            tasks = [make_request(i) for i in range(concurrent_requests)]
            results = await asyncio.gather(*tasks)

            total_time = time.perf_counter() - start_time

            # Analyze queue acceptance results
            response_times = [r[0] for r in results]
            successes = [r[1] for r in results]
            queued_results = [r[2] for r in results if r[2] is not None]

            p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
            success_rate = sum(successes) / len(successes) * 100
            queue_acceptance_rate = len(queued_results) / concurrent_requests * 100

            print("Infrastructure concurrent queue acceptance performance:")
            print(f"  Total requests: {concurrent_requests}")
            print(f"  Queued requests: {len(queued_results)}")
            print(f"  Queue acceptance rate: {queue_acceptance_rate:.1f}%")
            print(f"  Total time: {total_time:.4f}s")
            print(f"  Queue throughput: {concurrent_requests / total_time:.2f} requests/sec")
            print(f"  Success rate: {success_rate:.1f}%")
            print(f"  P95 queue acceptance time: {p95_time:.4f}s")
            print(f"  Mean queue acceptance time: {statistics.mean(response_times):.4f}s")
            print("  Infrastructure: Real Kafka + Redis")

            # Assertions for infrastructure queue acceptance performance
            assert queue_acceptance_rate >= 90  # At least 90% queue acceptance rate
            assert p95_time < 5.0  # P95 queue acceptance should be under 5 seconds
            assert statistics.mean(response_times) < 2.0  # Mean queue acceptance under 2 seconds

    @pytest.mark.asyncio
    async def test_queue_resilience_with_real_redis(self, infrastructure_di_container: Any) -> None:
        """Test queue performance with real Redis infrastructure.

        Tests queue operations performance with controlled Redis testcontainer.
        """
        from datetime import datetime, timedelta, timezone

        from common_core import LLMComparisonRequest, QueueStatus

        from services.llm_provider_service.queue_models import QueuedRequest

        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import QueueManagerProtocol

            queue_manager = await request_container.get(QueueManagerProtocol)

            # Create test requests
            requests = []
            for i in range(10):
                request_data = LLMComparisonRequest(
                    user_prompt=f"""Compare these essays

**Essay A (ID: test_a_{i}):**
Queue test essay A {i}

**Essay B (ID: test_b_{i}):**
Queue test essay B {i}""",
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
                    size_bytes=len(f"Queue test essay A {i}") + len(f"Queue test essay B {i}"),
                    callback_topic="test.callback.topic",
                )
                requests.append(request)

            # Measure queue operations
            start_time = time.perf_counter()

            # Add requests to queue
            for request in requests:
                success = await queue_manager.enqueue(request)
                assert success, f"Failed to queue request {request.queue_id}"

            queue_add_time = time.perf_counter() - start_time

            # Measure queue retrieval
            start_time = time.perf_counter()

            retrieved_requests = []
            for _ in range(len(requests)):
                next_request = await queue_manager.dequeue()
                if next_request:
                    retrieved_requests.append(next_request)

            queue_retrieval_time = time.perf_counter() - start_time

            print("Queue performance with real Redis (testcontainer):")
            print(f"  Queue add time: {queue_add_time:.4f}s for {len(requests)} requests")
            print(f"  Average add time: {queue_add_time / len(requests):.6f}s per request")
            print(
                f"  Queue retrieval time: {queue_retrieval_time:.4f}s "
                f"for {len(retrieved_requests)} requests"
            )
            print(
                f"  Average retrieval time: "
                f"{queue_retrieval_time / len(retrieved_requests):.6f}s per request"
            )

            # Assertions for real Redis performance
            assert len(retrieved_requests) == len(requests)
            assert queue_add_time / len(requests) < 0.1  # Under 100ms per add
            assert queue_retrieval_time / len(retrieved_requests) < 0.1  # Under 100ms per retrieval

    @pytest.mark.asyncio
    async def test_event_publishing_performance(self, infrastructure_di_container: Any) -> None:
        """Test Kafka event publishing performance with real infrastructure.

        Tests event publishing performance with controlled Kafka testcontainer.
        """
        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import LLMEventPublisherProtocol

            event_publisher = await request_container.get(LLMEventPublisherProtocol)

            # Test event publishing performance
            event_count = 10
            start_time = time.perf_counter()

            for i in range(event_count):
                await event_publisher.publish_llm_request_completed(
                    provider=LLMProviderType.MOCK.value,
                    correlation_id=UUID(f"00000000-0000-0000-0000-{i:012d}"),
                    success=True,
                    response_time_ms=100 + i,
                    metadata={
                        "request_type": "comparison",
                        "model": "mock-model",
                        "result": {
                            "winner": "Essay A",
                            "justification": f"Performance test justification {i}",
                            "confidence": 4.0 + (i % 10) / 10,
                        },
                    },
                )

            publishing_time = time.perf_counter() - start_time

            print("Kafka event publishing performance (testcontainer):")
            print(f"  Published {event_count} events in {publishing_time:.4f}s")
            print(f"  Average time per event: {publishing_time / event_count:.6f}s")
            print(f"  Events per second: {event_count / publishing_time:.2f}")
            print("  Infrastructure: Real Kafka")

            # Assertions for real Kafka performance
            assert publishing_time / event_count < 0.5  # Under 500ms per event
            assert event_count / publishing_time > 1  # At least 1 event per second

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.performance
    async def test_end_to_end_infrastructure_load(self, infrastructure_di_container: Any) -> None:
        """Test complete infrastructure load capacity with real Redis and Kafka.

        Tests infrastructure queue acceptance capacity under concurrent load.
        Success criteria: measures queue acceptance rates and infrastructure throughput limits.
        """
        request_count = 15  # Moderate load for infrastructure capacity test

        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import LLMOrchestratorProtocol

            orchestrator = await request_container.get(LLMOrchestratorProtocol)

            # Run infrastructure load test
            start_time = time.perf_counter()

            tasks = []
            for i in range(request_count):

                async def make_e2e_request(
                    request_id: int,
                ) -> Tuple[float, bool, LLMQueuedResult | None]:
                    start = time.perf_counter()
                    try:
                        prompt = f"""Compare these essays for infrastructure load test {request_id}

**Essay A (ID: test_a_{request_id}):**
Infrastructure load test essay A {request_id}

**Essay B (ID: test_b_{request_id}):**
Infrastructure load test essay B {request_id}"""
                        result = await orchestrator.perform_comparison(
                            provider=LLMProviderType.MOCK,
                            user_prompt=prompt,
                            correlation_id=uuid4(),
                            callback_topic=f"test.e2e.callback.topic.{request_id}",
                            model="mock-model",
                        )
                        duration = time.perf_counter() - start
                        is_success = (
                            isinstance(result, LLMQueuedResult) and result.status == "queued"
                        )
                        return duration, is_success, result if is_success else None
                    except Exception:
                        duration = time.perf_counter() - start
                        return duration, False, None

                tasks.append(make_e2e_request(i))

            # Execute all requests concurrently
            results = await asyncio.gather(*tasks)

            total_time = time.perf_counter() - start_time

            # Analyze infrastructure load results
            response_times = [r[0] for r in results]
            successes = [r[1] for r in results]
            queued_results = [r[2] for r in results if r[2] is not None]

            success_count = sum(successes)
            success_rate = success_count / len(successes) * 100
            queue_acceptance_rate = len(queued_results) / request_count * 100
            p95_time = sorted(response_times)[int(len(response_times) * 0.95)]

            print("Infrastructure load capacity test (testcontainers):")
            print(f"  Total requests: {request_count}")
            print(f"  Queued requests: {len(queued_results)}")
            print(f"  Queue acceptance rate: {queue_acceptance_rate:.1f}%")
            print(f"  Success rate: {success_rate:.1f}%")
            print(f"  Total time: {total_time:.4f}s")
            print(f"  Infrastructure throughput: {request_count / total_time:.2f} requests/sec")
            print(f"  P95 queue acceptance time: {p95_time:.4f}s")
            print(f"  Mean queue acceptance time: {statistics.mean(response_times):.4f}s")
            print("  Infrastructure: Real Kafka + Redis (testcontainers)")
            print("  LLM Provider: Mock (no API costs)")

            # Infrastructure capacity performance targets
            assert queue_acceptance_rate >= 85  # At least 85% queue acceptance rate
            assert p95_time < 10.0  # P95 queue acceptance under 10 seconds
            assert statistics.mean(response_times) < 3.0  # Mean queue acceptance under 3 seconds
