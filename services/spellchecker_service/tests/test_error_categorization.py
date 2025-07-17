"""Error categorization business logic tests for spellchecker service.

Tests the real _categorize_processing_error business logic to ensure proper
error classification and correlation ID handling. This focuses purely on
the business logic without external dependencies.

ULTRATHINK Requirements:
- Test actual _categorize_processing_error logic, not mock behavior
- Verify correlation ID preservation through real business logic
- Test error detection patterns match actual implementation
- Focused testing approach (NOT test-all)
"""

from __future__ import annotations

import json
from typing import Generator
from unittest.mock import MagicMock
from uuid import uuid4

import aiohttp
import pytest
from common_core.error_enums import ErrorCode
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from pydantic import ValidationError

from services.spellchecker_service.event_processor import _categorize_processing_error


class TestErrorCategorizationBusinessLogic:
    """Test the real _categorize_processing_error business logic works correctly."""

    def test_categorize_preserves_correlation_id(self) -> None:
        """Test that error categorization preserves correlation ID."""
        correlation_id = uuid4()
        exc = Exception("Test error")

        error_detail = _categorize_processing_error(exc, correlation_id)

        assert error_detail.correlation_id == correlation_id
        assert error_detail.service == "spellchecker_service"
        assert error_detail.operation == "categorize_processing_error"

    def test_categorize_preserves_original_error_context(self) -> None:
        """Test that error categorization preserves original error information."""
        correlation_id = uuid4()
        original_message = "Database connection failed"
        exc = RuntimeError(original_message)

        error_detail = _categorize_processing_error(exc, correlation_id)

        assert error_detail.details["original_exception_type"] == "RuntimeError"
        assert error_detail.details["original_message"] == original_message
        assert original_message in error_detail.message

    def test_categorize_huleedu_error_passthrough(self) -> None:
        """Test that HuleEduError instances are passed through unchanged."""
        correlation_id = uuid4()
        original_error_detail = MagicMock()
        original_error_detail.error_code = ErrorCode.CONTENT_SERVICE_ERROR
        original_error_detail.correlation_id = correlation_id

        huleedu_error = HuleEduError(original_error_detail)

        result = _categorize_processing_error(huleedu_error, uuid4())

        # Should return the original error detail unchanged
        assert result == original_error_detail

    def test_categorize_timeout_detection(self) -> None:
        """Test actual timeout error detection logic."""
        correlation_id = uuid4()

        # Test exceptions that actually contain "timeout" (not "timed out")
        timeout_exceptions = [
            Exception("Request timeout occurred"),
            aiohttp.ServerTimeoutError("Server timeout"),
            Exception("Connection timeout"),
        ]

        for exc in timeout_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.TIMEOUT

        # Test that "timed out" does NOT match (falls back to PROCESSING_ERROR)
        timed_out_exception = Exception("Operation timed out")
        error_detail = _categorize_processing_error(timed_out_exception, correlation_id)
        assert error_detail.error_code == ErrorCode.PROCESSING_ERROR

    def test_categorize_connection_detection(self) -> None:
        """Test actual connection error detection logic."""
        correlation_id = uuid4()

        connection_exceptions = [
            Exception("Connection refused"),
            aiohttp.ClientConnectionError("Failed to connect"),
            Exception("Lost connection to server"),
        ]

        for exc in connection_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.CONNECTION_ERROR

    def test_categorize_validation_detection(self) -> None:
        """Test actual validation error detection logic."""
        correlation_id = uuid4()

        validation_exceptions = [
            ValidationError.from_exception_data("TestModel", []),
            Exception("Validation failed for field"),
        ]

        for exc in validation_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.VALIDATION_ERROR

    def test_categorize_parsing_detection(self) -> None:
        """Test actual parsing error detection logic."""
        correlation_id = uuid4()

        parsing_exceptions = [
            Exception("Failed to parse JSON"),
            json.JSONDecodeError("Invalid JSON", "", 0),
        ]

        for exc in parsing_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.PARSING_ERROR

    def test_categorize_defaults_to_processing_error(self) -> None:
        """Test that unknown exceptions default to PROCESSING_ERROR."""
        correlation_id = uuid4()

        unknown_exceptions = [
            RuntimeError("Unknown runtime error"),
            ValueError("Invalid value provided"),
            KeyError("Missing key"),
        ]

        for exc in unknown_exceptions:
            error_detail = _categorize_processing_error(exc, correlation_id)
            assert error_detail.error_code == ErrorCode.PROCESSING_ERROR

    def test_categorize_error_message_structure(self) -> None:
        """Test that categorized errors have proper message structure."""
        correlation_id = uuid4()
        original_message = "Test connection failure"
        exc = Exception(original_message)

        error_detail = _categorize_processing_error(exc, correlation_id)

        # Message should include categorization context
        assert "Categorized error:" in error_detail.message
        assert original_message in error_detail.message

        # Details should contain structured information
        assert "original_exception_type" in error_detail.details
        assert "original_message" in error_detail.details
        assert error_detail.details["original_message"] == original_message

    def test_categorize_error_types_exhaustive(self) -> None:
        """Test error categorization covers all expected error types."""
        correlation_id = uuid4()

        # Test each major error category
        test_cases = [
            (Exception("timeout occurred"), ErrorCode.TIMEOUT),
            (Exception("connection failed"), ErrorCode.CONNECTION_ERROR),
            (Exception("validation error"), ErrorCode.VALIDATION_ERROR),
            (Exception("parse failure"), ErrorCode.PARSING_ERROR),
            (Exception("unknown error"), ErrorCode.PROCESSING_ERROR),
        ]

        for exception, expected_code in test_cases:
            error_detail = _categorize_processing_error(exception, correlation_id)
            assert error_detail.error_code == expected_code
            assert error_detail.correlation_id == correlation_id


# Prometheus registry cleanup for test isolation
@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear Prometheus registry between tests to avoid metric conflicts."""
    from prometheus_client import REGISTRY

    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        try:
            REGISTRY.unregister(collector)
        except KeyError:
            pass  # Already unregistered
    yield
