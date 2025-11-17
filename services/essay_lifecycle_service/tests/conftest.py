"""Pytest configuration for the Essay Lifecycle Service test suite.

This file provides fixtures that are automatically applied to all tests
within this directory, ensuring a clean and consistent testing environment.

Public API:
    - _clear_prometheus_registry: Fixture to clear the global Prometheus registry.
    - assert_huleedu_error: Function to assert HuleEduError has expected structure and values.
    - expect_huleedu_error: Context manager for expecting HuleEduError with validation.
    - assert_correlation_id_propagated: Validate correlation ID is properly propagated in error.
    - assert_error_detail_structure: Validate error_detail has required fields and structure.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Generator
from contextlib import _AsyncGeneratorContextManager, asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from huleedu_service_libs.error_handling import HuleEduError
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import REGISTRY


@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear the global Prometheus registry before each test.

    This fixture prevents `ValueError: Duplicated timeseries` errors when running
    multiple tests that define the same metrics in the same process. This is the
    standard pattern mandated by rule 070-testing-and-quality-assurance.md.

    It is marked with `autouse=True` to be automatically applied to every
    test function within its scope without needing to be explicitly requested.

    Yields:
        None: Yields control back to the test function.
    """
    # Get a list of all collector names currently in the registry
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        # Unregister each collector to ensure a clean state
        REGISTRY.unregister(collector)
    yield


@pytest.fixture
def opentelemetry_test_isolation() -> Generator[InMemorySpanExporter, None, None]:
    """
    Provide OpenTelemetry test isolation with InMemorySpanExporter.

    Works with existing TracerProvider by adding a test span processor
    with InMemorySpanExporter for collecting spans during tests.
    Cleans up after each test for proper isolation.
    """
    # Create an in-memory span exporter for test span collection
    span_exporter = InMemorySpanExporter()

    # Get the current tracer provider (may be already set by service initialization)
    current_provider = trace.get_tracer_provider()

    # If no provider is set yet, create one for tests
    if not hasattr(current_provider, "add_span_processor"):
        test_provider = TracerProvider()
        trace.set_tracer_provider(test_provider)
        current_provider = test_provider

    # Add our test span processor to the existing provider
    test_processor = SimpleSpanProcessor(span_exporter)
    current_provider.add_span_processor(test_processor)

    try:
        # Yield the exporter so tests can access recorded spans
        yield span_exporter
    finally:
        # Clean up: clear spans and remove our processor if possible
        span_exporter.clear()
        # Note: TracerProvider doesn't have remove_span_processor,
        # but clearing the exporter is sufficient for test isolation


@pytest.fixture
def mock_session_factory() -> Callable[[], AsyncMock]:
    """
    Mock session factory for Unit of Work pattern.

    Returns a factory that creates AsyncSession mocks with proper
    async context manager support for transactions.
    """
    # Create the transaction mock
    mock_transaction = AsyncMock()
    mock_transaction.__aenter__.return_value = None
    mock_transaction.__aexit__.return_value = None

    # Create the session mock
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    # Make begin() return the transaction directly (not as a coroutine)
    mock_session.begin = MagicMock(return_value=mock_transaction)

    # Create the factory that returns the session when called
    mock_factory = MagicMock()
    mock_factory.return_value = mock_session

    # Attach the session to the factory for easy access in tests
    mock_factory._test_session = mock_session
    mock_factory._test_transaction = mock_transaction

    return mock_factory


# Error Testing Utilities following Rule 048 exception-based patterns


def assert_huleedu_error(
    exception: HuleEduError,
    expected_code: str,
    expected_correlation_id: UUID | None = None,
    expected_service: str = "essay_lifecycle_service",
) -> None:
    """Assert HuleEduError has expected structure and values.

    This utility validates that a caught HuleEduError follows the Rule 048
    exception-based pattern and contains the expected error code, service,
    and optionally correlation ID.

    Args:
        exception: The HuleEduError instance to validate
        expected_code: Expected error code value (string, e.g., "VALIDATION_ERROR")
        expected_correlation_id: Optional expected correlation ID
        expected_service: Expected service name (defaults to "essay_lifecycle_service")

    Raises:
        AssertionError: If any validation fails

    Example:
        try:
            await service.some_operation()
        except HuleEduError as e:
            assert_huleedu_error(e, "RESOURCE_NOT_FOUND", correlation_id)
    """
    # Validate exception type
    assert isinstance(exception, HuleEduError), f"Expected HuleEduError, got {type(exception)}"

    # Validate error_detail exists and has proper structure
    assert hasattr(exception, "error_detail"), "HuleEduError missing error_detail attribute"
    error_detail = exception.error_detail

    # Validate error_detail structure
    assert_error_detail_structure(error_detail.model_dump())

    # Validate error code
    assert error_detail.error_code.value == expected_code, (
        f"Expected error code '{expected_code}', got '{error_detail.error_code.value}'"
    )

    # Validate service
    assert error_detail.service == expected_service, (
        f"Expected service '{expected_service}', got '{error_detail.service}'"
    )

    # Validate correlation ID if provided
    if expected_correlation_id is not None:
        assert_correlation_id_propagated(exception, expected_correlation_id)


@asynccontextmanager
async def expect_huleedu_error(
    expected_code: str,
    expected_correlation_id: UUID | None = None,
) -> AsyncGenerator[None, None]:
    """Context manager for expecting HuleEduError with validation.

    This async context manager validates that a HuleEduError is raised
    with the expected error code and optionally correlation ID. It follows
    the Rule 048 exception-based pattern for testing.

    Args:
        expected_code: Expected error code value (string, e.g., "VALIDATION_ERROR")
        expected_correlation_id: Optional expected correlation ID

    Yields:
        None - Context for the test code that should raise the error

    Raises:
        AssertionError: If no error is raised or error doesn't match expected values

    Example:
        async with expect_huleedu_error("RESOURCE_NOT_FOUND", correlation_id):
            await service.get_nonexistent_essay("invalid-id")

        # Error has been validated by the context manager
    """
    try:
        yield
        # If we reach here, no exception was raised
        raise AssertionError(
            f"Expected HuleEduError with code '{expected_code}' but no error was raised"
        )
    except HuleEduError as e:
        # Validate the error matches expectations
        assert_huleedu_error(e, expected_code, expected_correlation_id)
    except Exception as e:
        # Any other exception type is unexpected
        raise AssertionError(f"Expected HuleEduError but got {type(e).__name__}: {str(e)}") from e


def assert_correlation_id_propagated(
    error: HuleEduError,
    expected_correlation_id: UUID,
) -> None:
    """Validate correlation ID is properly propagated in error.

    This utility ensures that the correlation ID is correctly propagated
    through the error handling chain, which is critical for distributed
    tracing and request correlation.

    Args:
        error: The HuleEduError to validate
        expected_correlation_id: The expected correlation ID

    Raises:
        AssertionError: If correlation ID doesn't match or is missing

    Example:
        correlation_id = uuid4()
        try:
            await service.operation_with_correlation(correlation_id)
        except HuleEduError as e:
            assert_correlation_id_propagated(e, correlation_id)
    """
    assert error.error_detail.correlation_id == expected_correlation_id, (
        f"Expected correlation_id '{expected_correlation_id}', "
        f"got '{error.error_detail.correlation_id}'"
    )


def assert_error_detail_structure(error_detail: dict[str, Any]) -> None:
    """Validate error_detail has required fields and structure.

    This utility validates that an error_detail dictionary contains all
    required fields according to the ErrorDetail model and Rule 048 standards.
    Works with both raw model_dump() output and serialized JSON data.

    Args:
        error_detail: The error detail dictionary to validate

    Raises:
        AssertionError: If any required field is missing or has wrong type

    Example:
        error_dict = error.error_detail.model_dump()
        assert_error_detail_structure(error_dict)
    """
    from datetime import datetime
    from uuid import UUID

    from common_core.error_enums import ErrorCode

    # Required fields with their acceptable types
    required_fields = {
        "error_code": (ErrorCode, str),  # Enum or serialized string
        "message": (str,),
        "correlation_id": (UUID, str),  # UUID object or serialized string
        "timestamp": (datetime, str),  # datetime object or serialized string
        "service": (str,),
        "operation": (str,),
        "details": (dict,),
    }

    # Check all required fields are present
    for field_name, expected_types in required_fields.items():
        assert field_name in error_detail, f"Missing required field: {field_name}"

        field_value = error_detail[field_name]

        # Special handling for details field (can be empty dict)
        if field_name == "details":
            assert isinstance(field_value, dict), (
                f"Field '{field_name}' must be dict, got {type(field_value)}"
            )
        else:
            # All other fields must be non-empty and of correct type
            assert field_value is not None, f"Field '{field_name}' cannot be None"
            assert isinstance(field_value, expected_types), (
                f"Field '{field_name}' must be one of {expected_types}, got {type(field_value)}"
            )

            # Additional validation for string fields
            if isinstance(field_value, str) and field_name in ("message", "service", "operation"):
                assert field_value.strip(), f"Field '{field_name}' cannot be empty string"


# Make error testing utilities available as pytest fixtures for test dependency injection


@pytest.fixture
def huleedu_error_validator() -> Callable[[HuleEduError, str, UUID | None, str], None]:
    """Provide assert_huleedu_error as a pytest fixture."""
    return assert_huleedu_error


@pytest.fixture
def huleedu_error_expecter() -> Callable[
    [str, UUID | None], _AsyncGeneratorContextManager[None, None]
]:
    """Provide expect_huleedu_error as a pytest fixture."""
    return expect_huleedu_error


@pytest.fixture
def correlation_id_validator() -> Callable[[HuleEduError, UUID], None]:
    """Provide assert_correlation_id_propagated as a pytest fixture."""
    return assert_correlation_id_propagated


@pytest.fixture
def error_detail_validator() -> Callable[[dict[str, Any]], None]:
    """Provide assert_error_detail_structure as a pytest fixture."""
    return assert_error_detail_structure
