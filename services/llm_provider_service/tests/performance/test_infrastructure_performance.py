"""
Infrastructure performance tests using testcontainers.

Tests realistic performance with controlled Redis and Kafka infrastructure while keeping
LLM providers mocked to avoid API costs. Uses testcontainers for deterministic,
isolated infrastructure testing.
"""

import asyncio
import statistics
import time
from typing import Any, AsyncGenerator, Dict, Generator, Tuple
from uuid import UUID, uuid4

import pytest
from dishka import Scope, make_async_container, provide
from testcontainers.kafka import KafkaContainer
from testcontainers.redis import RedisContainer

from common_core import Environment, EssayComparisonWinner, LLMProviderType
from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider


class TestLLMProviderServiceProvider(LLMProviderServiceProvider):
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
    test_provider = TestLLMProviderServiceProvider(infrastructure_settings)

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
                from services.llm_provider_service.implementations.connection_pool_manager_impl import (
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
    async def test_realistic_single_request_performance(
        self, infrastructure_di_container: Any
    ) -> None:
        """Test single request performance with real Redis and Kafka infrastructure.

        Measures actual infrastructure overhead using controlled testcontainers.
        """
        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import LLMOrchestratorProtocol

            orchestrator = await request_container.get(LLMOrchestratorProtocol)

            # Measure single request performance with real infrastructure
            start_time = time.perf_counter()

            result, error = await orchestrator.perform_comparison(
                provider=LLMProviderType.MOCK,  # Mock provider to avoid API costs
                user_prompt="Compare these two essays for infrastructure testing",
                essay_a="Sample essay A content for infrastructure testing",
                essay_b="Sample essay B content for infrastructure testing",
                correlation_id=uuid4(),
                model="mock-model",
            )

            response_time = time.perf_counter() - start_time

            # Assertions for infrastructure performance
            assert error is None, f"Request failed: {error}"
            assert result is not None
            assert result.winner in [EssayComparisonWinner.ESSAY_A, EssayComparisonWinner.ESSAY_B]

            # Performance targets for real infrastructure
            assert response_time < 2.0  # Should be under 2 seconds with real infrastructure

            print(f"Realistic single request performance: {response_time:.4f}s")
            print("  Infrastructure: Real Kafka + Redis (testcontainers)")
            print("  Provider: Mock (no API costs)")

    @pytest.mark.asyncio
    async def test_realistic_concurrent_requests_performance(
        self, infrastructure_di_container: Any
    ) -> None:
        """Test concurrent request performance with real Redis and Kafka infrastructure.

        Tests realistic concurrent load with controlled testcontainers.
        """
        concurrent_requests = 20  # Appropriate load for real infrastructure

        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import LLMOrchestratorProtocol

            orchestrator = await request_container.get(LLMOrchestratorProtocol)

            async def make_request(request_id: int) -> Tuple[float, bool]:
                """Make a single request and return response time and success."""
                start_time = time.perf_counter()

                try:
                    result, error = await orchestrator.perform_comparison(
                        provider=LLMProviderType.MOCK,  # Mock to avoid API costs
                        user_prompt=f"Compare these essays for infrastructure test {request_id}",
                        essay_a=f"Infrastructure test essay A {request_id}",
                        essay_b=f"Infrastructure test essay B {request_id}",
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

            print("Realistic concurrent requests performance:")
            print(f"  Total requests: {concurrent_requests}")
            print(f"  Total time: {total_time:.4f}s")
            print(f"  Requests per second: {concurrent_requests / total_time:.2f}")
            print(f"  Success rate: {success_rate:.1f}%")
            print(f"  P95 response time: {p95_time:.4f}s")
            print(f"  Mean response time: {statistics.mean(response_times):.4f}s")
            print("  Infrastructure: Real Kafka + Redis")

            # Assertions for real infrastructure performance
            assert success_rate >= 90  # At least 90% success rate
            assert p95_time < 5.0  # P95 should be under 5 seconds with real infrastructure
            assert statistics.mean(response_times) < 2.0  # Mean should be under 2 seconds

    @pytest.mark.asyncio
    async def test_queue_resilience_with_real_redis(self, infrastructure_di_container: Any) -> None:
        """Test queue performance with real Redis infrastructure.

        Tests queue operations performance with controlled Redis testcontainer.
        """
        from datetime import datetime, timedelta, timezone

        from common_core import QueueStatus
        from services.llm_provider_service.api_models import LLMComparisonRequest
        from services.llm_provider_service.queue_models import QueuedRequest

        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import QueueManagerProtocol

            queue_manager = await request_container.get(QueueManagerProtocol)

            # Create test requests
            requests = []
            for i in range(10):
                request_data = LLMComparisonRequest(
                    user_prompt="Compare these essays",
                    essay_a=f"Queue test essay A {i}",
                    essay_b=f"Queue test essay B {i}",
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
    async def test_end_to_end_infrastructure_load(self, infrastructure_di_container: Any) -> None:
        """Test complete end-to-end load with real infrastructure.

        This is the most realistic performance test - measures the full stack
        with real Kafka and Redis but mock LLM providers.
        """
        request_count = 15  # Moderate load for end-to-end test

        async with infrastructure_di_container() as request_container:
            from services.llm_provider_service.protocols import LLMOrchestratorProtocol

            orchestrator = await request_container.get(LLMOrchestratorProtocol)

            # Run end-to-end load test
            start_time = time.perf_counter()

            tasks = []
            for i in range(request_count):

                async def make_e2e_request(request_id: int) -> Tuple[float, bool, Dict[str, Any]]:
                    start = time.perf_counter()
                    try:
                        result, error = await orchestrator.perform_comparison(
                            provider=LLMProviderType.MOCK,
                            user_prompt=f"Compare these essays for e2e test {request_id}",
                            essay_a=f"End-to-end test essay A {request_id}",
                            essay_b=f"End-to-end test essay B {request_id}",
                            correlation_id=uuid4(),
                            model="mock-model",
                        )
                        duration = time.perf_counter() - start
                        return duration, error is None, result or {}
                    except Exception as e:
                        duration = time.perf_counter() - start
                        return duration, False, {"error": str(e)}

                tasks.append(make_e2e_request(i))

            # Execute all requests concurrently
            results = await asyncio.gather(*tasks)

            total_time = time.perf_counter() - start_time

            # Analyze results
            response_times = [r[0] for r in results]
            successes = [r[1] for r in results]

            success_count = sum(successes)
            success_rate = success_count / len(successes) * 100
            p95_time = sorted(response_times)[int(len(response_times) * 0.95)]

            print("End-to-end infrastructure load test (testcontainers):")
            print(f"  Total requests: {request_count}")
            print(f"  Successful requests: {success_count}")
            print(f"  Success rate: {success_rate:.1f}%")
            print(f"  Total time: {total_time:.4f}s")
            print(f"  Throughput: {request_count / total_time:.2f} requests/sec")
            print(f"  P95 response time: {p95_time:.4f}s")
            print(f"  Mean response time: {statistics.mean(response_times):.4f}s")
            print("  Infrastructure: Real Kafka + Redis (testcontainers)")
            print("  LLM Provider: Mock (no API costs)")

            # Performance targets for real infrastructure
            assert success_rate >= 85  # At least 85% success rate
            assert p95_time < 10.0  # P95 under 10 seconds for full stack
            assert statistics.mean(response_times) < 3.0  # Mean under 3 seconds
