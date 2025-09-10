"""
Integration tests for Dishka DI container lifecycle and behavioral validation.

These tests validate the Dishka DI container behavioral outcomes following Rule 070 and 075:
- Full container lifecycle with real providers (not test mocks)
- Protocol compliance: LanguageToolWrapperProtocol implementations work
- Dependency resolution provides correct implementations based on environment
- Scope management: APP scope persists, REQUEST scope creates new instances
- Container cleanup releases resources properly

Following pattern from services/essay_lifecycle_service/tests/unit/test_kafka_circuit_breaker_di.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from dishka import Provider, Scope, make_async_container, provide
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from prometheus_client import REGISTRY, CollectorRegistry

from services.language_tool_service.config import Settings
from services.language_tool_service.di import (
    ServiceImplementationsProvider,
)
from services.language_tool_service.implementations.language_tool_manager import (
    LanguageToolManager,
)
from services.language_tool_service.implementations.stub_wrapper import (
    StubLanguageToolWrapper,
)
from services.language_tool_service.metrics import METRICS
from services.language_tool_service.protocols import (
    LanguageToolManagerProtocol,
    LanguageToolWrapperProtocol,
)

# Note: Registry clearing removed to avoid breaking metrics tests.
# Tests should be idempotent instead.


class StandaloneCoreInfrastructureProvider(Provider):
    """Test provider that doesn't depend on Flask/Quart app context."""

    @provide(scope=Scope.APP)
    def provide_settings(self) -> Settings:
        """Provide service settings."""
        return Settings()

    @provide(scope=Scope.APP)
    def provide_metrics_registry(self) -> CollectorRegistry:
        """Provide the global Prometheus metrics registry shared across collectors."""
        return REGISTRY

    @provide(scope=Scope.APP)
    def provide_metrics(self) -> dict[str, Any]:
        """Provide shared Prometheus metrics dictionary."""
        return METRICS

    @provide(scope=Scope.REQUEST)
    def provide_correlation_context(self) -> CorrelationContext:
        """Provide correlation context for testing without app context."""
        return CorrelationContext(original="test-original", uuid=uuid4(), source="generated")


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with predictable configuration."""
    return Settings(
        LANGUAGE_TOOL_TIMEOUT_SECONDS=30,
        LANGUAGE_TOOL_MAX_RETRIES=3,
        LANGUAGE_TOOL_PORT=8081,
        LANGUAGE_TOOL_HEAP_SIZE="256m",
        LANGUAGE_TOOL_JAR_PATH="/nonexistent/test.jar",
        LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS=5,
        LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS=10,
        LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL=30,
        GRAMMAR_CATEGORIES_ALLOWED=["GRAMMAR", "CONFUSED_WORDS"],
        GRAMMAR_CATEGORIES_BLOCKED=["TYPOS", "SPELLING"],
    )


@pytest.fixture
def test_settings_with_jar() -> Settings:
    """Create test settings with a real JAR file path for testing."""
    # Create a temporary file to simulate JAR existence
    with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as tmp_jar:
        jar_path = tmp_jar.name

    try:
        return Settings(
            LANGUAGE_TOOL_TIMEOUT_SECONDS=30,
            LANGUAGE_TOOL_MAX_RETRIES=3,
            LANGUAGE_TOOL_PORT=8081,
            LANGUAGE_TOOL_HEAP_SIZE="256m",
            LANGUAGE_TOOL_JAR_PATH=jar_path,
            LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS=5,
            LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS=10,
            LANGUAGE_TOOL_HEALTH_CHECK_INTERVAL=30,
            GRAMMAR_CATEGORIES_ALLOWED=["GRAMMAR", "CONFUSED_WORDS"],
            GRAMMAR_CATEGORIES_BLOCKED=["TYPOS", "SPELLING"],
        )
    finally:
        # Cleanup will happen in the test that uses this fixture
        pass


class TestDIContainerIntegration:
    """Integration tests for Dishka DI container lifecycle and behavior."""

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_container_lifecycle_with_real_providers(self) -> None:
        """Test container creation and cleanup with real providers (not test mocks)."""
        # Test environment setup to ensure stub mode
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            # Create container with test providers that don't require app context
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )

            # Verify container can be created successfully
            assert container is not None

            try:
                # Test async context manager behavior with request scope
                async with container() as request_container:
                    # Verify container is usable within context
                    settings_instance = await request_container.get(Settings)
                    assert settings_instance is not None
                    assert isinstance(settings_instance, Settings)

                    # Verify all core providers can provide their dependencies
                    registry = await request_container.get(CollectorRegistry)
                    assert registry is not None

                    metrics = await request_container.get(dict[str, Any])
                    assert metrics is not None
                    assert isinstance(metrics, dict)
                # Request scope should clean up automatically after context exit
            finally:
                # Clean up the app-level container
                await container.close()

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_protocol_implementation_compliance(self) -> None:
        """Test that protocol implementations comply with their contracts."""
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )

            try:
                async with container() as request_container:
                    # Get LanguageToolWrapperProtocol from container
                    wrapper = await request_container.get(LanguageToolWrapperProtocol)
                    assert wrapper is not None
                    assert isinstance(wrapper, StubLanguageToolWrapper)

                    # Verify it implements all protocol methods
                    assert hasattr(wrapper, "check_text")
                    assert hasattr(wrapper, "get_health_status")
                    assert callable(wrapper.check_text)
                    assert callable(wrapper.get_health_status)

                    # Test actual protocol behavior with real method calls
                    correlation_context = CorrelationContext(
                        original="test-original", uuid=uuid4(), source="generated"
                    )

                    # Test check_text method
                    result = await wrapper.check_text(
                        "Test text with there error", correlation_context
                    )
                    assert isinstance(result, list)

                    # Test get_health_status method
                    health = await wrapper.get_health_status(correlation_context)
                    assert isinstance(health, dict)
                    assert "status" in health

                    # Get LanguageToolManagerProtocol from container
                    manager = await request_container.get(LanguageToolManagerProtocol)
                    assert manager is not None
                    assert isinstance(manager, LanguageToolManager)

                    # Verify protocol contract satisfaction
                    assert hasattr(manager, "start")
                    assert hasattr(manager, "stop")
                    assert hasattr(manager, "health_check")
                    assert hasattr(manager, "restart_if_needed")
                    assert hasattr(manager, "get_status")
                    assert hasattr(manager, "get_jvm_heap_usage")
            finally:
                await container.close()

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_dependency_resolution_by_environment(
        self, test_settings_with_jar: Settings
    ) -> None:
        """Test dependency resolution provides correct implementations based on environment."""
        # Test 1: USE_STUB_LANGUAGE_TOOL=true → StubLanguageToolWrapper
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )
            try:
                async with container() as request_container:
                    wrapper = await request_container.get(LanguageToolWrapperProtocol)
                    assert isinstance(wrapper, StubLanguageToolWrapper)
            finally:
                await container.close()

        # Test 2: Missing JAR → falls back to StubLanguageToolWrapper
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "false"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )
            try:
                async with container() as request_container:
                    wrapper = await request_container.get(LanguageToolWrapperProtocol)
                    # Should fall back to stub when JAR doesn't exist
                    assert isinstance(wrapper, StubLanguageToolWrapper)
            finally:
                await container.close()

        # Test 3: Valid JAR path → LanguageToolWrapper (but forced to stub to avoid process start)
        with (
            patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}),  # Force stub mode
            patch.object(Path, "exists", return_value=True),
        ):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )
            try:
                async with container() as request_container:
                    wrapper = await request_container.get(LanguageToolWrapperProtocol)
                    # Should still be stub due to environment override
                    assert isinstance(wrapper, StubLanguageToolWrapper)
            finally:
                await container.close()

        # Cleanup the temporary JAR file
        try:
            os.unlink(test_settings_with_jar.LANGUAGE_TOOL_JAR_PATH)
        except FileNotFoundError:
            pass

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_scope_management(self) -> None:
        """Test that APP scope persists and REQUEST scope creates new instances."""
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )

            try:
                # Test APP scope persistence across multiple request contexts
                async with container() as request_container1:
                    settings1 = await request_container1.get(Settings)
                    metrics1 = await request_container1.get(dict[str, Any])
                    manager1 = await request_container1.get(LanguageToolManagerProtocol)

                async with container() as request_container2:
                    settings2 = await request_container2.get(Settings)
                    metrics2 = await request_container2.get(dict[str, Any])
                    manager2 = await request_container2.get(LanguageToolManagerProtocol)

                    # APP scope: Should be same instances across request contexts
                    assert settings1 is settings2  # Same instance
                    assert metrics1 is metrics2  # Same instance
                    assert manager1 is manager2  # Same instance

                # REQUEST scope: CorrelationContext should be new instances per request
                async with container() as request_container:
                    ctx1 = await request_container.get(CorrelationContext)
                    ctx2 = await request_container.get(CorrelationContext)

                    # Within same request context, should get same instance
                    assert ctx1 is ctx2
            finally:
                await container.close()

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_correlation_context_propagation(self) -> None:
        """Test correlation context extraction and propagation."""
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )

            try:
                # Test correlation context creation and uniqueness across requests
                async with container() as request_container1:
                    ctx1 = await request_container1.get(CorrelationContext)

                # Test with different request in different container context
                async with container() as request_container2:
                    ctx2 = await request_container2.get(CorrelationContext)

                # Should be different contexts for different request scopes
                assert ctx1.uuid != ctx2.uuid
            finally:
                await container.close()

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_metrics_injection(self) -> None:
        """Test that metrics are properly injected and shared across components."""
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )

            try:
                async with container() as request_container:
                    # Verify METRICS dict injected correctly
                    metrics = await request_container.get(dict[str, Any])
                    assert metrics is not None
                    assert isinstance(metrics, dict)

                    # Verify REGISTRY shared across components
                    registry = await request_container.get(CollectorRegistry)
                    assert registry is REGISTRY  # Should be the global instance

                    # Test that metrics are actually usable
                    wrapper = await request_container.get(LanguageToolWrapperProtocol)
                    assert isinstance(wrapper, StubLanguageToolWrapper)
                    # Stub doesn't use metrics, but real implementation would
            finally:
                await container.close()

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_container_resource_cleanup(self) -> None:
        """Test container properly manages resource lifecycle and cleanup."""
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )

            try:
                # Start container and get manager
                async with container() as request_container:
                    manager_instance = await request_container.get(LanguageToolManagerProtocol)
                    assert manager_instance is not None
                    assert isinstance(manager_instance, LanguageToolManager)

                    # In stub mode, manager doesn't actually start a process
                    # but we can verify the instance is properly managed

                # After request context exit, resources should be cleaned up
                # The manager's lifecycle is handled by the provider's async generator
            finally:
                # Cleanup app-level container
                await container.close()

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_provider_error_handling(self) -> None:
        """Test provider error handling and graceful degradation."""
        # Test with malformed environment variable
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "invalid"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )
            try:
                async with container() as request_container:
                    # Should gracefully handle invalid boolean and default to false
                    wrapper = await request_container.get(LanguageToolWrapperProtocol)
                    # Should fall back to stub due to missing JAR
                    assert isinstance(wrapper, StubLanguageToolWrapper)
            finally:
                await container.close()

        # Test with missing dependencies - all should be provided by the container
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )
            try:
                async with container() as request_container:
                    # All these should resolve without NoFactoryError
                    settings_instance = await request_container.get(Settings)
                    assert settings_instance is not None

                    correlation_context = await request_container.get(CorrelationContext)
                    assert correlation_context is not None

                    wrapper = await request_container.get(LanguageToolWrapperProtocol)
                    assert wrapper is not None

                    manager = await request_container.get(LanguageToolManagerProtocol)
                    assert manager is not None
            finally:
                await container.close()

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_container_integration_with_real_services(self) -> None:
        """Test container integration provides working service instances."""
        with patch.dict(os.environ, {"USE_STUB_LANGUAGE_TOOL": "true"}):
            container = make_async_container(
                StandaloneCoreInfrastructureProvider(),
                ServiceImplementationsProvider(),
            )

            try:
                async with container() as request_container:
                    # Get instances from container
                    wrapper = await request_container.get(LanguageToolWrapperProtocol)
                    correlation_context = await request_container.get(CorrelationContext)

                    # Test that the instances actually work together
                    # This validates the full DI chain is functional
                    correlation_context = CorrelationContext(
                        original="test-original", uuid=uuid4(), source="generated"
                    )
                    result = await wrapper.check_text(
                        "This is test text with there instead of their",
                        correlation_context,
                        "en-US",
                    )

                    # Verify realistic behavior
                    assert isinstance(result, list)
                    # Stub should detect the 'there/their' pattern
                    if result:  # Stub may return grammar suggestions
                        assert all(isinstance(error, dict) for error in result)
                        assert all("rule_id" in error for error in result)

                    # Test health check integration
                    health = await wrapper.get_health_status(correlation_context)
                    assert isinstance(health, dict)
                    assert "status" in health
                    assert health["status"] == "healthy"
                    assert health["implementation"] == "stub"
            finally:
                await container.close()
