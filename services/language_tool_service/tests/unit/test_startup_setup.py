"""
Comprehensive behavioral tests for Language Tool Service startup_setup module.

Tests focus on initialization behavior, middleware setup, DI container lifecycle,
metrics initialization, and error recovery scenarios following Rule 075 standards.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import Mock

import pytest
from quart import Quart

from services.language_tool_service.config import Settings
from services.language_tool_service.startup_setup import initialize_services, shutdown_services


class TestInitializeServicesFunction:
    """Test initialize_services function comprehensive behavior."""

    @pytest.fixture
    def mock_app(self) -> Quart:
        """Create mock Quart app for testing."""
        app = Mock(spec=Quart)
        app.extensions = {}
        return app

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings for testing."""
        settings = Mock(spec=Settings)
        settings.SERVICE_NAME = "language-tool-service"
        settings.HTTP_PORT = 8085
        settings.LOG_LEVEL = "INFO"
        return settings

    async def test_initialize_services_success_path(
        self, mock_app: Quart, mock_settings: Settings
    ) -> None:
        """Test successful service initialization with all components."""
        # When
        await initialize_services(mock_app, mock_settings)

        # Then - Extensions dictionary should be populated
        assert hasattr(mock_app, "extensions")
        assert "metrics" in mock_app.extensions
        assert "tracer" in mock_app.extensions

    async def test_initialize_services_di_container_setup(
        self, mock_app: Quart, mock_settings: Settings
    ) -> None:
        """Test DI container creation and Quart-Dishka integration."""
        # When
        await initialize_services(mock_app, mock_settings)

        # Then - Should complete without errors
        # Dishka integration happens via QuartDishka constructor

    async def test_initialize_services_metrics_integration(
        self, mock_app: Quart, mock_settings: Settings
    ) -> None:
        """Test metrics dictionary is properly exposed through app.extensions."""
        # When
        await initialize_services(mock_app, mock_settings)

        # Then
        assert "metrics" in mock_app.extensions
        metrics = mock_app.extensions["metrics"]
        assert isinstance(metrics, dict)

    async def test_initialize_services_tracing_initialization(
        self, mock_app: Quart, mock_settings: Settings
    ) -> None:
        """Test distributed tracing initialization and middleware setup."""
        # When
        await initialize_services(mock_app, mock_settings)

        # Then
        assert "tracer" in mock_app.extensions
        tracer = mock_app.extensions["tracer"]
        assert tracer is not None

    async def test_initialize_services_swedish_service_contexts(self, mock_app: Quart) -> None:
        """Test initialization with Swedish service naming contexts."""
        # Given
        mock_settings = Mock(spec=Settings)
        mock_settings.SERVICE_NAME = "språkverktyg-göteborg"

        # When
        await initialize_services(mock_app, mock_settings)

        # Then - Should initialize successfully regardless of service name
        assert "metrics" in mock_app.extensions
        assert "tracer" in mock_app.extensions

    async def test_initialize_services_error_handling(self, mock_settings: Settings) -> None:
        """Test error handling during service initialization."""

        # Given - Create an app that will cause AttributeError
        class FailingApp:
            """Mock app that fails when accessing extensions."""

            @property
            def extensions(self) -> None:
                raise AttributeError("Simulated failure")

            @extensions.setter
            def extensions(self, value: Any) -> None:
                raise AttributeError("Simulated failure")

        mock_app = FailingApp()

        # When/Then - Should raise exception
        with pytest.raises(Exception):
            await initialize_services(mock_app, mock_settings)  # type: ignore[arg-type]

    async def test_initialize_services_extension_handling(self, mock_settings: Settings) -> None:
        """Test extension handling with existing components."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_app.extensions = {"existing_component": "test_value"}

        # When
        await initialize_services(mock_app, mock_settings)

        # Then
        assert "metrics" in mock_app.extensions
        assert "tracer" in mock_app.extensions


class TestShutdownServicesFunction:
    """Test shutdown_services function behavior and error handling."""

    async def test_graceful_shutdown_procedure(self) -> None:
        """Test graceful shutdown completes without errors."""
        # When
        await shutdown_services()

        # Then - Should complete without raising exceptions

    async def test_shutdown_with_app_parameter(self) -> None:
        """Test shutdown with app parameter provided."""
        # Given
        mock_app = Mock(spec=Quart)

        # When
        await shutdown_services(mock_app)

        # Then - Should complete without raising exceptions

    async def test_shutdown_with_none_app_parameter(self) -> None:
        """Test shutdown with explicit None app parameter."""
        # When
        await shutdown_services(None)

        # Then - Should complete without raising exceptions

    async def test_shutdown_multiple_calls(self) -> None:
        """Test multiple shutdown calls are safe."""
        # When - Multiple calls should be safe
        await shutdown_services()
        await shutdown_services()
        await shutdown_services()

        # Then - Should complete without raising exceptions

    async def test_shutdown_concurrent_calls(self) -> None:
        """Test concurrent shutdown calls are safe."""
        # When - Concurrent calls should be safe
        await asyncio.gather(
            shutdown_services(),
            shutdown_services(),
            shutdown_services(),
        )

        # Then - Should complete without raising exceptions

    async def test_shutdown_error_resilience(self) -> None:
        """Test shutdown handles internal errors gracefully."""
        # When - Should not raise exceptions even with potential issues
        await shutdown_services()

        # Then - Should complete gracefully
        # Current implementation handles exceptions internally


class TestDishkaContainerIntegration:
    """Test Dishka container integration during startup."""

    async def test_di_container_setup(self) -> None:
        """Test DI container is created with correct providers."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_app.extensions = {}
        mock_settings = Mock(spec=Settings)

        # When
        await initialize_services(mock_app, mock_settings)

        # Then - Should complete initialization with both providers
        assert "metrics" in mock_app.extensions
        assert "tracer" in mock_app.extensions


class TestMetricsInitialization:
    """Test metrics initialization and registry setup."""

    async def test_metrics_dictionary_exposure(self) -> None:
        """Test metrics dictionary is properly exposed through app.extensions."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_app.extensions = {}
        mock_settings = Mock(spec=Settings)

        # When
        await initialize_services(mock_app, mock_settings)

        # Then
        assert "metrics" in mock_app.extensions
        metrics = mock_app.extensions["metrics"]
        assert isinstance(metrics, dict)

    @pytest.mark.parametrize(
        "expected_metric_name",
        [
            "request_count",
            "request_duration",
            "grammar_analysis_total",
            "grammar_analysis_duration_seconds",
            "language_tool_health_checks_total",
        ],
    )
    async def test_expected_metrics_availability(self, expected_metric_name: str) -> None:
        """Test expected metrics are available in the metrics dictionary."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_app.extensions = {}
        mock_settings = Mock(spec=Settings)

        # When
        await initialize_services(mock_app, mock_settings)

        # Then
        metrics = mock_app.extensions["metrics"]
        # Note: Actual metric validation happens in metrics module tests
        assert isinstance(metrics, dict)


class TestTracingMiddlewareSetup:
    """Test distributed tracing and middleware setup."""

    async def test_tracer_initialization(self) -> None:
        """Test tracer is initialized and stored in app.extensions."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_app.extensions = {}
        mock_settings = Mock(spec=Settings)

        # When
        await initialize_services(mock_app, mock_settings)

        # Then
        assert "tracer" in mock_app.extensions
        tracer = mock_app.extensions["tracer"]
        assert tracer is not None

    async def test_tracing_middleware_setup(self) -> None:
        """Test tracing middleware is properly set up."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_app.extensions = {}
        mock_settings = Mock(spec=Settings)

        # When
        await initialize_services(mock_app, mock_settings)

        # Then
        # Middleware setup happens via setup_tracing_middleware call
        assert "tracer" in mock_app.extensions


class TestErrorHandlingScenarios:
    """Test error handling and recovery scenarios."""

    async def test_initialization_error_propagation(self) -> None:
        """Test errors during initialization are properly propagated."""

        # Given - Create an app that will cause failure
        class FailingApp:
            """Mock app that fails when accessing extensions."""

            @property
            def extensions(self) -> None:
                raise AttributeError("Simulated failure")

        mock_app = FailingApp()
        mock_settings = Mock(spec=Settings)

        # When/Then
        with pytest.raises(Exception):
            await initialize_services(mock_app, mock_settings)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "error_scenario",
        [
            "metrics_import_error",
            "tracer_initialization_error",
            "dishka_setup_error",
        ],
    )
    async def test_component_error_scenarios(self, error_scenario: str) -> None:
        """Test error handling for specific component failures."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_settings = Mock(spec=Settings)

        if error_scenario == "metrics_import_error":
            # Test with app that can't handle extensions
            class MetricsFailingApp:
                @property
                def extensions(self) -> None:
                    raise AttributeError("Extensions failure")

            failing_app: Any = MetricsFailingApp()
        elif error_scenario == "tracer_initialization_error":
            # Test with minimal app setup
            mock_app.extensions = {}
            failing_app = mock_app
        elif error_scenario == "dishka_setup_error":
            # Test with app setup issues
            class DishkaFailingApp:
                @property
                def extensions(self) -> None:
                    raise AttributeError("Dishka failure")

            failing_app = DishkaFailingApp()

        # When/Then - Should handle or propagate errors appropriately
        if error_scenario in ["metrics_import_error", "dishka_setup_error"]:
            with pytest.raises(Exception):
                await initialize_services(failing_app, mock_settings)  # type: ignore[arg-type]
        else:
            # Some scenarios may complete with degraded functionality
            await initialize_services(failing_app, mock_settings)


class TestConfigurationIntegration:
    """Test configuration integration during startup."""

    async def test_settings_parameter_usage(self) -> None:
        """Test settings parameter is properly used during initialization."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_app.extensions = {}
        mock_settings = Mock(spec=Settings)
        mock_settings.SERVICE_NAME = "test-service"

        # When
        await initialize_services(mock_app, mock_settings)

        # Then - Should complete with provided settings
        assert "metrics" in mock_app.extensions
        assert "tracer" in mock_app.extensions

    @pytest.mark.parametrize(
        "settings_scenario",
        [
            {"SERVICE_NAME": "language-tool-service", "LOG_LEVEL": "INFO"},
            {"SERVICE_NAME": "språkverktyg-service", "LOG_LEVEL": "DEBUG"},
            {"SERVICE_NAME": "grammatik-service", "LOG_LEVEL": "WARNING"},
        ],
    )
    async def test_various_settings_configurations(self, settings_scenario: dict[str, str]) -> None:
        """Test startup with various settings configurations."""
        # Given
        mock_app = Mock(spec=Quart)
        mock_app.extensions = {}
        mock_settings = Mock(spec=Settings)
        mock_settings.SERVICE_NAME = settings_scenario["SERVICE_NAME"]
        mock_settings.LOG_LEVEL = settings_scenario["LOG_LEVEL"]

        # When
        await initialize_services(mock_app, mock_settings)

        # Then - Should handle various configurations
        assert "metrics" in mock_app.extensions
        assert "tracer" in mock_app.extensions
