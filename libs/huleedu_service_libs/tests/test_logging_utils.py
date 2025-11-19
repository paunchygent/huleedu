"""Tests for logging_utils module processors and configuration."""

import os
from typing import Any
from unittest.mock import Mock, patch

from huleedu_service_libs.logging_utils import add_service_context, add_trace_context


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


class TestAddTraceContext:
    """Tests for the add_trace_context processor."""

    def test_adds_trace_id_and_span_id_when_span_active(self) -> None:
        """Verify trace_id and span_id are added when active span exists."""
        # Arrange
        event_dict: dict[str, Any] = {"message": "test message"}

        # Create mock span context
        mock_span_context = Mock()
        mock_span_context.is_valid = True
        mock_span_context.trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        mock_span_context.span_id = 0x1234567890ABCDEF

        # Create mock span
        mock_span = Mock()
        mock_span.get_span_context.return_value = mock_span_context

        # Act
        with patch("huleedu_service_libs.logging_utils.get_current_span", return_value=mock_span):
            with patch("huleedu_service_libs.logging_utils.TRACING_AVAILABLE", True):
                result = add_trace_context(None, "", event_dict)

        # Assert
        assert "trace_id" in result
        assert "span_id" in result
        assert result["trace_id"] == "1234567890abcdef1234567890abcdef"
        assert result["span_id"] == "1234567890abcdef"

    def test_trace_id_formatted_as_32_char_hex(self) -> None:
        """Verify trace_id is formatted as 32-character hexadecimal string."""
        # Arrange
        event_dict: dict[str, Any] = {"message": "test"}

        mock_span_context = Mock()
        mock_span_context.is_valid = True
        mock_span_context.trace_id = 1  # Minimal trace ID
        mock_span_context.span_id = 1

        mock_span = Mock()
        mock_span.get_span_context.return_value = mock_span_context

        # Act
        with patch("huleedu_service_libs.logging_utils.get_current_span", return_value=mock_span):
            with patch("huleedu_service_libs.logging_utils.TRACING_AVAILABLE", True):
                result = add_trace_context(None, "", event_dict)

        # Assert
        assert result["trace_id"] == "00000000000000000000000000000001"
        assert len(result["trace_id"]) == 32

    def test_span_id_formatted_as_16_char_hex(self) -> None:
        """Verify span_id is formatted as 16-character hexadecimal string."""
        # Arrange
        event_dict: dict[str, Any] = {"message": "test"}

        mock_span_context = Mock()
        mock_span_context.is_valid = True
        mock_span_context.trace_id = 1
        mock_span_context.span_id = 1  # Minimal span ID

        mock_span = Mock()
        mock_span.get_span_context.return_value = mock_span_context

        # Act
        with patch("huleedu_service_libs.logging_utils.get_current_span", return_value=mock_span):
            with patch("huleedu_service_libs.logging_utils.TRACING_AVAILABLE", True):
                result = add_trace_context(None, "", event_dict)

        # Assert
        assert result["span_id"] == "0000000000000001"
        assert len(result["span_id"]) == 16

    def test_no_fields_when_no_active_span(self) -> None:
        """Verify no trace fields added when no active span exists."""
        # Arrange
        event_dict: dict[str, Any] = {"message": "test message"}

        # Act - get_current_span returns None
        with patch("huleedu_service_libs.logging_utils.get_current_span", return_value=None):
            with patch("huleedu_service_libs.logging_utils.TRACING_AVAILABLE", True):
                result = add_trace_context(None, "", event_dict)

        # Assert
        assert "trace_id" not in result
        assert "span_id" not in result
        assert result["message"] == "test message"

    def test_preserves_existing_fields(self) -> None:
        """Verify existing event_dict fields are preserved."""
        # Arrange
        event_dict: dict[str, Any] = {
            "message": "test message",
            "correlation_id": "abc-123",
            "level": "info",
        }

        mock_span_context = Mock()
        mock_span_context.is_valid = True
        mock_span_context.trace_id = 0x1234567890ABCDEF1234567890ABCDEF
        mock_span_context.span_id = 0x1234567890ABCDEF

        mock_span = Mock()
        mock_span.get_span_context.return_value = mock_span_context

        # Act
        with patch("huleedu_service_libs.logging_utils.get_current_span", return_value=mock_span):
            with patch("huleedu_service_libs.logging_utils.TRACING_AVAILABLE", True):
                result = add_trace_context(None, "", event_dict)

        # Assert
        assert result["message"] == "test message"
        assert result["correlation_id"] == "abc-123"
        assert result["level"] == "info"
        assert "trace_id" in result
        assert "span_id" in result

    def test_handles_tracing_not_available(self) -> None:
        """Verify early exit when TRACING_AVAILABLE is False."""
        # Arrange
        event_dict: dict[str, Any] = {"message": "test"}

        # Act - TRACING_AVAILABLE=False (simulates no tracing module)
        with patch("huleedu_service_libs.logging_utils.TRACING_AVAILABLE", False):
            result = add_trace_context(None, "", event_dict)

        # Assert - No trace fields, no errors
        assert "trace_id" not in result
        assert "span_id" not in result
        assert result == event_dict  # Unchanged
