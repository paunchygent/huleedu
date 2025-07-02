"""
Unit tests for Class Management Service Kafka circuit breaker DI configuration.

These tests verify that the DI container correctly creates and configures
circuit breaker protection for Kafka publishing in the Class Management Service.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from huleedu_service_libs.kafka.resilient_kafka_bus import ResilientKafkaPublisher
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.resilience import CircuitBreaker, CircuitBreakerRegistry

from services.class_management_service.config import Settings
from services.class_management_service.di import ServiceProvider


@pytest.fixture
def mock_settings() -> Settings:
    """Mock settings for testing."""
    return Settings(
        SERVICE_NAME="class_management_service",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        CIRCUIT_BREAKER_ENABLED=True,
        KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5,
        KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT=30,
        KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD=2,
        KAFKA_FALLBACK_QUEUE_SIZE=500,
    )


@pytest.fixture
def mock_settings_disabled() -> Settings:
    """Mock settings with circuit breaker disabled."""
    return Settings(
        SERVICE_NAME="class_management_service",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        CIRCUIT_BREAKER_ENABLED=False,
    )


@pytest.fixture
def provider() -> ServiceProvider:
    """DI provider for testing."""
    return ServiceProvider()


@pytest.mark.asyncio
async def test_circuit_breaker_registry_creation(
    provider: ServiceProvider, mock_settings: Settings
) -> None:
    """Test that circuit breaker registry is created correctly."""
    registry = provider.provide_circuit_breaker_registry(mock_settings)

    assert isinstance(registry, CircuitBreakerRegistry)
    assert registry is not None


@pytest.mark.asyncio
async def test_circuit_breaker_registry_disabled(
    provider: ServiceProvider, mock_settings_disabled: Settings
) -> None:
    """Test that circuit breaker registry works when disabled."""
    registry = provider.provide_circuit_breaker_registry(mock_settings_disabled)

    assert isinstance(registry, CircuitBreakerRegistry)
    # Registry is created but no breakers are registered when disabled


@pytest.mark.asyncio
async def test_kafka_bus_with_circuit_breaker(
    provider: ServiceProvider, mock_settings: Settings
) -> None:
    """Test that KafkaBus is wrapped with circuit breaker when enabled."""
    # Create registry first
    registry = provider.provide_circuit_breaker_registry(mock_settings)

    # Mock the KafkaBus.start method to avoid actual Kafka connection
    with (
        patch.object(KafkaBus, "start", new_callable=AsyncMock) as mock_start,
        patch.object(KafkaBus, "stop", new_callable=AsyncMock),
    ):
        kafka_bus = await provider.provide_kafka_bus(mock_settings, registry)

        try:
            # Should return ResilientKafkaPublisher when circuit breaker is enabled
            assert isinstance(kafka_bus, ResilientKafkaPublisher)
            assert kafka_bus.client_id == "class_management_service-producer"
            assert kafka_bus.bootstrap_servers == "localhost:9092"

            # Verify circuit breaker is configured
            cb_state = kafka_bus.get_circuit_breaker_state()
            assert cb_state["enabled"] is True
            assert cb_state["state"] == "closed"
            assert cb_state["name"] == "class_management_service.kafka_producer"

            # Verify fallback queue
            assert kafka_bus.get_fallback_queue_size() == 0

            # Verify circuit breaker is registered
            assert registry.get("kafka_producer") is not None
            assert len(registry) > 0

            # Verify start was called
            mock_start.assert_called_once()

        finally:
            # Cleanup to avoid pending tasks
            await kafka_bus.stop()


@pytest.mark.asyncio
async def test_kafka_bus_without_circuit_breaker(
    provider: ServiceProvider, mock_settings_disabled: Settings
) -> None:
    """Test that base KafkaBus is returned when circuit breaker is disabled."""
    # Create registry first
    registry = provider.provide_circuit_breaker_registry(mock_settings_disabled)

    # Mock the KafkaBus.start method to avoid actual Kafka connection
    with patch.object(KafkaBus, "start", new_callable=AsyncMock) as mock_start:
        kafka_bus = await provider.provide_kafka_bus(mock_settings_disabled, registry)

        # Should return base KafkaBus when circuit breaker is disabled
        assert isinstance(kafka_bus, KafkaBus)
        assert not isinstance(kafka_bus, ResilientKafkaPublisher)
        assert kafka_bus.client_id == "class_management_service-producer"
        assert kafka_bus.bootstrap_servers == "localhost:9092"

        # Verify start was called
        mock_start.assert_called_once()


@pytest.mark.asyncio
async def test_circuit_breaker_configuration(
    provider: ServiceProvider, mock_settings: Settings
) -> None:
    """Test that circuit breaker is configured with correct settings."""
    registry = provider.provide_circuit_breaker_registry(mock_settings)

    with patch.object(KafkaBus, "start", new_callable=AsyncMock):
        await provider.provide_kafka_bus(mock_settings, registry)

        # Get the circuit breaker from registry
        circuit_breaker = registry.get("kafka_producer")
        assert circuit_breaker is not None
        assert isinstance(circuit_breaker, CircuitBreaker)

        # Verify configuration matches settings
        assert circuit_breaker.failure_threshold == 5
        assert circuit_breaker.recovery_timeout == timedelta(seconds=30)
        assert circuit_breaker.success_threshold == 2
        assert circuit_breaker.name == "class_management_service.kafka_producer"


@pytest.mark.asyncio
async def test_settings_configuration() -> None:
    """Test that settings include all required circuit breaker configuration."""
    settings = Settings()

    # Verify all circuit breaker settings are present with correct defaults
    assert hasattr(settings, "CIRCUIT_BREAKER_ENABLED")
    assert settings.CIRCUIT_BREAKER_ENABLED is True

    assert hasattr(settings, "KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    assert settings.KAFKA_CIRCUIT_BREAKER_FAILURE_THRESHOLD == 10

    assert hasattr(settings, "KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT")
    assert settings.KAFKA_CIRCUIT_BREAKER_RECOVERY_TIMEOUT == 30

    assert hasattr(settings, "KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD")
    assert settings.KAFKA_CIRCUIT_BREAKER_SUCCESS_THRESHOLD == 3

    assert hasattr(settings, "KAFKA_FALLBACK_QUEUE_SIZE")
    assert settings.KAFKA_FALLBACK_QUEUE_SIZE == 1000


@pytest.mark.asyncio
async def test_lifecycle_cleanup(provider: ServiceProvider, mock_settings: Settings) -> None:
    """Test that resources are properly cleaned up."""
    registry = provider.provide_circuit_breaker_registry(mock_settings)

    with (
        patch.object(KafkaBus, "start", new_callable=AsyncMock),
        patch.object(KafkaBus, "stop", new_callable=AsyncMock) as mock_stop,
    ):
        kafka_bus = await provider.provide_kafka_bus(mock_settings, registry)

        # Test cleanup
        await kafka_bus.stop()
        mock_stop.assert_called_once()


def test_env_prefix() -> None:
    """Test that environment variable prefix is correctly set."""
    settings = Settings()
    assert settings.model_config["env_prefix"] == "CLASS_MANAGEMENT_SERVICE_"


@pytest.mark.asyncio
async def test_integration_with_existing_providers(
    provider: ServiceProvider, mock_settings: Settings
) -> None:
    """Test that circuit breaker integration doesn't break existing DI flow."""
    # Test that other providers can still be created
    settings_instance = provider.provide_settings()
    assert settings_instance is not None

    # Test that circuit breaker registry integrates smoothly
    cb_registry = provider.provide_circuit_breaker_registry(mock_settings)
    assert cb_registry is not None

    # All providers should work together
    with (
        patch.object(KafkaBus, "start", new_callable=AsyncMock),
        patch.object(KafkaBus, "stop", new_callable=AsyncMock),
    ):
        kafka_bus = await provider.provide_kafka_bus(mock_settings, cb_registry)
        try:
            assert kafka_bus is not None
        finally:
            await kafka_bus.stop()
