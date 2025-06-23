"""Tests for CJ Assessment Service runner functionality.

Tests the service management and startup logic without mocking business logic.
Focuses on external boundaries and integration points.
"""

from __future__ import annotations

import asyncio
import signal
from unittest.mock import AsyncMock

import pytest

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.run_service import ServiceManager


class TestServiceManager:
    """Test the ServiceManager class functionality."""

    @pytest.fixture
    def settings(self) -> Settings:
        """Provide test settings."""
        return Settings(LOG_LEVEL="DEBUG")

    @pytest.fixture
    def service_manager(self, settings: Settings) -> ServiceManager:
        """Create a ServiceManager instance for testing."""
        return ServiceManager(settings)

    async def test_service_manager_initialization(
        self,
        service_manager: ServiceManager,
        settings: Settings,
    ) -> None:
        """Test ServiceManager initializes correctly."""
        assert service_manager.settings == settings
        assert service_manager.tasks == []
        assert not service_manager.shutdown_event.is_set()

    async def test_handle_shutdown_signal(self, service_manager: ServiceManager) -> None:
        """Test shutdown signal handling."""
        # Initially shutdown event should not be set
        assert not service_manager.shutdown_event.is_set()

        # Handle shutdown signal
        service_manager.handle_shutdown_signal(signal.SIGTERM, None)

        # Shutdown event should now be set
        assert service_manager.shutdown_event.is_set()

    async def test_shutdown_event_propagation(self, service_manager: ServiceManager) -> None:
        """Test that shutdown event can be waited on."""
        # Start a task that waits for shutdown event
        wait_task = asyncio.create_task(service_manager.shutdown_event.wait())

        # Give it a moment to start waiting
        await asyncio.sleep(0.01)
        assert not wait_task.done()

        # Trigger shutdown
        service_manager.shutdown_event.set()

        # Wait task should complete
        await asyncio.wait_for(wait_task, timeout=1.0)
        assert wait_task.done()


class TestServiceIntegration:
    """Test service integration points and configuration."""

    async def test_service_runs_with_valid_config(self) -> None:
        """Test that services can be configured correctly."""
        settings = Settings(
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            METRICS_PORT=9999,
            LOG_LEVEL="INFO",
        )

        # Test that we can create a service manager with these settings
        manager = ServiceManager(settings)
        assert manager.settings.KAFKA_BOOTSTRAP_SERVERS == "localhost:9092"
        assert manager.settings.METRICS_PORT == 9999
        assert manager.settings.LOG_LEVEL == "INFO"

    async def test_service_manager_task_tracking(self) -> None:
        """Test task management without actually running services."""
        settings = Settings()
        manager = ServiceManager(settings)

        # Initially no tasks
        assert len(manager.tasks) == 0

        # Test that tasks list exists and can be modified
        mock_task = AsyncMock()
        manager.tasks.append(mock_task)
        assert len(manager.tasks) == 1

    async def test_signal_handler_setup_in_main(self) -> None:
        """Test that signal handlers can be configured."""
        settings = Settings()
        manager = ServiceManager(settings)

        # Test signal handler function exists and is callable
        assert callable(manager.handle_shutdown_signal)

        # Test it accepts the expected signature
        try:
            manager.handle_shutdown_signal(signal.SIGTERM, None)
            # Should not raise an exception
        except Exception as e:
            pytest.fail(f"Signal handler raised unexpected exception: {e}")


class TestConfigurationValidation:
    """Test configuration and environment variable handling."""

    async def test_settings_validation(self) -> None:
        """Test that Settings validation works correctly."""
        # Test default settings
        default_settings = Settings()
        assert default_settings.METRICS_PORT == 9090
        assert default_settings.LOG_LEVEL == "INFO"

        # Test custom settings
        custom_settings = Settings(METRICS_PORT=8080, LOG_LEVEL="DEBUG")
        assert custom_settings.METRICS_PORT == 8080
        assert custom_settings.LOG_LEVEL == "DEBUG"

    async def test_service_name_configuration(self) -> None:
        """Test service name configuration."""
        settings = Settings()
        # Test that service has a proper name configured
        assert hasattr(settings, "SERVICE_NAME")
        # Service name should be meaningful
        assert len(settings.SERVICE_NAME) > 0

    async def test_kafka_configuration_exists(self) -> None:
        """Test that Kafka configuration is available."""
        settings = Settings()
        assert hasattr(settings, "KAFKA_BOOTSTRAP_SERVERS")
        assert hasattr(settings, "CONSUMER_GROUP_ID_CJ")
        assert hasattr(settings, "PRODUCER_CLIENT_ID_CJ")
        assert hasattr(settings, "CJ_ASSESSMENT_COMPLETED_TOPIC")
        assert hasattr(settings, "CJ_ASSESSMENT_FAILED_TOPIC")

        # Should have sensible defaults (kafka:9092 for Docker containers)
        assert settings.KAFKA_BOOTSTRAP_SERVERS == "kafka:9092"
        assert len(settings.CONSUMER_GROUP_ID_CJ) > 0
        assert len(settings.PRODUCER_CLIENT_ID_CJ) > 0
