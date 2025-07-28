"""
Unit tests for ErrorDetail factory function.

Tests comprehensive coverage of create_error_detail_with_context function including
automatic context capture, correlation ID generation, stack trace handling, and
OpenTelemetry integration. Follows HuleEdu testing excellence patterns.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from opentelemetry.trace import Span, SpanContext


# Test fixtures
@pytest.fixture
def test_service() -> str:
    """Provide consistent service name for testing."""
    return "test_service"


@pytest.fixture
def test_operation() -> str:
    """Provide consistent operation name for testing."""
    return "test_operation"


@pytest.fixture
def test_message() -> str:
    """Provide consistent error message for testing."""
    return "Test error occurred"


@pytest.fixture
def test_correlation_id() -> UUID:
    """Provide consistent correlation ID for testing."""
    return uuid.uuid4()


@pytest.fixture
def test_details() -> dict[str, Any]:
    """Provide consistent error details for testing."""
    return {"key1": "value1", "key2": 42, "key3": True}


class TestBasicErrorDetailCreation:
    """Test basic ErrorDetail creation functionality."""

    def test_create_with_all_parameters(
        self,
        test_service: str,
        test_operation: str,
        test_message: str,
        test_correlation_id: UUID,
        test_details: dict[str, Any],
    ) -> None:
        """Test create_error_detail_with_context with all parameters provided."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            correlation_id=test_correlation_id,
            details=test_details,
            capture_stack=True,
        )

        # Verify all fields are set correctly
        assert error_detail.error_code == ErrorCode.VALIDATION_ERROR
        assert error_detail.message == test_message
        assert error_detail.service == test_service
        assert error_detail.operation == test_operation
        assert error_detail.correlation_id == test_correlation_id
        assert error_detail.details == test_details

        # Verify timestamp is set and recent
        assert isinstance(error_detail.timestamp, datetime)
        assert error_detail.timestamp.tzinfo == timezone.utc
        time_diff = datetime.now(timezone.utc) - error_detail.timestamp
        assert time_diff.total_seconds() < 1.0  # Should be very recent

        # Verify stack trace is captured
        assert error_detail.stack_trace is not None
        assert isinstance(error_detail.stack_trace, str)

    def test_create_with_minimal_parameters(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test create_error_detail_with_context with minimal required parameters."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.UNKNOWN_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        # Verify required fields
        assert error_detail.error_code == ErrorCode.UNKNOWN_ERROR
        assert error_detail.message == test_message
        assert error_detail.service == test_service
        assert error_detail.operation == test_operation

        # Verify auto-generated correlation_id
        assert error_detail.correlation_id is not None
        assert isinstance(error_detail.correlation_id, UUID)

        # Verify default empty details
        assert error_detail.details == {}

        # Verify timestamp is set
        assert isinstance(error_detail.timestamp, datetime)

    def test_create_with_different_error_codes(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test ErrorDetail creation with different error code types."""
        error_codes_to_test = [
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.RESOURCE_NOT_FOUND,
            ErrorCode.EXTERNAL_SERVICE_ERROR,
            ErrorCode.TIMEOUT,
            ErrorCode.CIRCUIT_BREAKER_OPEN,
        ]

        for error_code in error_codes_to_test:
            error_detail: ErrorDetail = create_error_detail_with_context(
                error_code=error_code,
                message=test_message,
                service=test_service,
                operation=test_operation,
            )

            assert error_detail.error_code == error_code
            assert error_detail.message == test_message
            assert error_detail.service == test_service
            assert error_detail.operation == test_operation

    def test_create_with_none_details(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test ErrorDetail creation with None details parameter."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            details=None,
        )

        # Should default to empty dict when None provided
        assert error_detail.details == {}


class TestCorrelationIdHandling:
    """Test correlation ID generation and handling."""

    def test_correlation_id_auto_generation(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test automatic correlation ID generation when not provided."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.UNKNOWN_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        # Should generate valid UUID
        assert error_detail.correlation_id is not None
        assert isinstance(error_detail.correlation_id, UUID)

        # Each call should generate different UUID
        error_detail2: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.UNKNOWN_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        assert error_detail.correlation_id != error_detail2.correlation_id

    def test_correlation_id_preservation(
        self,
        test_service: str,
        test_operation: str,
        test_message: str,
        test_correlation_id: UUID,
    ) -> None:
        """Test that provided correlation ID is preserved."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            correlation_id=test_correlation_id,
        )

        assert error_detail.correlation_id == test_correlation_id
        assert isinstance(error_detail.correlation_id, UUID)


class TestStackTraceCapture:
    """Test stack trace capture functionality."""

    def test_stack_trace_capture_enabled(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test stack trace capture when capture_stack=True."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            capture_stack=True,
        )

        # Should capture stack trace
        assert error_detail.stack_trace is not None
        assert isinstance(error_detail.stack_trace, str)
        assert len(error_detail.stack_trace) > 0

        # Should contain function name in stack trace
        assert "test_stack_trace_capture_enabled" in error_detail.stack_trace

    def test_stack_trace_capture_disabled(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test stack trace capture when capture_stack=False."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            capture_stack=False,
        )

        # Should not capture stack trace
        assert error_detail.stack_trace is None

    def test_stack_trace_capture_default(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test default stack trace capture behavior (should be enabled)."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            # capture_stack not specified, should default to True
        )

        # Should capture stack trace by default
        assert error_detail.stack_trace is not None
        assert isinstance(error_detail.stack_trace, str)

    def test_stack_trace_during_exception_handling(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test stack trace capture when called during exception handling."""
        try:
            # Create a test exception scenario
            raise ValueError("Test exception for stack trace")
        except ValueError:
            error_detail: ErrorDetail = create_error_detail_with_context(
                error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                message=test_message,
                service=test_service,
                operation=test_operation,
                capture_stack=True,
            )

            # Should capture the exception stack trace
            assert error_detail.stack_trace is not None
            assert "ValueError: Test exception for stack trace" in error_detail.stack_trace
            assert "test_stack_trace_during_exception_handling" in error_detail.stack_trace

    @patch("huleedu_service_libs.error_handling.error_detail_factory.traceback.format_exc")
    @patch("huleedu_service_libs.error_handling.error_detail_factory.traceback.format_stack")
    def test_stack_trace_fallback_to_current_stack(
        self,
        mock_format_stack: MagicMock,
        mock_format_exc: MagicMock,
        test_service: str,
        test_operation: str,
        test_message: str,
    ) -> None:
        """Test stack trace fallback when no exception is being handled."""
        # Mock format_exc to return the "no exception" marker
        mock_format_exc.return_value = "NoneType: None\n"
        mock_format_stack.return_value = ["frame1\n", "frame2\n", "current_frame\n"]

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            capture_stack=True,
        )

        # Should call format_stack when no exception is being handled
        mock_format_exc.assert_called_once()
        mock_format_stack.assert_called_once()

        # Should use current stack (excluding the current frame)
        expected_stack = "frame1\nframe2\n"  # Should exclude last frame
        assert error_detail.stack_trace == expected_stack


class TestOpenTelemetryIntegration:
    """Test OpenTelemetry trace and span ID extraction."""

    @patch("huleedu_service_libs.error_handling.error_detail_factory.trace.get_current_span")
    def test_opentelemetry_trace_extraction_with_active_span(
        self,
        mock_get_current_span: MagicMock,
        test_service: str,
        test_operation: str,
        test_message: str,
    ) -> None:
        """Test OpenTelemetry trace/span ID extraction with active recording span."""
        # Create mock span with valid context
        mock_span: MagicMock = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True

        # Create mock span context with valid trace and span IDs
        mock_span_context: MagicMock = MagicMock(spec=SpanContext)
        mock_span_context.is_valid = True
        mock_span_context.trace_id = 0xABCDEF123456789012345678ABCDEF12
        mock_span_context.span_id = 0x1234567890ABCDEF

        mock_span.get_span_context.return_value = mock_span_context
        mock_get_current_span.return_value = mock_span

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        # Verify OpenTelemetry integration was called
        mock_get_current_span.assert_called_once()
        mock_span.is_recording.assert_called_once()
        mock_span.get_span_context.assert_called_once()

        # Verify trace and span IDs are extracted correctly
        expected_trace_id = "abcdef123456789012345678abcdef12"
        expected_span_id = "1234567890abcdef"

        assert error_detail.trace_id == expected_trace_id
        assert error_detail.span_id == expected_span_id

    @patch("huleedu_service_libs.error_handling.error_detail_factory.trace.get_current_span")
    def test_opentelemetry_trace_extraction_with_inactive_span(
        self,
        mock_get_current_span: MagicMock,
        test_service: str,
        test_operation: str,
        test_message: str,
    ) -> None:
        """Test OpenTelemetry handling with inactive (non-recording) span."""
        # Create mock span that is not recording
        mock_span: MagicMock = MagicMock(spec=Span)
        mock_span.is_recording.return_value = False
        mock_get_current_span.return_value = mock_span

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.TIMEOUT,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        # Verify span was checked but context not extracted
        mock_get_current_span.assert_called_once()
        mock_span.is_recording.assert_called_once()
        mock_span.get_span_context.assert_not_called()

        # Should have None values for trace info
        assert error_detail.trace_id is None
        assert error_detail.span_id is None

    @patch("huleedu_service_libs.error_handling.error_detail_factory.trace.get_current_span")
    def test_opentelemetry_trace_extraction_with_no_span(
        self,
        mock_get_current_span: MagicMock,
        test_service: str,
        test_operation: str,
        test_message: str,
    ) -> None:
        """Test OpenTelemetry handling when no current span exists."""
        # Mock no current span
        mock_get_current_span.return_value = None

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.CONNECTION_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        # Should handle gracefully with no span
        mock_get_current_span.assert_called_once()

        # Should have None values for trace info
        assert error_detail.trace_id is None
        assert error_detail.span_id is None

    @patch("huleedu_service_libs.error_handling.error_detail_factory.trace.get_current_span")
    def test_opentelemetry_trace_extraction_with_invalid_context(
        self,
        mock_get_current_span: MagicMock,
        test_service: str,
        test_operation: str,
        test_message: str,
    ) -> None:
        """Test OpenTelemetry handling with invalid span context."""
        # Create mock span with invalid context
        mock_span: MagicMock = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True

        mock_span_context: MagicMock = MagicMock(spec=SpanContext)
        mock_span_context.is_valid = False  # Invalid context

        mock_span.get_span_context.return_value = mock_span_context
        mock_get_current_span.return_value = mock_span

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        # Should check context validity
        mock_get_current_span.assert_called_once()
        mock_span.is_recording.assert_called_once()
        mock_span.get_span_context.assert_called_once()

        # Should have None values for invalid context
        assert error_detail.trace_id is None
        assert error_detail.span_id is None


class TestErrorDetailFactoryEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_strings_handling(self) -> None:
        """Test ErrorDetail creation with empty string parameters."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="",  # Empty message
            service="",  # Empty service
            operation="",  # Empty operation
        )

        # Should handle empty strings gracefully
        assert error_detail.error_code == ErrorCode.VALIDATION_ERROR
        assert error_detail.message == ""
        assert error_detail.service == ""
        assert error_detail.operation == ""
        assert isinstance(error_detail.correlation_id, UUID)

    def test_complex_details_handling(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test ErrorDetail creation with complex nested details."""
        complex_details: dict[str, Any] = {
            "nested_dict": {"level1": {"level2": "deep_value"}},
            "list_data": [1, "string", {"mixed": True}],
            "none_value": None,
            "boolean_flags": {"flag1": True, "flag2": False},
            "numeric_data": {"int": 42, "float": 3.14159},
        }

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            details=complex_details,
        )

        # Should preserve complex details structure
        assert error_detail.details == complex_details
        assert error_detail.details["nested_dict"]["level1"]["level2"] == "deep_value"
        assert error_detail.details["list_data"][2]["mixed"] is True

    def test_large_details_handling(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test ErrorDetail creation with large details dictionary."""
        large_details: dict[str, Any] = {f"key_{i}": f"value_{i}" for i in range(1000)}

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
            details=large_details,
        )

        # Should handle large details without issues
        assert len(error_detail.details) == 1000
        assert error_detail.details["key_500"] == "value_500"
        assert error_detail.details["key_999"] == "value_999"

    def test_unicode_content_handling(self) -> None:
        """Test ErrorDetail creation with Unicode content."""
        unicode_message = "Error with unicode: 🚨 français español 中文 русский"
        unicode_service = "service_測試"
        unicode_operation = "operation_тест"
        unicode_details = {
            "unicode_key_测试": "unicode_value_🔧",
            "emoji_data": "✅ ❌ ⚠️ 📊",
        }

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=unicode_message,
            service=unicode_service,
            operation=unicode_operation,
            details=unicode_details,
        )

        # Should handle Unicode content correctly
        assert error_detail.message == unicode_message
        assert error_detail.service == unicode_service
        assert error_detail.operation == unicode_operation
        assert error_detail.details["unicode_key_测试"] == "unicode_value_🔧"

    def test_error_detail_immutability(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test that created ErrorDetail instances are immutable."""
        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.UNKNOWN_ERROR,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        # Verify ErrorDetail is frozen (immutable)
        with pytest.raises(ValueError, match="Instance is frozen"):
            error_detail.message = "Modified message"  # type: ignore[misc]

        with pytest.raises(ValueError, match="Instance is frozen"):
            error_detail.service = "Modified service"  # type: ignore[misc]

    def test_timestamp_consistency(
        self, test_service: str, test_operation: str, test_message: str
    ) -> None:
        """Test timestamp consistency and timezone handling."""
        before_creation = datetime.now(timezone.utc)

        error_detail: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.TIMEOUT,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        after_creation = datetime.now(timezone.utc)

        # Timestamp should be within creation window
        assert before_creation <= error_detail.timestamp <= after_creation
        assert error_detail.timestamp.tzinfo == timezone.utc

        # Multiple calls should have different timestamps
        import time

        time.sleep(0.001)  # Small delay to ensure different timestamp

        error_detail2: ErrorDetail = create_error_detail_with_context(
            error_code=ErrorCode.TIMEOUT,
            message=test_message,
            service=test_service,
            operation=test_operation,
        )

        assert error_detail.timestamp != error_detail2.timestamp
