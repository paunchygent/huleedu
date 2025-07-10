"""Retry manager implementation for LLM API requests.

Extracted from utils/llm_utils.py to follow clean architecture
with protocol-based dependency injection.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from common_core.error_enums import ErrorCode
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import ErrorDetail
from services.cj_assessment_service.protocols import RetryManagerProtocol

logger = create_service_logger("cj_assessment_service.retry_manager_impl")


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

    def _create_error_detail(
        self,
        error_code: ErrorCode,
        message: str,
        correlation_id: UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> ErrorDetail:
        """Create an ErrorDetail object with standard fields.

        Args:
            error_code: The error code from ErrorCode enum
            message: Human-readable error message
            correlation_id: Optional correlation ID (generates new if not provided)
            details: Optional additional error context

        Returns:
            ErrorDetail instance
        """
        return ErrorDetail(
            error_code=error_code,
            message=message,
            correlation_id=correlation_id or uuid4(),
            timestamp=datetime.now(timezone.utc),
            service="cj_assessment_service",
            details=details or {},
        )

    async def with_retry(
        self,
        operation: Any,  # Callable coroutine
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, ErrorDetail | None]:
        """Execute operation with retry logic.

        Args:
            operation: The async operation to execute with retry
            *args: Arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation

        Returns:
            Tuple of (result, error_detail)
        """
        # Extract provider_name from kwargs before passing to operation
        provider_name = kwargs.pop("provider_name", "unknown")

        # Extract correlation_id if provided
        correlation_id = kwargs.get("correlation_id", uuid4())

        # Create a wrapper function that matches call_with_retry expectations
        async def operation_wrapper() -> tuple[dict[str, Any] | None, ErrorDetail | None]:
            try:
                result = await operation(*args, **kwargs)
                # Normalize result to match expected return type
                if isinstance(result, tuple) and len(result) == 2:
                    return result
                # If operation returns single value, wrap it as success
                return result, None
            except Exception:
                # Re-raise to let the retry mechanism handle it
                raise

        # Use existing call_with_retry implementation
        return await self.call_with_retry(
            operation_wrapper,
            provider_name=provider_name,
            correlation_id=correlation_id,
        )

    async def call_with_retry(
        self,
        api_request_func: Callable[[], Awaitable[tuple[dict[str, Any] | None, ErrorDetail | None]]],
        provider_name: str,
        correlation_id: UUID | None = None,
    ) -> tuple[dict[str, Any] | None, ErrorDetail | None]:
        """Execute an LLM API request function with configured retry logic.

        Args:
            api_request_func: The async function that makes the API call.
            provider_name: Name of the provider for logging purposes.

        Returns:
            Tuple of (response_data, error_detail). One will be None.
        """
        # Use provided correlation_id or generate new one
        correlation_id = correlation_id or uuid4()
        if not self.settings.llm_retry_enabled:
            logger.debug(
                f"{provider_name}: Retries disabled. Making single API call attempt.",
            )
            try:
                return await api_request_func()
            # Format errors consistently even if retries are disabled
            except TimeoutError as e:
                logger.error(f"{provider_name} API call timed out (no retry): {e}")
                return None, self._create_error_detail(
                    error_code=ErrorCode.TIMEOUT,
                    message="API call timed out",
                    correlation_id=correlation_id,
                    details={"provider": provider_name, "retry_enabled": False},
                )
            except aiohttp.ClientResponseError as e:
                logger.error(
                    f"{provider_name} API ClientResponseError (no retry): {e.status} - {e.message}",
                )
                return None, self._create_error_detail(
                    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                    message=f"API error: {e.status} - {e.message}",
                    correlation_id=correlation_id,
                    details={"provider": provider_name, "status": e.status, "retry_enabled": False},
                )
            except aiohttp.ClientError as e:  # Other client errors (connection, etc.)
                logger.error(
                    f"{provider_name} API ClientError (no retry): {e}",
                    exc_info=True,
                )
                return None, self._create_error_detail(
                    error_code=ErrorCode.CONNECTION_ERROR,
                    message=f"API client error: {e}",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "exception_type": type(e).__name__,
                        "retry_enabled": False,
                    },
                )
            except Exception as e:  # pylint: disable=broad-except
                logger.error(
                    f"{provider_name} unhandled API error (no retry): {e}",
                    exc_info=True,
                )
                return None, self._create_error_detail(
                    error_code=ErrorCode.UNKNOWN_ERROR,
                    message=f"Unexpected API error: {e!s}",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "exception_type": type(e).__name__,
                        "retry_enabled": False,
                    },
                )

        retry_exceptions_tuple = self._retry_exceptions

        if not retry_exceptions_tuple:
            logger.error(
                f"{provider_name}: No retryable exception types configured, "
                "despite retries being enabled. Attempting single call.",
            )
            try:
                return await api_request_func()
            except TimeoutError:
                return None, self._create_error_detail(
                    error_code=ErrorCode.TIMEOUT,
                    message="API call timed out",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "retry_enabled": True,
                        "no_retry_exceptions": True,
                    },
                )
            except aiohttp.ClientResponseError as e:
                return None, self._create_error_detail(
                    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                    message=f"API error: {e.status} - {e.message}",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "status": e.status,
                        "retry_enabled": True,
                        "no_retry_exceptions": True,
                    },
                )
            except aiohttp.ClientError as e:
                return None, self._create_error_detail(
                    error_code=ErrorCode.CONNECTION_ERROR,
                    message=f"API client error: {e}",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "exception_type": type(e).__name__,
                        "retry_enabled": True,
                        "no_retry_exceptions": True,
                    },
                )
            except Exception as e:  # pylint: disable=broad-except
                return None, self._create_error_detail(
                    error_code=ErrorCode.UNKNOWN_ERROR,
                    message=f"Unexpected API error: {e!s}",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "exception_type": type(e).__name__,
                        "retry_enabled": True,
                        "no_retry_exceptions": True,
                    },
                )

        retryer = AsyncRetrying(
            stop=stop_after_attempt(self.settings.llm_retry_attempts),
            wait=wait_exponential(
                min=self.settings.llm_retry_wait_min_seconds,
                max=self.settings.llm_retry_wait_max_seconds,
            ),
            retry=retry_if_exception_type(retry_exceptions_tuple),
            reraise=True,
            before_sleep=lambda rs: logger.warning(
                f"Retrying {provider_name} API call (attempt {rs.attempt_number + 1}) after error: "
                f"{rs.outcome.exception() if rs.outcome else 'Unknown error'}",
            ),
        )

        try:
            async for attempt in retryer:
                with attempt:
                    return await api_request_func()

        except RetryError as e:
            last_exception = e.last_attempt.exception()
            logger.error(
                f"{provider_name} API call failed after "
                f"{self.settings.llm_retry_attempts} retries: {last_exception}",
                exc_info=last_exception,
            )

            # Construct the error detail with "(after retries)"
            if isinstance(last_exception, TimeoutError):
                return None, self._create_error_detail(
                    error_code=ErrorCode.TIMEOUT,
                    message="API call timed out (after retries)",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "retry_attempts": self.settings.llm_retry_attempts,
                        "after_retries": True,
                    },
                )
            elif isinstance(last_exception, aiohttp.ClientResponseError):
                return None, self._create_error_detail(
                    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
                    message=(
                        f"API error: {last_exception.status} - "
                        f"{last_exception.message} (after retries)"
                    ),
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "status": last_exception.status,
                        "retry_attempts": self.settings.llm_retry_attempts,
                        "after_retries": True,
                    },
                )
            elif isinstance(last_exception, aiohttp.ClientError):
                return None, self._create_error_detail(
                    error_code=ErrorCode.CONNECTION_ERROR,
                    message=f"API client error: {last_exception} (after retries)",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "exception_type": type(last_exception).__name__,
                        "retry_attempts": self.settings.llm_retry_attempts,
                        "after_retries": True,
                    },
                )
            else:
                return None, self._create_error_detail(
                    error_code=ErrorCode.UNKNOWN_ERROR,
                    message=f"Unexpected API error: {last_exception!s} (after retries)",
                    correlation_id=correlation_id,
                    details={
                        "provider": provider_name,
                        "exception_type": type(last_exception).__name__,
                        "retry_attempts": self.settings.llm_retry_attempts,
                        "after_retries": True,
                    },
                )

        except Exception as e:  # pylint: disable=broad-except
            logger.error(
                f"{provider_name} unexpected error during retry logic: {e}",
                exc_info=True,
            )
            return None, self._create_error_detail(
                error_code=ErrorCode.PROCESSING_ERROR,
                message=f"Retry logic error: {e!s}",
                correlation_id=correlation_id,
                details={
                    "provider": provider_name,
                    "exception_type": type(e).__name__,
                    "error_context": "retry_logic",
                },
            )

        # This should never be reached, but satisfies mypy's control flow analysis
        logger.error(f"{provider_name}: Unexpected code path - retry loop completed without return")
        return None, self._create_error_detail(
            error_code=ErrorCode.UNKNOWN_ERROR,
            message="Retry logic reached unexpected state",
            correlation_id=correlation_id,
            details={
                "provider": provider_name,
                "error_context": "unexpected_code_path",
            },
        )
