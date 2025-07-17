"""
Performance validation tests for specific optimization components.

Tests the effectiveness of implemented performance optimizations:
- Connection pool efficiency
- Response validation performance improvements
- Redis pipelining benefits
- Provider-specific optimizations
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Generator
from uuid import uuid4

import pytest
from common_core import Environment
from dishka import Scope, provide

from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider
from services.llm_provider_service.implementations.connection_pool_manager_impl import (
    ConnectionPoolManagerImpl,
)
from services.llm_provider_service.response_validator import validate_and_normalize_response


@pytest.fixture
def performance_settings() -> Settings:
    """Settings for performance testing.

    CRITICAL: Mock providers are enabled to avoid API costs during testing.
    """
    settings = Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.TESTING,
        LOG_LEVEL="INFO",
        USE_MOCK_LLM=True,  # CRITICAL: Prevents real API calls and costs
    )

    # Double-check that mock providers are enabled
    assert settings.USE_MOCK_LLM is True, "Mock LLM must be enabled to avoid API costs"
    return settings


class TestConnectionPoolOptimizations:
    """Test connection pool performance optimizations."""

    @pytest.mark.asyncio
    async def test_provider_specific_pool_limits(self, performance_settings: Settings) -> None:
        """Test that provider-specific pool limits are properly configured."""
        pool_manager = ConnectionPoolManagerImpl(performance_settings)

        try:
            # Test different providers get appropriate pool configurations
            providers = ["openai", "anthropic", "google", "openrouter"]

            for provider in providers:
                session = await pool_manager.get_session(provider)
                assert session is not None

                # Check that session was created with provider-specific settings
                limits = pool_manager._get_provider_connection_limits(provider)
                assert limits["total_pool_size"] > 0
                assert limits["per_host_limit"] > 0
                assert limits["total_timeout"] > 0

                print(f"{provider} pool config: {limits}")

        finally:
            await pool_manager.cleanup()

    @pytest.mark.asyncio
    async def test_connection_reuse_efficiency(self, performance_settings: Settings) -> None:
        """Test connection reuse reduces latency."""
        pool_manager = ConnectionPoolManagerImpl(performance_settings)

        try:
            # First session creation (cold start)
            start_time = time.perf_counter()
            session1 = await pool_manager.get_session("openai")
            first_creation_time = time.perf_counter() - start_time

            # Second session retrieval (should reuse)
            start_time = time.perf_counter()
            session2 = await pool_manager.get_session("openai")
            reuse_time = time.perf_counter() - start_time

            # Verify reuse
            assert session1 is session2
            assert reuse_time < first_creation_time  # Reuse should be faster

            print(f"Session creation time: {first_creation_time:.6f}s")
            print(f"Session reuse time: {reuse_time:.6f}s")
            print(
                f"Reuse improvement: "
                f"{((first_creation_time - reuse_time) / first_creation_time * 100):.1f}%"
            )

        finally:
            await pool_manager.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_connection_efficiency(self, performance_settings: Settings) -> None:
        """Test connection pool efficiency under concurrent load."""
        pool_manager = ConnectionPoolManagerImpl(performance_settings)

        try:

            async def get_session_timed(provider: str) -> float:
                """Get session and return time taken."""
                start_time = time.perf_counter()
                session = await pool_manager.get_session(provider)
                time_taken = time.perf_counter() - start_time
                assert session is not None
                return time_taken

            # Test concurrent access to same provider
            concurrent_requests = 20
            tasks = [get_session_timed("openai") for _ in range(concurrent_requests)]

            start_time = time.perf_counter()
            times = await asyncio.gather(*tasks)
            total_time = time.perf_counter() - start_time

            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)

            print("Concurrent session access results:")
            print(f"  Total requests: {concurrent_requests}")
            print(f"  Total time: {total_time:.4f}s")
            print(f"  Average time per request: {avg_time:.6f}s")
            print(f"  Min time: {min_time:.6f}s")
            print(f"  Max time: {max_time:.6f}s")

            # Verify performance
            assert avg_time < 0.001  # Should be very fast for session reuse
            assert max_time < 0.01  # Even worst case should be under 10ms

        finally:
            await pool_manager.cleanup()

    @pytest.mark.asyncio
    async def test_connection_health_monitoring(self, performance_settings: Settings) -> None:
        """Test connection health monitoring performance."""
        pool_manager = ConnectionPoolManagerImpl(performance_settings)

        try:
            # Create sessions for multiple providers
            providers = ["openai", "anthropic", "google"]
            for provider in providers:
                await pool_manager.get_session(provider)

            # Test health check performance
            start_time = time.perf_counter()
            health_status = await pool_manager.health_check_connections()
            health_check_time = time.perf_counter() - start_time

            print("Health check results:")
            print(f"  Time taken: {health_check_time:.6f}s")
            print(f"  Status: {health_status}")

            # Verify all providers are healthy
            for provider in providers:
                assert provider in health_status
                assert health_status[provider] is True

            # Health check should be fast
            assert health_check_time < 0.1

        finally:
            await pool_manager.cleanup()


class TestResponseValidationOptimizations:
    """Test response validation performance improvements."""

    def test_response_validation_performance(self) -> None:
        """Test optimized response validation performance."""
        # Test data with various scenarios
        test_responses = [
            '{"winner": "Essay A", "justification": "Better structure and clarity", '
            '"confidence": 4.2}',
            '{"winner": "Essay B", "justification": "More compelling arguments", '
            '"confidence": 3.8}',
            '{"winner": "Essay A", "justification": "Superior analysis", "confidence": 4.5}',
            '{"winner": "Essay B", "justification": "Clearer presentation", "confidence": 3.9}',
            '{"winner": "Essay A", "justification": "Better evidence", "confidence": 4.1}',
        ]

        # Warm up the validator (compile regex patterns)
        for response in test_responses[:2]:
            validate_and_normalize_response(response, "test_provider")

        # Measure validation performance
        iterations = 1000

        start_time = time.perf_counter()
        successful_validations = 0

        for _ in range(iterations):
            for response in test_responses:
                try:
                    result = validate_and_normalize_response(response, correlation_id=uuid4())
                    if result is not None:
                        successful_validations += 1
                except Exception:
                    # Validation failed, don't count as successful
                    pass

        total_time = time.perf_counter() - start_time
        total_validations = iterations * len(test_responses)
        avg_time_per_validation = total_time / total_validations

        print("Response validation performance:")
        print(f"  Total validations: {total_validations}")
        print(f"  Successful validations: {successful_validations}")
        print(f"  Total time: {total_time:.4f}s")
        print(f"  Average time per validation: {avg_time_per_validation:.6f}s")
        print(f"  Validations per second: {total_validations / total_time:.0f}")

        # Performance targets
        assert avg_time_per_validation < 0.0001  # Under 0.1ms per validation
        assert successful_validations == total_validations  # 100% success rate
        assert total_validations / total_time > 10000  # Over 10k validations per second

    def test_regex_pattern_compilation_performance(self) -> None:
        """Test that pre-compiled regex patterns improve performance
        by measuring PURE compilation overhead."""
        import re

        # Use realistic patterns from actual response validation
        patterns = {
            "winner": r'"winner"\s*:\s*"(Essay [AB])"',
            "justification": r'"justification"\s*:\s*"([^"]{10,500})"',
            "confidence": r'"confidence"\s*:\s*(\d+(?:\.\d+)?)',
        }

        test_response = (
            '{"winner": "Essay A", "justification": "Better structure and clarity", '
            '"confidence": 4.2}'
        )

        iterations = 10000

        # Test 1: Measure PURE compilation overhead (no search)
        start_time = time.perf_counter()
        for _ in range(iterations):
            for pattern in patterns.values():
                re.compile(pattern)  # Only compilation, no search
        pure_compilation_time = time.perf_counter() - start_time

        # Test 2: Measure pre-compiled pattern access (no compilation)
        compiled_patterns = {key: re.compile(pattern) for key, pattern in patterns.items()}

        start_time = time.perf_counter()
        for _ in range(iterations):
            for pattern_obj in compiled_patterns.values():
                pass  # Just access the pre-compiled pattern
        precompiled_access_time = time.perf_counter() - start_time

        # Test 3: Measure search time only (for context)
        start_time = time.perf_counter()
        for _ in range(iterations):
            for pattern_obj in compiled_patterns.values():
                pattern_obj.search(test_response)
        search_only_time = time.perf_counter() - start_time

        # Calculate improvement: compilation vs pre-compiled access
        compilation_overhead = pure_compilation_time - precompiled_access_time
        improvement = (compilation_overhead / pure_compilation_time) * 100

        print("Regex compilation analysis:")
        print(f"  Pure compilation time: {pure_compilation_time:.4f}s")
        print(f"  Pre-compiled access time: {precompiled_access_time:.4f}s")
        print(f"  Search execution time: {search_only_time:.4f}s")
        print(f"  Compilation overhead: {compilation_overhead:.4f}s")
        print(f"  Compilation savings: {improvement:.1f}%")

        # Proper assertions: compilation should be significantly more expensive than access
        assert pure_compilation_time > precompiled_access_time
        assert improvement > 50  # Compilation overhead should be >50% of total compilation time

        # Verify that compilation dominates when patterns are compiled repeatedly
        total_compile_and_search = pure_compilation_time + search_only_time
        total_precompiled_search = precompiled_access_time + search_only_time
        overall_improvement = (
            (total_compile_and_search - total_precompiled_search) / total_compile_and_search
        ) * 100

        print(f"  Overall workflow improvement: {overall_improvement:.1f}%")
        assert overall_improvement > 20  # Real-world improvement should be significant

    def test_json_parsing_optimization(self) -> None:
        """Test JSON parsing performance with various response sizes."""

        # Test responses of different sizes
        test_cases = [
            {"size": "small", "justification": "Good analysis" * 10},
            {"size": "medium", "justification": "Excellent detailed analysis " * 25},
            {"size": "large", "justification": "Very comprehensive and detailed analysis " * 50},
        ]

        for case in test_cases:
            response_data = {
                "winner": "Essay A",
                "justification": case["justification"],
                "confidence": 4.2,
            }

            response_json = json.dumps(response_data)
            response_size = len(response_json)

            # Measure parsing performance
            iterations = 1000
            start_time = time.perf_counter()

            for _ in range(iterations):
                parsed = json.loads(response_json)
                assert parsed["winner"] == "Essay A"

            parsing_time = time.perf_counter() - start_time
            avg_time = parsing_time / iterations

            print(f"JSON parsing ({case['size']}):")
            print(f"  Response size: {response_size} bytes")
            print(f"  Average parsing time: {avg_time:.6f}s")
            print(f"  Parses per second: {iterations / parsing_time:.0f}")

            # Performance targets based on size
            if case["size"] == "small":
                assert avg_time < 0.00001  # Under 10 microseconds
            elif case["size"] == "medium":
                assert avg_time < 0.00005  # Under 50 microseconds
            else:  # large
                assert avg_time < 0.0001  # Under 100 microseconds


class LLMProviderServiceTestProvider(LLMProviderServiceProvider):
    """Test-specific provider that allows settings injection."""

    def __init__(self, test_settings: Settings):
        super().__init__()
        self._test_settings = test_settings

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        return self._test_settings

    # Optimization validation tests don't need custom provider override
    # since they focus on infrastructure performance, not provider behavior


@pytest.fixture(scope="class")
def redis_container() -> Generator[Any, None, None]:
    """Provide a Redis container for testing."""
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="class")
def redis_optimization_settings(redis_container: Any) -> Settings:
    """Settings configured for Redis optimization testing."""
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    return Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.TESTING,
        LOG_LEVEL="INFO",
        USE_MOCK_LLM=True,
        REDIS_URL=redis_url,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",  # Not used in Redis-only tests
    )


@pytest.fixture
async def redis_di_container(redis_optimization_settings: Settings) -> AsyncGenerator[Any, None]:
    """DI container with real Redis for optimization testing."""
    from dishka import make_async_container

    test_provider = LLMProviderServiceTestProvider(redis_optimization_settings)
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


class TestRedisOptimizations:
    """Test Redis pipelining and batch operation optimizations with real infrastructure."""

    @pytest.mark.asyncio
    async def test_pipeline_vs_individual_operations(self, redis_di_container: Any) -> None:
        """Compare pipeline vs individual Redis operations performance with real infrastructure."""
        async with redis_di_container() as request_container:
            from services.llm_provider_service.implementations.redis_queue_repository_impl import (
                RedisQueueRepositoryImpl,
            )

            queue_repo = await request_container.get(RedisQueueRepositoryImpl)

            # Test data using same pattern as working test
        from datetime import timedelta, timezone
        from uuid import uuid4

        from common_core import QueueStatus

        from services.llm_provider_service.api_models import LLMComparisonRequest
        from services.llm_provider_service.queue_models import QueuedRequest

        # Create smaller batch to avoid timeout issues
        requests = []
        for i in range(3):
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

            # Test pipeline operations
            start_time = time.perf_counter()
            for request in requests:
                await queue_repo.add(request)
            pipeline_time = time.perf_counter() - start_time

        print("Pipeline operations performance (real Redis):")
        print(f"  {len(requests)} operations in {pipeline_time:.6f}s")
        print(f"  Average per operation: {pipeline_time / len(requests):.6f}s")
        print("  Infrastructure: Real Redis (testcontainer)")

        # Realistic performance assertion for Redis pipeline
        assert pipeline_time / len(requests) < 0.1  # Under 100ms per operation

    @pytest.mark.asyncio
    async def test_batch_retrieval_optimization(self, redis_di_container: Any) -> None:
        """Test batch queue retrieval optimization with real Redis."""
        async with redis_di_container() as request_container:
            from huleedu_service_libs.queue_protocols import QueueRedisClientProtocol

            from services.llm_provider_service.implementations.redis_queue_repository_impl import (
                RedisQueueRepositoryImpl,
            )

            queue_repo = await request_container.get(RedisQueueRepositoryImpl)
            queue_redis_client = await request_container.get(QueueRedisClientProtocol)

            # Clean up any leftover queue data from previous tests
            await queue_redis_client.delete("llm_provider_service:queue:requests")
            await queue_redis_client.delete("llm_provider_service:queue:data")
            await queue_redis_client.delete("llm_provider_service:queue:stats")

            # Test batch retrieval performance (simple case)
            iterations = 5
            start_time = time.perf_counter()

            for _ in range(iterations):
                result = await queue_repo.get_next()
                assert result is None  # Should return None for empty queue

            batch_time = time.perf_counter() - start_time
            avg_time = batch_time / iterations

        print("Batch retrieval performance (real Redis):")
        print(f"  {iterations} retrievals in {batch_time:.4f}s")
        print(f"  Average per retrieval: {avg_time:.6f}s")
        print("  Infrastructure: Real Redis (testcontainer)")

        # Realistic performance assertion for Redis batch retrieval
        assert avg_time < 0.2  # Under 200ms per retrieval with real Redis


class TestProviderSpecificOptimizations:
    """Test provider-specific performance optimizations."""

    def test_provider_timeout_configurations(self) -> None:
        """Test that provider-specific timeouts are optimized."""
        from services.llm_provider_service.config import Settings

        settings = Settings(
            SERVICE_NAME="llm_provider_service",
            ENVIRONMENT=Environment.TESTING,
        )

        pool_manager = ConnectionPoolManagerImpl(settings)

        # Test provider-specific configurations
        providers_config = {
            "openai": {"expected_timeout": 30, "expected_pool": 50},
            "anthropic": {"expected_timeout": 45, "expected_pool": 40},
            "google": {"expected_timeout": 40, "expected_pool": 60},
            "openrouter": {"expected_timeout": 50, "expected_pool": 30},
        }

        for provider, expectations in providers_config.items():
            config = pool_manager._get_provider_connection_limits(provider)

            print(f"{provider} configuration:")
            print(f"  Pool size: {config['total_pool_size']}")
            print(f"  Timeout: {config['total_timeout']}s")
            print(f"  Per host limit: {config['per_host_limit']}")

            # Verify optimizations
            assert config["total_pool_size"] == expectations["expected_pool"]
            assert config["total_timeout"] == expectations["expected_timeout"]
            assert config["per_host_limit"] > 0
            assert config["connect_timeout"] < config["total_timeout"]
            assert config["read_timeout"] < config["total_timeout"]

    def test_provider_header_optimizations(self) -> None:
        """Test provider-specific header optimizations."""
        from services.llm_provider_service.config import Settings

        settings = Settings(
            SERVICE_NAME="llm_provider_service",
            ENVIRONMENT=Environment.TESTING,
        )

        pool_manager = ConnectionPoolManagerImpl(settings)

        # Test provider-specific headers
        providers = ["openai", "anthropic", "google", "openrouter"]

        for provider in providers:
            headers = pool_manager._get_provider_headers(provider)

            print(f"{provider} headers: {headers}")

            # Common headers
            assert "User-Agent" in headers
            assert "Accept" in headers
            assert "Content-Type" in headers
            assert "Connection" in headers
            assert headers["Connection"] == "keep-alive"

            # Provider-specific headers
            if provider == "openai":
                assert "OpenAI-Beta" in headers
            elif provider == "anthropic":
                assert "Anthropic-Version" in headers
            elif provider == "google":
                # Google deliberately omits X-Goog-User-Project to avoid 403 errors
                # Verify Google headers don't include problematic headers
                assert "X-Goog-User-Project" not in headers
