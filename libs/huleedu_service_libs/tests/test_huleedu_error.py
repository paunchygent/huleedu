"""
Unit tests for HuleEduError core exception class.

Tests error creation, property access, OpenTelemetry integration, utility methods,
and exception inheritance. Validates structured error handling patterns and
observability integration. Follows HuleEdu testing excellence patterns.
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
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from opentelemetry.trace import Span, Status, StatusCode


# Test fixtures
@pytest.fixture
def test_correlation_id() -> UUID:
    """Provide consistent correlation ID for testing."""
    return uuid.uuid4()


@pytest.fixture
def test_timestamp() -> datetime:
    """Provide consistent timestamp for testing."""
    return datetime.now(timezone.utc)


@pytest.fixture
def basic_error_detail(test_correlation_id: UUID, test_timestamp: datetime) -> ErrorDetail:
    """Provide basic ErrorDetail for testing."""
    return ErrorDetail(
        error_code=ErrorCode.UNKNOWN_ERROR,
        message="Test error message",
        correlation_id=test_correlation_id,
        timestamp=test_timestamp,
        service="test_service",
        operation="test_operation",
        details={"key": "value", "number": 42},
        stack_trace="Test stack trace",
        trace_id="abc123def456",
        span_id="789xyz012",
    )


@pytest.fixture
def minimal_error_detail(test_correlation_id: UUID, test_timestamp: datetime) -> ErrorDetail:
    """Provide minimal ErrorDetail with optional fields as None."""
    return ErrorDetail(
        error_code=ErrorCode.VALIDATION_ERROR,
        message="Validation failed",
        correlation_id=test_correlation_id,
        timestamp=test_timestamp,
        service="validation_service",
        operation="validate_input",
        details={},
        stack_trace=None,
        trace_id=None,
        span_id=None,
    )


class TestHuleEduErrorConstruction:
    """Test HuleEduError construction and basic properties."""

    def test_basic_construction(self, basic_error_detail: ErrorDetail) -> None:
        """Test HuleEduError construction with ErrorDetail."""
        error: HuleEduError = HuleEduError(basic_error_detail)

        # Verify basic exception properties
        assert isinstance(error, Exception)
        assert isinstance(error, HuleEduError)
        expected_str = f"[{basic_error_detail.error_code.value}] {basic_error_detail.message}"
        assert str(error) == expected_str
        assert error.error_detail == basic_error_detail

    def test_property_accessors(self, basic_error_detail: ErrorDetail) -> None:
        """Test property accessor methods."""
        error: HuleEduError = HuleEduError(basic_error_detail)

        # Test correlation_id property (string conversion)
        assert error.correlation_id == str(basic_error_detail.correlation_id)
        assert isinstance(error.correlation_id, str)

        # Test error_code property (enum value extraction)
        assert error.error_code == ErrorCode.UNKNOWN_ERROR.value
        assert isinstance(error.error_code, str)

        # Test service property
        assert error.service == basic_error_detail.service
        assert isinstance(error.service, str)

        # Test operation property
        assert error.operation == basic_error_detail.operation
        assert isinstance(error.operation, str)

    def test_minimal_error_detail_construction(self, minimal_error_detail: ErrorDetail) -> None:
        """Test construction with minimal ErrorDetail (None values)."""
        error: HuleEduError = HuleEduError(minimal_error_detail)

        assert error.error_code == ErrorCode.VALIDATION_ERROR.value
        assert error.service == "validation_service"
        assert error.operation == "validate_input"
        assert error.correlation_id == str(minimal_error_detail.correlation_id)

    def test_exception_inheritance(self, basic_error_detail: ErrorDetail) -> None:
        """Test proper exception inheritance and behavior."""
        error: HuleEduError = HuleEduError(basic_error_detail)

        # Should be catchable as Exception
        with pytest.raises(Exception):
            raise error

        # Should be catchable as HuleEduError specifically
        with pytest.raises(HuleEduError):
            raise error

        # Should preserve message in exception chain
        try:
            raise error
        except HuleEduError as caught_error:
            expected_str = f"[{basic_error_detail.error_code.value}] {basic_error_detail.message}"
            assert str(caught_error) == expected_str


class TestHuleEduErrorOpenTelemetryIntegration:
    """Test OpenTelemetry integration and span recording."""

    @patch("huleedu_service_libs.error_handling.huleedu_error.trace.get_current_span")
    def test_record_to_span_with_active_span(
        self, mock_get_current_span: MagicMock, basic_error_detail: ErrorDetail
    ) -> None:
        """Test _record_to_span with active OpenTelemetry span."""
        # Create mock span that is recording
        mock_span: MagicMock = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True
        mock_get_current_span.return_value = mock_span

        # Create error (triggers _record_to_span in constructor)
        error: HuleEduError = HuleEduError(basic_error_detail)

        # Verify span interactions
        mock_get_current_span.assert_called_once()
        mock_span.is_recording.assert_called_once()
        mock_span.record_exception.assert_called_once_with(error)

        # Verify status is set to ERROR
        mock_span.set_status.assert_called_once()
        status_call = mock_span.set_status.call_args[0][0]
        assert isinstance(status_call, Status)
        assert status_call.status_code == StatusCode.ERROR
        assert status_call.description == basic_error_detail.message

        # Verify error attributes are set
        expected_attributes = [
            ("error", True),
            ("error.code", ErrorCode.UNKNOWN_ERROR.value),
            ("error.message", basic_error_detail.message),
            ("error.service", basic_error_detail.service),
            ("error.operation", basic_error_detail.operation),
            ("correlation_id", str(basic_error_detail.correlation_id)),
        ]

        # Check that set_attribute was called for each expected attribute
        attribute_calls = mock_span.set_attribute.call_args_list
        assert len(attribute_calls) >= len(expected_attributes)

        # Verify specific attribute calls
        for expected_key, expected_value in expected_attributes:
            assert any(
                call[0][0] == expected_key and call[0][1] == expected_value
                for call in attribute_calls
            ), f"Expected attribute {expected_key}={expected_value} not found"

    @patch("huleedu_service_libs.error_handling.huleedu_error.trace.get_current_span")
    def test_record_to_span_with_details_attributes(self, mock_get_current_span: MagicMock) -> None:
        """Test that error details are properly added as span attributes."""
        mock_span: MagicMock = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True
        mock_get_current_span.return_value = mock_span

        # Create error with complex details
        error_detail_with_details = ErrorDetail(
            error_code=ErrorCode.PROCESSING_ERROR,
            message="Processing failed",
            correlation_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            service="processing_service",
            operation="process_data",
            details={
                "string_value": "test",
                "int_value": 42,
                "float_value": 3.14,
                "bool_value": True,
                "complex_value": {"nested": "data"},  # Should be stringified
            },
        )

        HuleEduError(error_detail_with_details)

        # Check details attributes
        attribute_calls = mock_span.set_attribute.call_args_list
        detail_calls = [call for call in attribute_calls if call[0][0].startswith("error.details.")]

        # Verify expected detail attributes
        expected_details = [
            ("error.details.string_value", "test"),
            ("error.details.int_value", 42),
            ("error.details.float_value", 3.14),
            ("error.details.bool_value", True),
            ("error.details.complex_value", str({"nested": "data"})),
        ]

        for expected_key, expected_value in expected_details:
            assert any(
                call[0][0] == expected_key and call[0][1] == expected_value for call in detail_calls
            ), f"Expected detail attribute {expected_key}={expected_value} not found"

    @patch("huleedu_service_libs.error_handling.huleedu_error.trace.get_current_span")
    def test_record_to_span_with_inactive_span(
        self, mock_get_current_span: MagicMock, basic_error_detail: ErrorDetail
    ) -> None:
        """Test _record_to_span with inactive span (not recording)."""
        mock_span: MagicMock = MagicMock(spec=Span)
        mock_span.is_recording.return_value = False
        mock_get_current_span.return_value = mock_span

        # Create error
        HuleEduError(basic_error_detail)

        # Verify span is checked but no recording happens
        mock_get_current_span.assert_called_once()
        mock_span.is_recording.assert_called_once()
        mock_span.record_exception.assert_not_called()
        mock_span.set_status.assert_not_called()
        mock_span.set_attribute.assert_not_called()

    @patch("huleedu_service_libs.error_handling.huleedu_error.trace.get_current_span")
    def test_record_to_span_with_no_span(
        self, mock_get_current_span: MagicMock, basic_error_detail: ErrorDetail
    ) -> None:
        """Test _record_to_span with no current span (None)."""
        mock_get_current_span.return_value = None

        # Create error (should not crash)
        error: HuleEduError = HuleEduError(basic_error_detail)

        # Verify span is checked but no operations occur
        mock_get_current_span.assert_called_once()
        assert isinstance(error, HuleEduError)


class TestHuleEduErrorUtilityMethods:
    """Test utility methods for serialization and manipulation."""

    def test_to_dict_serialization(self, basic_error_detail: ErrorDetail) -> None:
        """Test to_dict method for error serialization."""
        error: HuleEduError = HuleEduError(basic_error_detail)
        error_dict: dict[str, Any] = error.to_dict()

        # Verify structure
        assert "error" in error_dict
        assert "error_detail" in error_dict

        # Verify error string representation
        assert error_dict["error"] == str(error)
        expected_str = f"[{basic_error_detail.error_code.value}] {basic_error_detail.message}"
        assert error_dict["error"] == expected_str

        # Verify error_detail is properly serialized
        error_detail_dict = error_dict["error_detail"]
        assert isinstance(error_detail_dict, dict)
        assert error_detail_dict["error_code"] == ErrorCode.UNKNOWN_ERROR.value
        assert error_detail_dict["message"] == basic_error_detail.message
        assert error_detail_dict["service"] == basic_error_detail.service
        assert error_detail_dict["operation"] == basic_error_detail.operation

    def test_add_detail_creates_new_instance(self, basic_error_detail: ErrorDetail) -> None:
        """Test add_detail creates new immutable HuleEduError instance."""
        original_error: HuleEduError = HuleEduError(basic_error_detail)

        # Add new detail
        new_error: HuleEduError = original_error.add_detail("additional_key", "additional_value")

        # Verify new instance was created
        assert new_error is not original_error
        assert isinstance(new_error, HuleEduError)

        # Verify original error is unchanged
        assert "additional_key" not in original_error.error_detail.details

        # Verify new error has additional detail
        assert "additional_key" in new_error.error_detail.details
        assert new_error.error_detail.details["additional_key"] == "additional_value"

        # Verify all original details are preserved
        for key, value in basic_error_detail.details.items():
            assert new_error.error_detail.details[key] == value

        # Verify other properties are identical
        assert new_error.error_code == original_error.error_code
        assert new_error.service == original_error.service
        assert new_error.operation == original_error.operation
        assert new_error.correlation_id == original_error.correlation_id

    def test_add_detail_preserves_all_fields(self, basic_error_detail: ErrorDetail) -> None:
        """Test add_detail preserves all ErrorDetail fields correctly."""
        original_error: HuleEduError = HuleEduError(basic_error_detail)
        new_error: HuleEduError = original_error.add_detail("test_key", "test_value")

        # Verify all fields are preserved
        original_detail = original_error.error_detail
        new_detail = new_error.error_detail

        assert new_detail.error_code == original_detail.error_code
        assert new_detail.message == original_detail.message
        assert new_detail.correlation_id == original_detail.correlation_id
        assert new_detail.timestamp == original_detail.timestamp
        assert new_detail.service == original_detail.service
        assert new_detail.operation == original_detail.operation
        assert new_detail.stack_trace == original_detail.stack_trace
        assert new_detail.trace_id == original_detail.trace_id
        assert new_detail.span_id == original_detail.span_id

    def test_add_detail_overwrites_existing_key(self, basic_error_detail: ErrorDetail) -> None:
        """Test add_detail overwrites existing detail key."""
        original_error: HuleEduError = HuleEduError(basic_error_detail)

        # Original details contain "key": "value"
        assert original_error.error_detail.details["key"] == "value"

        # Add detail with same key but different value
        new_error: HuleEduError = original_error.add_detail("key", "new_value")

        # Verify key was overwritten
        assert new_error.error_detail.details["key"] == "new_value"
        # Verify original is unchanged
        assert original_error.error_detail.details["key"] == "value"

    def test_string_representations(self, basic_error_detail: ErrorDetail) -> None:
        """Test __str__ and __repr__ methods."""
        error: HuleEduError = HuleEduError(basic_error_detail)

        # Test __str__ representation
        str_repr: str = str(error)
        expected_str = f"[{ErrorCode.UNKNOWN_ERROR.value}] {basic_error_detail.message}"
        assert str_repr == expected_str

        # Test __repr__ representation
        repr_str: str = repr(error)
        assert "HuleEduError(" in repr_str
        assert f"code={ErrorCode.UNKNOWN_ERROR.value}" in repr_str
        assert f"message={basic_error_detail.message!r}" in repr_str
        assert f"service={basic_error_detail.service}" in repr_str
        assert f"operation={basic_error_detail.operation}" in repr_str
        assert f"correlation_id={str(basic_error_detail.correlation_id)}" in repr_str


class TestHuleEduErrorEdgeCasesAndIntegration:
    """Test edge cases and integration scenarios."""

    def test_different_error_codes(self) -> None:
        """Test HuleEduError with different error code types."""
        correlation_id: UUID = uuid.uuid4()
        timestamp: datetime = datetime.now(timezone.utc)

        error_codes_to_test = [
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.RESOURCE_NOT_FOUND,
            ErrorCode.TIMEOUT,
            ErrorCode.CIRCUIT_BREAKER_OPEN,
        ]

        for error_code in error_codes_to_test:
            error_detail = ErrorDetail(
                error_code=error_code,
                message=f"Test {error_code.value}",
                correlation_id=correlation_id,
                timestamp=timestamp,
                service="test_service",
                operation="test_operation",
            )

            error: HuleEduError = HuleEduError(error_detail)
            assert error.error_code == error_code.value
            assert error_code.value in str(error)

    def test_empty_details_handling(self) -> None:
        """Test HuleEduError with empty details dictionary."""
        error_detail = ErrorDetail(
            error_code=ErrorCode.PROCESSING_ERROR,
            message="Empty details test",
            correlation_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            service="test_service",
            operation="test_operation",
            details={},  # Empty details
        )

        error: HuleEduError = HuleEduError(error_detail)
        assert error.error_detail.details == {}

        # Test add_detail with empty original details
        new_error: HuleEduError = error.add_detail("first_key", "first_value")
        assert new_error.error_detail.details == {"first_key": "first_value"}

    def test_large_details_handling(self) -> None:
        """Test HuleEduError with large details dictionary."""
        large_details: dict[str, Any] = {f"key_{i}": f"value_{i}" for i in range(100)}

        error_detail = ErrorDetail(
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            message="Large details test",
            correlation_id=uuid.uuid4(),
            timestamp=datetime.now(timezone.utc),
            service="test_service",
            operation="test_operation",
            details=large_details,
        )

        error: HuleEduError = HuleEduError(error_detail)
        assert len(error.error_detail.details) == 100
        assert error.error_detail.details["key_50"] == "value_50"

        # Test serialization with large details
        error_dict: dict[str, Any] = error.to_dict()
        assert "error_detail" in error_dict
        serialized_details = error_dict["error_detail"]["details"]
        assert len(serialized_details) == 100

    @patch("huleedu_service_libs.error_handling.huleedu_error.trace.get_current_span")
    def test_opentelemetry_integration_with_none_values(
        self, mock_get_current_span: MagicMock, minimal_error_detail: ErrorDetail
    ) -> None:
        """Test OpenTelemetry integration with ErrorDetail containing None values."""
        mock_span: MagicMock = MagicMock(spec=Span)
        mock_span.is_recording.return_value = True
        mock_get_current_span.return_value = mock_span

        # ErrorDetail with trace_id and span_id as None
        HuleEduError(minimal_error_detail)

        # Should still record properly without crash
        mock_span.record_exception.assert_called_once()
        mock_span.set_status.assert_called_once()

    def test_exception_chaining_compatibility(self, basic_error_detail: ErrorDetail) -> None:
        """Test HuleEduError works properly with exception chaining."""
        original_exception = ValueError("Original error")

        try:
            raise original_exception
        except ValueError as e:
            # Chain with HuleEduError
            huleedu_error: HuleEduError = HuleEduError(basic_error_detail)

            try:
                raise huleedu_error from e
            except HuleEduError as chained_error:
                assert chained_error is huleedu_error
                assert chained_error.__cause__ is original_exception
                assert isinstance(chained_error.__cause__, ValueError)

    def test_correlation_id_type_consistency(self) -> None:
        """Test correlation_id property type consistency across operations."""
        correlation_id: UUID = uuid.uuid4()
        error_detail = ErrorDetail(
            error_code=ErrorCode.UNKNOWN_ERROR,
            message="Type consistency test",
            correlation_id=correlation_id,
            timestamp=datetime.now(timezone.utc),
            service="test_service",
            operation="test_operation",
        )

        error: HuleEduError = HuleEduError(error_detail)

        # Verify correlation_id property is always str
        assert isinstance(error.correlation_id, str)
        assert error.correlation_id == str(correlation_id)

        # Verify original ErrorDetail correlation_id is UUID
        assert isinstance(error.error_detail.correlation_id, UUID)
        assert error.error_detail.correlation_id == correlation_id

        # Verify consistency after add_detail
        new_error: HuleEduError = error.add_detail("test", "value")
        assert isinstance(new_error.correlation_id, str)
        assert new_error.correlation_id == str(correlation_id)
        assert isinstance(new_error.error_detail.correlation_id, UUID)
        assert new_error.error_detail.correlation_id == correlation_id
