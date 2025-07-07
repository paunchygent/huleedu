"""
Performance test fixtures with testcontainers for realistic infrastructure testing.

Uses real Kafka and Redis containers to measure actual performance characteristics
while keeping LLM providers mocked to avoid API costs.
"""

import statistics
from typing import Any, Dict, Generator, List, Optional, Tuple
from unittest.mock import AsyncMock

import aiohttp
import pytest
from testcontainers.kafka import KafkaContainer
from testcontainers.redis import RedisContainer

from common_core import Environment
from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.connection_pool_manager_impl import (
    ConnectionPoolManagerImpl,
)
from services.llm_provider_service.implementations.redis_queue_repository_impl import (
    RedisQueueRepositoryImpl,
)


@pytest.fixture(scope="session")
def kafka_container() -> Generator[KafkaContainer, None, None]:
    """Kafka container for performance testing."""
    with KafkaContainer("confluentinc/cp-kafka:7.4.0") as kafka:
        # Wait for Kafka to be ready
        kafka.get_bootstrap_server()
        yield kafka


@pytest.fixture(scope="session")
def redis_container() -> Generator[RedisContainer, None, None]:
    """Redis container for performance testing."""
    with RedisContainer("redis:7-alpine") as redis:
        # Wait for Redis to be ready and verify connection
        client = redis.get_client()
        assert client.ping() is True
        yield redis


@pytest.fixture
async def performance_settings_with_containers(
    kafka_container: KafkaContainer, redis_container: RedisContainer
) -> Settings:
    """Settings with real containers for performance testing.

    CRITICAL: Mock LLM providers are enabled to avoid API costs during testing.
    Real Kafka and Redis are used to measure actual infrastructure performance.
    """
    bootstrap_server = kafka_container.get_bootstrap_server()
    # Construct Redis URL from container host and exposed port
    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    settings = Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.TESTING,
        LOG_LEVEL="INFO",
        # CRITICAL: Mock LLM to avoid API costs
        USE_MOCK_LLM=True,
        # Container connection details
        KAFKA_BOOTSTRAP_SERVERS=bootstrap_server,
        REDIS_URL=redis_url,
        # Performance test optimizations
        QUEUE_MAX_SIZE=1000,
        QUEUE_MAX_MEMORY_MB=100,
        QUEUE_REQUEST_TTL_HOURS=4,
        QUEUE_POLL_INTERVAL_SECONDS=0.1,
    )

    # Double-check that mock LLM is enabled to avoid costs
    assert settings.USE_MOCK_LLM is True, "Mock LLM must be enabled to avoid API costs"

    return settings


@pytest.fixture
def mock_only_settings() -> Settings:
    """Settings with all mocks for unit-style performance tests."""
    settings = Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT=Environment.TESTING,
        LOG_LEVEL="INFO",
        USE_MOCK_LLM=True,  # CRITICAL: Prevents real API calls and costs
    )

    # Double-check that mock providers are enabled
    assert settings.USE_MOCK_LLM is True, "Mock LLM must be enabled to avoid API costs"
    return settings


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

        import time

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
