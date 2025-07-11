"""Retry manager implementation for LLM API requests.

Extracted from utils/llm_utils.py to follow clean architecture
with protocol-based dependency injection.
"""

from __future__ import annotations

import asyncio
import importlib
from typing import Any, Awaitable, Callable, TypeVar
from uuid import uuid4

import aiohttp
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_connection_error,
    raise_external_service_error,
    raise_timeout_error,
    raise_unknown_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from common_core.error_enums import ErrorCode
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.protocols import RetryManagerProtocol

logger = create_service_logger("cj_assessment_service.retry_manager_impl")

# Type variable for generic return types
T = TypeVar("T")

# Define retryable error codes
RETRYABLE_ERROR_CODES = {
    ErrorCode.TIMEOUT,
    ErrorCode.CONNECTION_ERROR,
    ErrorCode.SERVICE_UNAVAILABLE,
    ErrorCode.RATE_LIMIT,
    # EXTERNAL_SERVICE_ERROR is conditionally retryable (5xx only)
}


def _load_exception_class(class_name_str: str) -> type[BaseException] | None:
    """Dynamically loads an exception class given its fully qualified name."""
    try:
        module_name, class_name = class_name_str.rsplit(".", 1)
        module = importlib.import_module(module_name)
        exception_class = getattr(module, class_name)
        # Add explicit type check to satisfy mypy
        if isinstance(exception_class, type) and issubclass(
            exception_class,
            BaseException,
        ):
            return exception_class
        logger.warning(f"'{class_name_str}' is not a BaseException subclass.")
        return None
    except (
        ImportError,
        AttributeError,
        ValueError,
    ) as e:  # More specific common errors
        logger.warning(
            f"Could not load exception class '{class_name_str}': {e}. "
            "This exception type will not be retried.",
        )
        return None
    except Exception as e:  # pylint: disable=broad-except
        logger.error(
            f"Unexpected error loading exception class '{class_name_str}': {e}",
            exc_info=True,
        )
        return None


def _get_retry_exceptions_tuple(settings: Settings) -> tuple[type[BaseException], ...]:
    """Gets a tuple of exception classes to retry on, based on config.
    Uses lru_cache to avoid reloading/recomputing on every call.
    Handles potential errors during dynamic loading.
    """
    if not settings.llm_retry_enabled:
        return tuple()

    exception_classes: list[type[BaseException]] = []
    # Define sensible defaults that cover common transient network/API issues.
    default_exceptions = (
        asyncio.TimeoutError,
        aiohttp.ClientError,
        aiohttp.ClientResponseError,
    )

    if not settings.llm_retry_on_exception_names:
        logger.warning(
            "LLM retry enabled but 'llm_retry_on_exception_names' is empty in config. "
            f"Using defaults: {[e.__name__ for e in default_exceptions]}",
        )
        return default_exceptions

    for class_name_str in settings.llm_retry_on_exception_names:
        exc_class = _load_exception_class(class_name_str)
        if exc_class:
            exception_classes.append(exc_class)

    if not exception_classes:
        logger.warning(
            "No valid exception classes were successfully loaded from "
            "'llm_retry_on_exception_names' in config. "
            "Falling back to default retry exceptions: "
            f"{[e.__name__ for e in default_exceptions]}",
        )
        return default_exceptions

    # Ensure the default_exceptions are included if not already covered
    final_exceptions_set = set(exception_classes) | set(default_exceptions)
    return tuple(final_exceptions_set)


class RetryManagerImpl(RetryManagerProtocol):
    """Implementation of RetryManagerProtocol for LLM API request retry logic."""

    def __init__(self, settings: Settings) -> None:
        """Initialize retry manager with settings.

        Args:
            settings: Application settings for retry configuration.
        """
        self.settings = settings
        # Cache the retry exceptions tuple at initialization
        self._retry_exceptions = _get_retry_exceptions_tuple(settings)

    def _should_retry_error(self, exception: BaseException) -> bool:
        """Determine if an error should be retried based on its type and error code.

        Args:
            exception: The exception to evaluate

        Returns:
            True if the error should be retried, False otherwise
        """
        # Handle HuleEduError with error code classification
        if isinstance(exception, HuleEduError):
            error_code = exception.error_detail.error_code

            # Check if it's a directly retryable error code
            if error_code in RETRYABLE_ERROR_CODES:
                return True

            # Special handling for external service errors
            if error_code == ErrorCode.EXTERNAL_SERVICE_ERROR:
                # Only retry 5xx errors
                status_code = exception.error_detail.details.get("status_code")
                if status_code and isinstance(status_code, int) and 500 <= status_code < 600:
                    return True

            return False

        # Handle raw exceptions that should be retried
        if isinstance(exception, (asyncio.TimeoutError, aiohttp.ClientError)):
            return True

        return False

    async def with_retry(
        self,
        operation: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute operation with retry logic.

        Args:
            operation: The async operation to execute with retry
            *args: Arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation

        Returns:
            The result from the successful operation

        Raises:
            HuleEduError: On permanent failure after all retries exhausted
        """
        # Extract metadata from kwargs and remove from operation kwargs
        provider_name = kwargs.pop("provider_name", "unknown")
        correlation_id = kwargs.pop("correlation_id", uuid4())

        if not self.settings.llm_retry_enabled:
            logger.debug(f"{provider_name}: Retries disabled. Making single API call attempt.")
            try:
                return await operation(*args, **kwargs)
            except TimeoutError:
                raise_timeout_error(
                    service="cj_assessment_service",
                    operation="retry_manager.with_retry",
                    timeout_seconds=0,  # Could be extracted from context
                    message="API call timed out",
                    correlation_id=correlation_id,
                    provider=provider_name,
                    retry_enabled=False,
                )
            except aiohttp.ClientResponseError as e:
                raise_external_service_error(
                    service="cj_assessment_service",
                    operation="retry_manager.with_retry",
                    external_service=provider_name,
                    message=f"API error: {e.status} - {e.message}",
                    correlation_id=correlation_id,
                    status_code=e.status,
                    retry_enabled=False,
                )
            except aiohttp.ClientError as e:
                raise_connection_error(
                    service="cj_assessment_service",
                    operation="retry_manager.with_retry",
                    target=provider_name,
                    message=f"API client error: {e}",
                    correlation_id=correlation_id,
                    exception_type=type(e).__name__,
                    retry_enabled=False,
                )
            except HuleEduError:
                # Already a properly formatted error, just re-raise
                raise
            except Exception as e:
                raise_unknown_error(
                    service="cj_assessment_service",
                    operation="retry_manager.with_retry",
                    message=f"Unexpected error: {str(e)}",
                    correlation_id=correlation_id,
                    provider=provider_name,
                    exception_type=type(e).__name__,
                    retry_enabled=False,
                )

        # Create retry configuration
        retryer = AsyncRetrying(
            stop=stop_after_attempt(self.settings.llm_retry_attempts),
            wait=wait_exponential(
                min=self.settings.llm_retry_wait_min_seconds,
                max=self.settings.llm_retry_wait_max_seconds,
            ),
            retry=retry_if_exception(self._should_retry_error),
            reraise=True,
            before_sleep=lambda rs: logger.warning(
                f"Retrying {provider_name} API call (attempt {rs.attempt_number + 1}) "
                f"after error: {rs.outcome.exception() if rs.outcome else 'Unknown error'}"
            ),
        )

        try:
            async for attempt in retryer:
                with attempt:
                    return await operation(*args, **kwargs)

        except RetryError as retry_error:
            last_exception = retry_error.last_attempt.exception()
            logger.error(
                f"{provider_name} API call failed after {self.settings.llm_retry_attempts} retries",
                exc_info=last_exception,
            )

            # Handle the final error after all retries
            if isinstance(last_exception, HuleEduError):
                # Enhance existing error with retry information
                raise last_exception.add_detail("after_retries", True).add_detail(
                    "retry_attempts", self.settings.llm_retry_attempts
                )
            elif isinstance(last_exception, TimeoutError):
                raise_timeout_error(
                    service="cj_assessment_service",
                    operation="retry_manager.with_retry",
                    timeout_seconds=0,
                    message="API call timed out (after retries)",
                    correlation_id=correlation_id,
                    provider=provider_name,
                    retry_attempts=self.settings.llm_retry_attempts,
                    after_retries=True,
                )
            elif isinstance(last_exception, aiohttp.ClientResponseError):
                raise_external_service_error(
                    service="cj_assessment_service",
                    operation="retry_manager.with_retry",
                    external_service=provider_name,
                    message=(
                        f"API error: {last_exception.status} - "
                        f"{last_exception.message} (after retries)"
                    ),
                    correlation_id=correlation_id,
                    status_code=last_exception.status,
                    retry_attempts=self.settings.llm_retry_attempts,
                    after_retries=True,
                )
            elif isinstance(last_exception, aiohttp.ClientError):
                raise_connection_error(
                    service="cj_assessment_service",
                    operation="retry_manager.with_retry",
                    target=provider_name,
                    message=f"API client error: {last_exception} (after retries)",
                    correlation_id=correlation_id,
                    exception_type=type(last_exception).__name__,
                    retry_attempts=self.settings.llm_retry_attempts,
                    after_retries=True,
                )
            else:
                raise_unknown_error(
                    service="cj_assessment_service",
                    operation="retry_manager.with_retry",
                    message=f"Unexpected error after retries: {str(last_exception)}",
                    correlation_id=correlation_id,
                    provider=provider_name,
                    exception_type=type(last_exception).__name__,
                    retry_attempts=self.settings.llm_retry_attempts,
                    after_retries=True,
                )

        # This should never be reached, but satisfies mypy
        raise RuntimeError("Retry logic completed without returning or raising")
