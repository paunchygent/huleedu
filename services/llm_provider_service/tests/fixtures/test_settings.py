"""Typed settings fixtures for tests - no MagicMocks."""

from typing import Any

import pytest

from services.llm_provider_service.config import Settings


class TestSettings(Settings):
    """Typed settings for tests - inherits from production Settings."""

    # Override defaults for testing
    QUEUE_MAX_SIZE: int = 100
    QUEUE_REQUEST_TTL_HOURS: int = 1
    QUEUE_MAX_MEMORY_MB: int = 10

    # Disable external services for unit tests by default
    REDIS_ENABLED: bool = False
    KAFKA_ENABLED: bool = False

    # Simplified circuit breaker settings for tests
    LLM_CIRCUIT_BREAKER_ENABLED: bool = False
    LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 3
    LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = 10

    # Mock provider settings
    USE_MOCK_LLM: bool = True
    RECORD_LLM_RESPONSES: bool = False

    # Minimal timeouts for faster tests
    DEFAULT_TIMEOUT_SECONDS: int = 5
    PROVIDER_TIMEOUT_SECONDS: int = 3


@pytest.fixture
def unit_test_settings() -> TestSettings:
    """Settings for unit tests - no infrastructure dependencies."""
    return TestSettings(
        # Core service settings
        SERVICE_NAME="test-llm-provider-service",
        LOG_LEVEL="DEBUG",
        PORT=0,  # Use any available port for tests
        # Disable all external services
        REDIS_ENABLED=False,
        KAFKA_ENABLED=False,
        # Disable circuit breakers for predictable unit test behavior
        CIRCUIT_BREAKER_ENABLED=False,
        LLM_CIRCUIT_BREAKER_ENABLED=False,
        # Use mock providers only
        USE_MOCK_LLM=True,
        # Small queue for fast tests
        QUEUE_MAX_SIZE=10,
        QUEUE_REQUEST_TTL_HOURS=1,
        QUEUE_MAX_MEMORY_MB=1,
        # Fast timeouts
        DEFAULT_TIMEOUT_SECONDS=1,
        PROVIDER_TIMEOUT_SECONDS=1,
        # Test-specific overrides
        ANTHROPIC_API_KEY="test-anthropic-key",
        OPENAI_API_KEY="test-openai-key",
        GOOGLE_API_KEY="test-google-key",
        OPENROUTER_API_KEY="test-openrouter-key",
    )


@pytest.fixture
def integration_test_settings() -> TestSettings:
    """Settings for integration tests - includes infrastructure."""
    return TestSettings(
        # Core service settings
        SERVICE_NAME="test-llm-provider-service-integration",
        LOG_LEVEL="INFO",
        PORT=0,  # Use any available port for tests
        # Enable infrastructure for integration tests
        REDIS_ENABLED=True,
        KAFKA_ENABLED=True,
        # Enable circuit breakers to test resilience
        CIRCUIT_BREAKER_ENABLED=True,
        LLM_CIRCUIT_BREAKER_ENABLED=True,
        LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=2,  # Fail fast in tests
        LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=5,  # Quick recovery
        # Use mock providers to avoid API costs
        USE_MOCK_LLM=True,
        # Larger queue for integration scenarios
        QUEUE_MAX_SIZE=100,
        QUEUE_REQUEST_TTL_HOURS=1,
        QUEUE_MAX_MEMORY_MB=10,
        # Reasonable timeouts for integration tests
        DEFAULT_TIMEOUT_SECONDS=10,
        PROVIDER_TIMEOUT_SECONDS=5,
        # Test environment URLs
        REDIS_URL="redis://localhost:6379/15",  # Use test database
        KAFKA_BOOTSTRAP_SERVERS="localhost:29092",
    )


@pytest.fixture
def performance_test_settings() -> TestSettings:
    """Settings for performance tests - realistic configuration."""
    return TestSettings(
        # Core service settings
        SERVICE_NAME="test-llm-provider-service-performance",
        LOG_LEVEL="WARNING",  # Reduce logging noise
        PORT=0,
        # Enable all infrastructure
        REDIS_ENABLED=True,
        KAFKA_ENABLED=True,
        # Production-like circuit breaker settings
        CIRCUIT_BREAKER_ENABLED=True,
        LLM_CIRCUIT_BREAKER_ENABLED=True,
        LLM_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5,
        LLM_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30,
        # Use mock providers for consistent performance
        USE_MOCK_LLM=True,
        # Larger capacity for performance testing
        QUEUE_MAX_SIZE=1000,
        QUEUE_REQUEST_TTL_HOURS=4,
        QUEUE_MAX_MEMORY_MB=100,
        # Production-like timeouts
        DEFAULT_TIMEOUT_SECONDS=30,
        PROVIDER_TIMEOUT_SECONDS=15,
    )


# Factory function for custom settings
def create_test_settings(**overrides: Any) -> TestSettings:
    """Create test settings with custom overrides.

    Args:
        **overrides: Setting values to override

    Returns:
        TestSettings instance with overrides applied
    """
    base_settings = TestSettings()

    # Apply overrides
    for key, value in overrides.items():
        if hasattr(base_settings, key):
            setattr(base_settings, key, value)
        else:
            raise ValueError(f"Invalid setting: {key}")

    return base_settings
