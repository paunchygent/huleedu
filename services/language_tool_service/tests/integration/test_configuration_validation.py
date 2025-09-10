"""Integration tests for Language Tool Service configuration validation and boundaries."""

from __future__ import annotations

import os
import socket
from collections.abc import Generator

import pytest
from pydantic import ValidationError

from services.language_tool_service.config import Settings


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


class TestConfigurationValidation:
    """Integration tests for Language Tool Service configuration validation."""

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    def test_invalid_configuration_rejection(self, clean_environment: None) -> None:
        """
        Test that invalid configuration values are properly rejected.

        Validates that malformed values trigger appropriate validation
        errors and that the service fails fast on invalid configuration.
        """
        # Test invalid port numbers that should fail validation
        invalid_port_cases = [
            ("LANGUAGE_TOOL_SERVICE_HTTP_PORT", "not_a_number"),
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_PORT", "invalid_port"),
        ]

        for env_var, invalid_value in invalid_port_cases:
            # Clear environment
            for key in list(os.environ.keys()):
                if key.startswith("LANGUAGE_TOOL_SERVICE_"):
                    del os.environ[key]

            os.environ[env_var] = invalid_value

            with pytest.raises(ValidationError) as exc_info:
                Settings()

            # Verify the error is about the problematic field
            error_message = str(exc_info.value)
            field_name = env_var.replace("LANGUAGE_TOOL_SERVICE_", "")
            assert field_name in error_message

        # Test invalid timeout values
        invalid_timeout_cases = [
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_TIMEOUT_SECONDS", "not_a_timeout"),
            ("LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_REQUEST_TIMEOUT_SECONDS", "invalid"),
        ]

        for env_var, invalid_value in invalid_timeout_cases:
            # Clear environment
            for key in list(os.environ.keys()):
                if key.startswith("LANGUAGE_TOOL_SERVICE_"):
                    del os.environ[key]

            os.environ[env_var] = invalid_value

            with pytest.raises(ValidationError):
                Settings()

        # Test invalid environment value
        os.environ["ENVIRONMENT"] = "invalid_environment"

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "ENVIRONMENT" in str(exc_info.value)

        # Test malformed JSON for category lists
        # Clear environment first
        for key in list(os.environ.keys()):
            if key.startswith("LANGUAGE_TOOL_SERVICE_"):
                del os.environ[key]

        os.environ["LANGUAGE_TOOL_SERVICE_GRAMMAR_CATEGORIES_ALLOWED"] = "not_json"

        # This should raise either ValidationError or SettingsError
        with pytest.raises((ValidationError, Exception)):
            Settings()

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    def test_heap_size_validation(self, clean_environment: None) -> None:
        """
        Test heap size configuration validation.

        Validates that various heap size formats are accepted
        and that the configuration is passed correctly to the manager.
        """
        from services.language_tool_service.implementations.language_tool_manager import (
            LanguageToolManager,
        )

        test_cases = [
            ("256m", "256m"),
            ("512m", "512m"),
            ("1g", "1g"),
            ("2048m", "2048m"),
            ("1G", "1G"),
            ("4096M", "4096M"),
        ]

        for heap_value, expected in test_cases:
            # Clear any existing environment variables
            for key in list(os.environ.keys()):
                if key.startswith("LANGUAGE_TOOL_SERVICE_"):
                    del os.environ[key]

            # Set heap size
            os.environ["LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEAP_SIZE"] = heap_value

            # Create settings and verify
            settings = Settings()
            assert settings.LANGUAGE_TOOL_HEAP_SIZE == expected

            # Verify manager can be created with this heap size
            manager = LanguageToolManager(settings)
            assert manager.settings.LANGUAGE_TOOL_HEAP_SIZE == expected

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    def test_configuration_boundary_values(self, clean_environment: None) -> None:
        """
        Test configuration with boundary and edge case values.

        Validates that the system handles extreme values appropriately
        and maintains stability with unusual but valid configurations.
        """
        # Test boundary values for numeric fields
        boundary_cases = {
            "LANGUAGE_TOOL_SERVICE_HTTP_PORT": "65535",  # Max valid port
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_PORT": "1024",  # Min non-privileged port
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_TIMEOUT_SECONDS": "3600",  # 1 hour
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_RETRIES": "100",  # High retry count
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS": "1000",  # High
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_HEAP_SIZE": "8g",  # Large heap
        }

        for key, value in boundary_cases.items():
            os.environ[key] = value

        settings = Settings()

        # Verify boundary values are accepted
        assert settings.HTTP_PORT == 65535
        assert settings.LANGUAGE_TOOL_PORT == 1024
        assert settings.LANGUAGE_TOOL_TIMEOUT_SECONDS == 3600
        assert settings.LANGUAGE_TOOL_MAX_RETRIES == 100
        assert settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS == 1000
        assert settings.LANGUAGE_TOOL_HEAP_SIZE == "8g"

        # Test minimum values
        min_cases = {
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_TIMEOUT_SECONDS": "1",
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_RETRIES": "0",
            "LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS": "1",
        }

        # Clear and set minimum values
        for key in list(os.environ.keys()):
            if key.startswith("LANGUAGE_TOOL_SERVICE_"):
                del os.environ[key]

        for key, value in min_cases.items():
            os.environ[key] = value

        min_settings = Settings()

        assert min_settings.LANGUAGE_TOOL_TIMEOUT_SECONDS == 1
        assert min_settings.LANGUAGE_TOOL_MAX_RETRIES == 0
        assert min_settings.LANGUAGE_TOOL_MAX_CONCURRENT_REQUESTS == 1

    @pytest.mark.integration
    @pytest.mark.timeout(30)
    def test_port_binding_configuration(self, clean_environment: None) -> None:
        """
        Test port binding validation and conflict detection.

        Validates that port configuration works correctly and that
        actual port binding can be verified through socket checks.
        """
        # Arrange: Find available ports for testing
        http_port = get_available_port(8090)
        language_tool_port = get_available_port(http_port + 1)

        # Ensure ports are different
        assert http_port != language_tool_port

        # Set environment variables
        os.environ["LANGUAGE_TOOL_SERVICE_HTTP_PORT"] = str(http_port)
        os.environ["LANGUAGE_TOOL_SERVICE_LANGUAGE_TOOL_PORT"] = str(language_tool_port)

        # Act: Create settings
        settings = Settings()

        # Assert: Verify port configuration
        assert settings.HTTP_PORT == http_port
        assert settings.LANGUAGE_TOOL_PORT == language_tool_port

        # Verify ports are actually available for binding
        assert is_port_available(http_port)
        assert is_port_available(language_tool_port)

        # Test port conflict detection
        # Use a port that's definitely in use (bind it ourselves)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("localhost", http_port))

            # Now the port should not be available
            assert not is_port_available(http_port)
