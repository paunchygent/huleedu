"""Tests for logging_utils module processors and configuration."""

import os
from typing import Any

from huleedu_service_libs.logging_utils import add_service_context


class TestAddServiceContext:
    """Tests for the add_service_context processor."""

    def test_adds_service_name_from_env(self) -> None:
        """Verify service.name is added from SERVICE_NAME environment variable."""
        # Arrange
        os.environ["SERVICE_NAME"] = "test_service"
        os.environ["ENVIRONMENT"] = "test"
        event_dict: dict[str, Any] = {"message": "test message"}

        # Act
        result = add_service_context(None, "", event_dict)

        # Assert
        assert "service.name" in result
        assert result["service.name"] == "test_service"

    def test_adds_deployment_environment_from_env(self) -> None:
        """Verify deployment.environment is added from ENVIRONMENT variable."""
        # Arrange
        os.environ["SERVICE_NAME"] = "test_service"
        os.environ["ENVIRONMENT"] = "production"
        event_dict: dict[str, Any] = {"message": "test message"}

        # Act
        result = add_service_context(None, "", event_dict)

        # Assert
        assert "deployment.environment" in result
        assert result["deployment.environment"] == "production"

    def test_preserves_existing_fields(self) -> None:
        """Verify existing event_dict fields are preserved."""
        # Arrange
        os.environ["SERVICE_NAME"] = "test_service"
        os.environ["ENVIRONMENT"] = "development"
        event_dict: dict[str, Any] = {
            "message": "test message",
            "correlation_id": "abc-123",
            "level": "info",
        }

        # Act
        result = add_service_context(None, "", event_dict)

        # Assert
        assert result["message"] == "test message"
        assert result["correlation_id"] == "abc-123"
        assert result["level"] == "info"
        assert "service.name" in result
        assert "deployment.environment" in result

    def test_handles_missing_service_name_env(self) -> None:
        """Verify defaults to 'unknown' when SERVICE_NAME not set."""
        # Arrange
        os.environ.pop("SERVICE_NAME", None)  # Ensure not set
        os.environ["ENVIRONMENT"] = "development"
        event_dict: dict[str, Any] = {"message": "test message"}

        # Act
        result = add_service_context(None, "", event_dict)

        # Assert
        assert result["service.name"] == "unknown"

    def test_handles_missing_environment_env(self) -> None:
        """Verify defaults to 'development' when ENVIRONMENT not set."""
        # Arrange
        os.environ["SERVICE_NAME"] = "test_service"
        os.environ.pop("ENVIRONMENT", None)  # Ensure not set
        event_dict: dict[str, Any] = {"message": "test message"}

        # Act
        result = add_service_context(None, "", event_dict)

        # Assert
        assert result["deployment.environment"] == "development"

    def test_processor_signature_compatible(self) -> None:
        """Verify processor has correct structlog processor signature."""
        # Arrange
        event_dict: dict[str, Any] = {"message": "test"}

        # Act - Should accept (logger, method_name, event_dict) and return event_dict
        result = add_service_context(None, "info", event_dict)

        # Assert
        assert isinstance(result, dict)
        assert "service.name" in result
        assert "deployment.environment" in result
