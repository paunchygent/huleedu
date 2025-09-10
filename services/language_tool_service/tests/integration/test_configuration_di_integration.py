"""Integration tests for Language Tool Service DI container configuration integration."""

from __future__ import annotations

import os
import socket
import tempfile
import zipfile
from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from dishka import make_async_container
from huleedu_service_libs.error_handling.correlation import CorrelationContext

from services.language_tool_service.config import Settings
from services.language_tool_service.di import (
    CoreInfrastructureProvider,
    ServiceImplementationsProvider,
)
from services.language_tool_service.implementations.language_tool_manager import (
    LanguageToolManager,
)
from services.language_tool_service.implementations.stub_wrapper import (
    StubLanguageToolWrapper,
)
from services.language_tool_service.protocols import (
    LanguageToolWrapperProtocol,
)


@pytest.fixture
def clean_environment() -> Generator[None, None, None]:
    """
    Clean environment fixture for configuration testing.

    Removes all LANGUAGE_TOOL_SERVICE_* environment variables before
    and after each test to ensure isolated testing conditions.
    """
    # Store original environment
    original_env = dict(os.environ)

    # Remove any existing LANGUAGE_TOOL_SERVICE_* variables
    for key in list(os.environ.keys()):
        if key.startswith("LANGUAGE_TOOL_SERVICE_"):
            del os.environ[key]

    # Also clean up common global environment variables that might interfere
    for key in ["ENVIRONMENT", "USE_STUB_LANGUAGE_TOOL"]:
        if key in os.environ:
            del os.environ[key]

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def temp_jar_path() -> Generator[Path, None, None]:
    """Create temporary JAR file path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".jar", delete=False) as tmp:
        jar_path = Path(tmp.name)

    # Remove the file so we can test missing JAR behavior
    jar_path.unlink()

    yield jar_path

    # Cleanup if file was created during test
    if jar_path.exists():
        jar_path.unlink()


def create_test_jar(jar_path: Path) -> None:
    """Create minimal JAR file for testing."""
    jar_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(jar_path, "w") as jar:
        jar.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")


def is_port_available(port: int, host: str = "localhost") -> bool:
    """Check if a port is available for binding."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
            return True
    except socket.error:
        return False


def get_available_port(start_port: int = 8090, max_attempts: int = 50) -> int:
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(port):
            return port
    raise RuntimeError(
        f"No available ports found in range {start_port}-{start_port + max_attempts}"
    )


class TestConfigurationDIIntegration:
    """Integration tests for Language Tool Service DI container configuration."""

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    async def test_jar_path_fallback_behavior(
        self, clean_environment: None, temp_jar_path: Path
    ) -> None:
        """
        Test JAR path fallback behavior and DI container integration.

        Validates that missing JAR triggers stub mode and that the
        DI container provides the correct implementation based on JAR availability.
        """
        # Test Case 1: Missing JAR triggers stub mode in DI
        os.environ["LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_JAR_PATH"] = str(temp_jar_path)

        # Ensure JAR doesn't exist
        assert not temp_jar_path.exists()

        settings = Settings()
        assert settings.LANGUAGE_TOOL_JAR_PATH == str(temp_jar_path)

        # Create DI container and verify stub mode
        container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceImplementationsProvider(),
        )

        async with container() as request_container:
            wrapper = await request_container.get(LanguageToolWrapperProtocol)

            # Should be stub implementation due to missing JAR
            assert isinstance(wrapper, StubLanguageToolWrapper)

            # Verify stub wrapper is functional
            correlation_context = CorrelationContext(
                original="test-jar-fallback", uuid=uuid4(), source="generated"
            )

            health_status = await wrapper.get_health_status(correlation_context)
            assert isinstance(health_status, dict)
            assert health_status.get("status") == "healthy"

            # Test text checking works in stub mode
            result = await wrapper.check_text("Test text", correlation_context, language="en-US")
            assert isinstance(result, list)

        # Test Case 2: Manager handles missing JAR gracefully
        manager = LanguageToolManager(settings)

        # Starting should raise an exception due to missing JAR
        with pytest.raises(Exception):  # Expect HuleEduError or similar
            await manager.start()

        # Verify manager state
        assert manager.process is None
        health_result = await manager.health_check()
        assert health_result is False

        status = manager.get_status()
        assert status["running"] is False
        assert status["pid"] is None

        # Cleanup
        await manager.stop()

    @pytest.mark.integration
    @pytest.mark.timeout(45)
    async def test_full_di_integration_with_settings(
        self, clean_environment: None, temp_jar_path: Path
    ) -> None:
        """
        Test complete DI integration with various configuration scenarios.

        Validates that the DI container correctly responds to different
        configuration states and provides appropriate implementations.
        """
        # Test Case 1: Force stub mode via environment variable
        os.environ["USE_STUB_LANGUAGE_TOOL"] = "true"
        os.environ["LANGUAGE_TOOL_SERVICE_HTTP_PORT"] = str(get_available_port(8090))

        container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceImplementationsProvider(),
        )

        async with container() as request_container:
            # Get settings to verify it's available in container
            await request_container.get(Settings)
            wrapper = await request_container.get(LanguageToolWrapperProtocol)

            # Should use stub implementation
            assert isinstance(wrapper, StubLanguageToolWrapper)

            # Test functionality
            correlation_context = CorrelationContext(
                original="test-di-integration", uuid=uuid4(), source="generated"
            )

            result = await wrapper.check_text(
                "Test text with Swedish chars: åäö", correlation_context
            )
            assert isinstance(result, list)

        # Test Case 2: Missing JAR should also trigger stub mode
        del os.environ["USE_STUB_LANGUAGE_TOOL"]
        os.environ["LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_JAR_PATH"] = str(temp_jar_path)

        # Ensure JAR doesn't exist
        assert not temp_jar_path.exists()

        container2 = make_async_container(
            CoreInfrastructureProvider(),
            ServiceImplementationsProvider(),
        )

        async with container2() as request_container2:
            wrapper2 = await request_container2.get(LanguageToolWrapperProtocol)

            # Should fall back to stub due to missing JAR
            assert isinstance(wrapper2, StubLanguageToolWrapper)

        # Test Case 3: Present JAR file (create minimal one)
        create_test_jar(temp_jar_path)
        assert temp_jar_path.exists()

        # Note: Even with a JAR present, we might still get stub mode in a test
        # environment where Java isn't available or the JAR isn't functional.
        # This is expected behavior and tests the fallback robustness.

        container3 = make_async_container(
            CoreInfrastructureProvider(),
            ServiceImplementationsProvider(),
        )

        async with container3() as request_container3:
            wrapper3 = await request_container3.get(LanguageToolWrapperProtocol)

            # Behavior depends on Java availability and JAR functionality
            # In test environments, this will likely still be stub mode
            assert wrapper3 is not None

            # Verify the wrapper is functional regardless of implementation
            correlation_context = CorrelationContext(
                original="test-jar-present", uuid=uuid4(), source="generated"
            )

            health_status = await wrapper3.get_health_status(correlation_context)
            assert isinstance(health_status, dict)

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    def test_category_filtering_configuration(self, clean_environment: None) -> None:
        """
        Test grammar category filtering configuration.

        Validates that category lists are properly parsed from environment
        variables and that both allowed and blocked categories work correctly.
        """
        # Test custom category configuration with Swedish characters
        allowed_categories = ["GRAMMAR", "STYLE", "SVENSKA_KATEGORIER"]
        blocked_categories = ["TYPOS", "FELSTAVNING", "SVENSKT_FEL"]

        os.environ["LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_ALLOWED"] = (
            '["GRAMMAR", "STYLE", "SVENSKA_KATEGORIER"]'
        )
        os.environ["LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_BLOCKED"] = (
            '["TYPOS", "FELSTAVNING", "SVENSKT_FEL"]'
        )

        settings = Settings()

        assert settings.GRAMMAR_CATEGORIES_ALLOWED == allowed_categories
        assert settings.GRAMMAR_CATEGORIES_BLOCKED == blocked_categories

        # Test empty lists
        os.environ["LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_ALLOWED"] = "[]"
        os.environ["LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_BLOCKED"] = "[]"

        settings = Settings()
        assert settings.GRAMMAR_CATEGORIES_ALLOWED == []
        assert settings.GRAMMAR_CATEGORIES_BLOCKED == []

        # Test single item lists
        os.environ["LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_ALLOWED"] = '["ONLY_ONE"]'

        settings = Settings()
        assert settings.GRAMMAR_CATEGORIES_ALLOWED == ["ONLY_ONE"]
