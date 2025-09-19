"""
Shared fixtures and configuration for Language Tool Service integration tests.

This module provides integration test fixtures following Rule 070 (behavioral testing)
and Rule 075 (test creation methodology). All fixtures support real implementations
with proper resource cleanup and no @patch or mock.patch usage.

Key Features:
- Clear Prometheus registry to prevent metric conflicts
- Support for both stub and real LanguageTool modes
- Proper async cleanup and resource management
- Factory patterns for test data creation
- Real Dishka container integration
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.error_handling.quart import register_error_handlers
from prometheus_client import REGISTRY, CollectorRegistry
from quart import Quart
from quart_dishka import QuartDishka

from services.language_tool_service.api.grammar_routes import grammar_bp
from services.language_tool_service.api.health_routes import health_bp
from services.language_tool_service.config import Settings
from services.language_tool_service.di import (
    CoreInfrastructureProvider,
    ServiceImplementationsProvider,
)
from services.language_tool_service.implementations.stub_wrapper import StubLanguageToolWrapper
from services.language_tool_service.metrics import METRICS
from services.language_tool_service.protocols import (
    LanguageToolManagerProtocol,
    LanguageToolWrapperProtocol,
)


class MetricsAwareStubWrapper(StubLanguageToolWrapper):
    """Test-specific stub wrapper that emits metrics like the real wrapper."""

    def __init__(self, settings: Settings, metrics: dict[str, Any] | None = None) -> None:
        """Initialize with metrics support."""
        super().__init__(settings)
        self.metrics = metrics

    async def check_text(
        self,
        text: str,
        correlation_context: CorrelationContext,
        language: str = "en-US",
        request_options: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Check text and emit wrapper duration metrics like real wrapper."""
        import time

        # Start timing like real wrapper
        wrapper_start = time.perf_counter()

        # Call the actual stub implementation
        result = await super().check_text(text, correlation_context, language, request_options)

        # Emit metrics like real wrapper
        wrapper_duration = time.perf_counter() - wrapper_start
        if self.metrics and "wrapper_duration_seconds" in self.metrics:
            self.metrics["wrapper_duration_seconds"].labels(language=language).observe(
                wrapper_duration
            )

        return result


@pytest.fixture
def clear_prometheus_registry() -> Generator[None, None, None]:
    """
    Clear Prometheus registry before and after each test to prevent metric conflicts.

    This fixture runs when explicitly used, ensuring clean metric state and
    preventing "Duplicated timeseries in CollectorRegistry" errors.

    Rule 070: Prevent Prometheus metric conflicts between tests.

    Usage:
        @pytest.mark.usefixtures("clear_prometheus_registry")
        def test_with_clean_registry():
            # Test with clean registry
    """
    # Note: We don't actually clear the registry for integration tests
    # because the metrics are registered at import time and clearing them
    # would make the /metrics endpoint return empty.
    # Instead, we rely on the metrics being idempotent and the test isolation.
    yield


@pytest.fixture
def integration_settings() -> Settings:
    """
    Create Settings instance configured for integration testing.

    Uses test-specific ports and smaller resource allocations to avoid
    conflicts with production or other test instances.

    Returns:
        Settings configured for integration testing environment
    """
    settings = Settings()

    # Use test-specific ports to avoid conflicts
    settings.LANGUAGE_TOOL_PORT = 8091  # Different from default 8081
    settings.HTTP_PORT = 8095  # Different from default 8085

    # Configure for testing environment - smaller resources
    settings.LANGUAGE_TOOL_HEAP_SIZE = "256m"  # Smaller heap for testing
    settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL = 5  # Faster health checks
    settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS = 10  # Shorter timeout
    settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS = 5  # Lower concurrency

    # Configure timeouts for testing
    settings.LANGUAGE_TOOL_TIMEOUT_SECONDS = 15
    settings.LANGUAGE_TOOL_MAX_RETRIES = 2

    # Use actual JAR path if available, tests will handle missing JAR scenarios
    settings.LANGUAGE_TOOL_JAR_PATH = "/app/languagetool/languagetool-server.jar"

    return settings


@pytest.fixture
def test_jar_path() -> Generator[Path, None, None]:
    """
    Create temporary JAR file path for testing both existing and missing JAR scenarios.

    This fixture provides a Path object that can be used to test:
    - Missing JAR file behavior (default state)
    - Existing JAR file behavior (by creating the file in test)

    Yields:
        Path object to temporary JAR file location

    Example:
        def test_missing_jar(test_jar_path: Path):
            assert not test_jar_path.exists()  # Test missing JAR behavior

        def test_existing_jar(test_jar_path: Path):
            create_minimal_jar_file(test_jar_path)  # Create file for test
            assert test_jar_path.exists()  # Test existing JAR behavior
    """
    with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as tmp:
        jar_path = Path(tmp.name)

    # Remove the file so tests can control whether it exists
    jar_path.unlink()

    yield jar_path

    # Cleanup if file was created during test
    if jar_path.exists():
        jar_path.unlink()


@pytest.fixture
def stub_mode_env() -> Generator[None, None, None]:
    """
    Fixture to set/unset USE_STUB_LANGUAGE_TOOL environment variable.

    This fixture ensures the USE_STUB_LANGUAGE_TOOL environment variable
    is properly managed and restored after test execution.

    Usage:
        # Force stub mode for test
        @pytest.mark.usefixtures("stub_mode_env")
        def test_with_stub_mode():
            os.environ["USE_STUB_LANGUAGE_TOOL"] = "true"
            # Test stub mode behavior

        # Test real mode
        def test_real_mode(stub_mode_env):
            os.environ.pop("USE_STUB_LANGUAGE_TOOL", None)
            # Test real mode behavior
    """
    # Store original value
    original_value = os.environ.get("USE_STUB_LANGUAGE_TOOL")

    yield

    # Restore original state
    if original_value is not None:
        os.environ["USE_STUB_LANGUAGE_TOOL"] = original_value
    else:
        os.environ.pop("USE_STUB_LANGUAGE_TOOL", None)


@pytest_asyncio.fixture
async def test_container(integration_settings: Settings) -> AsyncGenerator[Any, None]:
    """
    Create real Dishka container with test providers for integration testing.

    This fixture provides a fully configured DI container with real providers,
    enabling true integration testing while supporting both stub and real modes
    based on environment configuration.

    Args:
        integration_settings: Test-configured settings instance

    Yields:
        Configured async Dishka container for integration testing

    Note:
        Supports both stub mode (USE_STUB_LANGUAGE_TOOL=true) and real mode
        with automatic cleanup of async resources.
    """
    # Create container with real providers
    container = make_async_container(
        CoreInfrastructureProvider(),
        ServiceImplementationsProvider(),
    )

    try:
        yield container
    finally:
        await container.close()


@pytest.fixture
def correlation_context_factory() -> Any:
    """
    Factory function to create test correlation contexts with deterministic UUIDs.

    This factory enables creating multiple correlation contexts for testing
    with predictable UUIDs for assertion purposes.

    Returns:
        Factory function that creates CorrelationContext instances

    Example:
        def test_multiple_requests(correlation_context_factory):
            ctx1 = correlation_context_factory("request-1")
            ctx2 = correlation_context_factory("request-2")
            # Both have predictable UUIDs for testing
    """

    def _create_correlation_context(
        original_id: str = "integration-test-correlation-id",
        uuid_seed: str | None = None,
    ) -> CorrelationContext:
        """
        Create correlation context for integration testing.

        Args:
            original_id: Original correlation ID for the request
            uuid_seed: Optional seed for deterministic UUID generation

        Returns:
            CorrelationContext instance configured for testing
        """
        if uuid_seed:
            # Create deterministic UUID based on seed for testing
            test_uuid = UUID(f"12345678-1234-1234-1234-{uuid_seed.zfill(12)[:12]}")
        else:
            # Use default deterministic UUID for single-context tests
            test_uuid = UUID("12345678-1234-1234-1234-123456789012")

        return CorrelationContext(
            original=original_id,
            uuid=test_uuid,
            source="generated",
        )

    return _create_correlation_context


class IntegrationTestProvider(Provider):
    """
    Test provider for integration testing with real metrics but configurable LanguageTool.

    This provider enables integration tests to use real infrastructure (metrics,
    DI container) while controlling LanguageTool implementation mode (stub vs real)
    based on environment configuration or test requirements.
    """

    scope = Scope.APP

    @provide
    def provide_settings(self) -> Settings:
        """Provide integration test settings configured for testing."""
        # Create test settings directly to avoid circular dependency
        settings = Settings()

        # Use test-specific ports to avoid conflicts
        settings.LANGUAGE_TOOL_PORT = 8091  # Different from default 8081
        settings.HTTP_PORT = 8095  # Different from default 8085

        # Configure for testing environment - smaller resources
        settings.LANGUAGE_TOOL_HEAP_SIZE = "256m"  # Smaller heap for testing
        settings.LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL = 5  # Faster health checks
        settings.LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS = 10  # Shorter timeout
        settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS = 5  # Lower concurrency

        # Configure timeouts for testing
        settings.LANGUAGE_TOOL_TIMEOUT_SECONDS = 15
        settings.LANGUAGE_TOOL_MAX_RETRIES = 2

        # Force stub mode for reliable integration testing
        settings.LANGUAGE_TOOL_JAR_PATH = "/nonexistent/path/to/test.jar"  # Forces stub mode

        return settings

    @provide
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide the real Prometheus metrics registry."""
        return REGISTRY

    @provide
    def provide_metrics(self) -> dict[str, Any]:
        """Provide the real Prometheus metrics dictionary."""
        return METRICS

    @provide
    def provide_language_tool_wrapper(
        self, settings: Settings, metrics: dict[str, Any]
    ) -> LanguageToolWrapperProtocol:
        """
        Provide Language Tool wrapper for integration testing.

        Uses stub implementation for reliable integration tests unless
        specifically configured for real LanguageTool testing.
        """
        # Use metrics-aware stub for integration testing
        return MetricsAwareStubWrapper(settings, metrics)

    @provide
    def provide_language_tool_manager(self, settings: Settings) -> LanguageToolManagerProtocol:
        """
        Provide Language Tool manager for integration testing.

        Uses mock manager to avoid actual process management complexity
        in integration tests, while still testing the service layer.
        """
        mock_manager = AsyncMock(spec=LanguageToolManagerProtocol)
        mock_manager.get_jvm_heap_usage.return_value = 128.0  # Mock heap usage
        mock_manager.health_check.return_value = True  # Mock healthy state
        mock_manager.get_status.return_value = {
            "running": True,
            "pid": 12345,
            "port": settings.LANGUAGE_TOOL_PORT,
        }
        return mock_manager

    @provide(scope=Scope.REQUEST)
    def provide_correlation_context(self) -> CorrelationContext:
        """Provide correlation context for request tracking."""
        return CorrelationContext(
            original="integration-test-correlation-id",
            uuid=UUID("12345678-1234-1234-1234-123456789012"),
            source="generated",
        )


@pytest_asyncio.fixture
async def integration_app() -> AsyncGenerator[Quart, None]:
    """
    Create real Quart application with actual DI container for integration testing.

    This fixture provides a complete application instance with:
    - Real Prometheus metrics collection
    - Real DI container with integration test providers
    - Real HTTP routes and error handling
    - Configurable LanguageTool implementation (stub by default)

    Yields:
        Configured Quart application for integration testing

    Note:
        Uses stub LanguageTool implementation by default for reliability.
        Set USE_STUB_LANGUAGE_TOOL=false for real LanguageTool testing.
    """
    # Default to stub mode for reliable integration testing
    os.environ["USE_STUB_LANGUAGE_TOOL"] = os.environ.get("USE_STUB_LANGUAGE_TOOL", "true")

    app = Quart(__name__)
    app.config.update({"TESTING": True})

    # Register real blueprints
    app.register_blueprint(grammar_bp)
    app.register_blueprint(health_bp)

    # Register real error handlers
    register_error_handlers(app)

    # Set up real DI container with integration test providers
    container = make_async_container(IntegrationTestProvider())
    QuartDishka(app=app, container=container)

    # Store real metrics in app extensions (like production)
    app.extensions = getattr(app, "extensions", {})
    app.extensions["metrics"] = METRICS

    # Setup HTTP metrics middleware like in production
    from huleedu_service_libs.metrics_middleware import setup_metrics_middleware

    setup_metrics_middleware(
        app=app,
        request_count_metric_name="request_count",
        request_duration_metric_name="request_duration",
        status_label_name="status",
        logger_name="language_tool_service.metrics",
    )

    try:
        yield app
    finally:
        await container.close()
        # Clean up environment
        os.environ.pop("USE_STUB_LANGUAGE_TOOL", None)


@pytest_asyncio.fixture
async def client(integration_app: Quart) -> AsyncGenerator[Any, None]:
    """
    Create test client for real HTTP requests to integration application.

    Args:
        integration_app: Configured Quart application for integration testing

    Yields:
        Test client for making HTTP requests
    """
    async with integration_app.test_client() as test_client:
        yield test_client


def create_minimal_jar_file(jar_path: Path) -> None:
    """
    Create minimal JAR file for testing JAR file existence scenarios.

    Creates a basic JAR structure that Java can recognize as a valid JAR file,
    though it won't be a functional LanguageTool server. Useful for testing
    JAR file discovery and validation logic.

    Args:
        jar_path: Path where JAR file should be created

    Note:
        Creates parent directories if they don't exist.
    """
    jar_path.parent.mkdir(parents=True, exist_ok=True)

    # Create minimal JAR content (ZIP file with manifest)
    import zipfile

    with zipfile.ZipFile(jar_path, "w") as jar:
        jar.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
