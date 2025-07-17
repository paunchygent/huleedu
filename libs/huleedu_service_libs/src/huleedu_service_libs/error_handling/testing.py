"""
Testing utilities for HuleEdu error handling.

This module provides utilities for testing code that uses the
exception-based error handling pattern.
"""

from contextlib import contextmanager
from typing import Any, Generator, Optional, Union

from common_core.error_enums import (
    ClassManagementErrorCode,
    ErrorCode,
    FileValidationErrorCode,
)
from common_core.models.error_models import ErrorDetail

from .huleedu_error import HuleEduError

# Type alias for all error code types
ErrorCodeType = Union[ErrorCode, ClassManagementErrorCode, FileValidationErrorCode]


class ErrorCapture:
    """Helper class to capture error in context manager."""

    def __init__(self) -> None:
        self.error: Optional[HuleEduError] = None


@contextmanager
def assert_raises_huleedu_error(
    error_code: ErrorCodeType,
    service: Optional[str] = None,
    operation: Optional[str] = None,
    message_contains: Optional[str] = None,
    details_contain: Optional[dict[str, Any]] = None,
) -> Generator[ErrorCapture, None, None]:
    """
    Context manager for asserting that HuleEduError is raised with specific attributes.

    Usage:
        with assert_raises_huleedu_error(
            error_code=ErrorCode.VALIDATION_ERROR,
            service="test_service",
            operation="test_operation",
            message_contains="invalid",
            details_contain={"field": "email"}
        ) as capture:
            # Code that should raise HuleEduError
            raise_validation_error(...)

        # Can access the caught error after the block
        assert capture.error.correlation_id is not None

    Args:
        error_code: The expected error code
        service: Expected service name (if provided)
        operation: Expected operation name (if provided)
        message_contains: Substring that should be in the error message
        details_contain: Key-value pairs that should be in error details

    Yields:
        An ErrorCapture object that will contain the caught error

    Raises:
        AssertionError: If the expected error is not raised or doesn't match criteria
    """
    capture = ErrorCapture()

    try:
        yield capture
        # If we get here, no exception was raised
        raise AssertionError(
            f"Expected HuleEduError with code {error_code.value} but no error was raised"
        )
    except HuleEduError as e:
        error_caught = e

        # Validate error code
        if e.error_detail.error_code != error_code:
            raise AssertionError(
                f"Expected error code {error_code.value} but got {e.error_detail.error_code.value}"
            )

        # Validate service if specified
        if service is not None and e.error_detail.service != service:
            raise AssertionError(f"Expected service '{service}' but got '{e.error_detail.service}'")

        # Validate operation if specified
        if operation is not None and e.error_detail.operation != operation:
            raise AssertionError(
                f"Expected operation '{operation}' but got '{e.error_detail.operation}'"
            )

        # Validate message contains substring if specified
        if message_contains is not None and message_contains not in e.error_detail.message:
            raise AssertionError(
                f"Expected message to contain '{message_contains}' "
                f"but got '{e.error_detail.message}'"
            )

        # Validate details contain expected keys/values
        if details_contain is not None:
            for key, expected_value in details_contain.items():
                if key not in e.error_detail.details:
                    raise AssertionError(
                        f"Expected detail key '{key}' not found in error details: "
                        f"{e.error_detail.details}"
                    )
                actual_value = e.error_detail.details[key]
                if actual_value != expected_value:
                    raise AssertionError(
                        f"Expected detail '{key}' to be {expected_value!r} but got {actual_value!r}"
                    )

        # Store the error for access after the context
        capture.error = error_caught
    except Exception as e:
        # Any other exception type is unexpected
        raise AssertionError(f"Expected HuleEduError but got {type(e).__name__}: {str(e)}")


class ErrorDetailMatcher:
    """
    A matcher for comparing ErrorDetail instances in tests.

    Useful for partial matching when you don't want to compare all fields.
    """

    def __init__(
        self,
        error_code: Optional[ErrorCodeType] = None,
        message: Optional[str] = None,
        service: Optional[str] = None,
        operation: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ):
        """
        Initialize the matcher with expected values.

        Only provided fields will be checked during matching.
        """
        self.error_code = error_code
        self.message = message
        self.service = service
        self.operation = operation
        self.details = details
        self.correlation_id = correlation_id

    def matches(self, error_detail: Any) -> bool:
        """
        Check if an ErrorDetail matches the expected values.

        Args:
            error_detail: The ErrorDetail instance to check

        Returns:
            True if all specified fields match
        """
        if not hasattr(error_detail, "error_code"):
            return False

        if self.error_code is not None and error_detail.error_code != self.error_code:
            return False

        if self.message is not None and error_detail.message != self.message:
            return False

        if self.service is not None and error_detail.service != self.service:
            return False

        if self.operation is not None and error_detail.operation != self.operation:
            return False

        if (
            self.correlation_id is not None
            and str(error_detail.correlation_id) != self.correlation_id
        ):
            return False

        if self.details is not None:
            for key, value in self.details.items():
                if key not in error_detail.details or error_detail.details[key] != value:
                    return False

        return True

    def __repr__(self) -> str:
        """String representation for test output."""
        parts = []
        if self.error_code:
            parts.append(f"error_code={self.error_code.value}")
        if self.message:
            parts.append(f"message={self.message!r}")
        if self.service:
            parts.append(f"service={self.service!r}")
        if self.operation:
            parts.append(f"operation={self.operation!r}")
        if self.details:
            parts.append(f"details={self.details!r}")
        if self.correlation_id:
            parts.append(f"correlation_id={self.correlation_id!r}")

        return f"ErrorDetailMatcher({', '.join(parts)})"


def create_test_error_detail(
    error_code: ErrorCodeType = ErrorCode.UNKNOWN_ERROR,
    message: str = "Test error",
    service: str = "test_service",
    operation: str = "test_operation",
    **kwargs: Any,
) -> ErrorDetail:
    """
    Create an ErrorDetail instance for testing.

    This is a convenience function that provides sensible defaults
    for all required fields.

    Args:
        error_code: Error code (defaults to UNKNOWN_ERROR)
        message: Error message (defaults to "Test error")
        service: Service name (defaults to "test_service")
        operation: Operation name (defaults to "test_operation")
        **kwargs: Additional fields to pass to ErrorDetail.create_with_context

    Returns:
        ErrorDetail instance for testing
    """
    from .error_detail_factory import create_error_detail_with_context

    return create_error_detail_with_context(
        error_code=error_code,
        message=message,
        service=service,
        operation=operation,
        capture_stack=False,  # Don't capture stack in tests
        **kwargs,
    )


def create_test_huleedu_error(
    error_code: ErrorCodeType = ErrorCode.UNKNOWN_ERROR,
    message: str = "Test error",
    service: str = "test_service",
    operation: str = "test_operation",
    **kwargs: Any,
) -> HuleEduError:
    """
    Create a HuleEduError instance for testing.

    This is a convenience function that creates an ErrorDetail
    and wraps it in HuleEduError.

    Args:
        error_code: Error code (defaults to UNKNOWN_ERROR)
        message: Error message (defaults to "Test error")
        service: Service name (defaults to "test_service")
        operation: Operation name (defaults to "test_operation")
        **kwargs: Additional fields to pass to ErrorDetail.create_with_context

    Returns:
        HuleEduError instance for testing
    """
    error_detail = create_test_error_detail(
        error_code=error_code,
        message=message,
        service=service,
        operation=operation,
        **kwargs,
    )

    return HuleEduError(error_detail)
