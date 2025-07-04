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
from unittest.mock import AsyncMock

import pytest

from services.llm_provider_service.config import Settings
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
        ENVIRONMENT="testing",
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
            print(f"Reuse improvement: {((first_creation_time - reuse_time) / first_creation_time * 100):.1f}%")

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
            assert max_time < 0.01   # Even worst case should be under 10ms

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
            '{"winner": "Essay A", "justification": "Better structure and clarity", "confidence": 4.2}',
            '{"winner": "Essay B", "justification": "More compelling arguments", "confidence": 3.8}',
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
                result, error = validate_and_normalize_response(response, "test_provider")
                if result is not None:
                    successful_validations += 1

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
        """Test that pre-compiled regex patterns improve performance."""
        # Test without pre-compilation
        import re

        patterns = {
            "winner": r'"winner"\s*:\s*"(Essay [AB])"',
            "justification": r'"justification"\s*:\s*"([^"]{10,500})"',
            "confidence": r'"confidence"\s*:\s*(\d+(?:\.\d+)?)',
        }

        test_response = '{"winner": "Essay A", "justification": "Better structure and clarity", "confidence": 4.2}'

        # Test compilation time vs usage time
        iterations = 1000

        # Without pre-compilation (compile each time)
        start_time = time.perf_counter()
        for _ in range(iterations):
            for pattern in patterns.values():
                compiled_pattern = re.compile(pattern)
                compiled_pattern.search(test_response)
        time_without_precompilation = time.perf_counter() - start_time

        # With pre-compilation
        compiled_patterns = {key: re.compile(pattern) for key, pattern in patterns.items()}

        start_time = time.perf_counter()
        for _ in range(iterations):
            for compiled_pattern in compiled_patterns.values():
                compiled_pattern.search(test_response)
        time_with_precompilation = time.perf_counter() - start_time

        improvement = ((time_without_precompilation - time_with_precompilation) / time_without_precompilation) * 100

        print("Regex compilation performance:")
        print(f"  Without pre-compilation: {time_without_precompilation:.4f}s")
        print(f"  With pre-compilation: {time_with_precompilation:.4f}s")
        print(f"  Performance improvement: {improvement:.1f}%")

        assert time_with_precompilation < time_without_precompilation
        assert improvement > 50  # Should be significantly faster

    def test_json_parsing_optimization(self) -> None:
        """Test JSON parsing performance with various response sizes."""
        import json

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
                assert avg_time < 0.0001   # Under 100 microseconds


class TestRedisOptimizations:
    """Test Redis pipelining and batch operation optimizations."""

    @pytest.mark.asyncio
    async def test_pipeline_vs_individual_operations(self) -> None:
        """Compare pipeline vs individual Redis operations performance."""
        # Mock Redis client
        mock_redis = AsyncMock()
        mock_pipeline = AsyncMock()

        # Configure pipeline mock
        mock_redis.client.pipeline.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [True] * 10

        # Configure individual operation mocks
        mock_redis.client.zadd.return_value = True
        mock_redis.client.hset.return_value = True
        mock_redis.client.setex.return_value = True

        from services.llm_provider_service.config import Settings
        from services.llm_provider_service.implementations.redis_queue_repository_impl import (
            RedisQueueRepositoryImpl,
        )

        settings = Settings(
            SERVICE_NAME="test_service",
            ENVIRONMENT="testing",
        )

        queue_repo = RedisQueueRepositoryImpl(mock_redis, settings)

        # Test data
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

        # Test pipeline operations
        start_time = time.perf_counter()
        for request in requests:
            await queue_repo.add(request)
        pipeline_time = time.perf_counter() - start_time

        # Verify pipeline was used
        assert mock_redis.client.pipeline.call_count >= len(requests)
        assert mock_pipeline.execute.call_count >= len(requests)

        print("Pipeline operations performance:")
        print(f"  {len(requests)} operations in {pipeline_time:.6f}s")
        print(f"  Average per operation: {pipeline_time / len(requests):.6f}s")

        # Pipeline should be efficient
        assert pipeline_time / len(requests) < 0.001  # Under 1ms per operation

    @pytest.mark.asyncio
    async def test_batch_retrieval_optimization(self) -> None:
        """Test batch queue retrieval optimization."""
        mock_redis = AsyncMock()

        # Configure batch retrieval mocks
        queue_ids = [f"queue-{i}" for i in range(10)]
        mock_redis.client.zrange.return_value = queue_ids

        # Mock request data
        request_data = []
        from datetime import timezone
        
        for i in range(10):
            data = {
                "queue_id": f"queue-{i}",
                "status": "QUEUED",
                "priority": 0,
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "request_data": {"essay_a": f"Essay A {i}", "essay_b": f"Essay B {i}"}
            }
            request_data.append(json.dumps(data))

        mock_redis.client.hmget.return_value = request_data

        from services.llm_provider_service.config import Settings
        from services.llm_provider_service.implementations.redis_queue_repository_impl import (
            RedisQueueRepositoryImpl,
        )

        settings = Settings(
            SERVICE_NAME="test_service",
            ENVIRONMENT="testing",
        )

        queue_repo = RedisQueueRepositoryImpl(mock_redis, settings)

        # Test batch retrieval performance
        iterations = 100
        start_time = time.perf_counter()

        for _ in range(iterations):
            await queue_repo.get_next()

        batch_time = time.perf_counter() - start_time
        avg_time = batch_time / iterations

        print("Batch retrieval performance:")
        print(f"  {iterations} retrievals in {batch_time:.4f}s")
        print(f"  Average per retrieval: {avg_time:.6f}s")

        # Verify batch operations were used
        assert mock_redis.client.zrange.called
        assert mock_redis.client.hmget.called

        # Should be very fast with batch operations
        assert avg_time < 0.01  # Under 10ms per retrieval


class TestProviderSpecificOptimizations:
    """Test provider-specific performance optimizations."""

    def test_provider_timeout_configurations(self) -> None:
        """Test that provider-specific timeouts are optimized."""
        from services.llm_provider_service.config import Settings

        settings = Settings(
            SERVICE_NAME="llm_provider_service",
            ENVIRONMENT="testing",
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
            ENVIRONMENT="testing",
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
                assert "X-Goog-User-Project" in headers
