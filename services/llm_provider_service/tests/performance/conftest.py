"""
Performance test fixtures with testcontainers for realistic infrastructure testing.

Uses real Kafka and Redis containers to measure actual performance characteristics
while keeping LLM providers mocked to avoid API costs.
"""

from typing import Generator

import pytest
from testcontainers.kafka import KafkaContainer
from testcontainers.redis import RedisContainer

from services.llm_provider_service.config import Settings


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
        # Wait for Redis to be ready
        redis.get_connection_url()
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
    redis_url = redis_container.get_connection_url()

    settings = Settings(
        SERVICE_NAME="llm_provider_service",
        ENVIRONMENT="testing",
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
        ENVIRONMENT="testing",
        LOG_LEVEL="INFO",
        USE_MOCK_LLM=True,  # CRITICAL: Prevents real API calls and costs
    )

    # Double-check that mock providers are enabled
    assert settings.USE_MOCK_LLM is True, "Mock LLM must be enabled to avoid API costs"
    return settings
