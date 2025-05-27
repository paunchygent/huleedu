# src/cj_essay_assessment/llm_utils.py

"""Utility functions for LLM interactions, including retry logic."""

import asyncio
import importlib
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

import aiohttp
from loguru import logger
from tenacity import (AsyncRetrying, RetryError, retry_if_exception_type,
                      stop_after_attempt, wait_exponential)

from src.cj_essay_assessment.config import Settings, get_settings


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


@lru_cache(maxsize=1)
def get_retry_exceptions_tuple() -> tuple[type[BaseException], ...]:
    """Gets a tuple of exception classes to retry on, based on config.
    Uses lru_cache to avoid reloading/recomputing on every call.
    Handles potential errors during dynamic loading.
    """
    settings = get_settings()
    if not settings.llm_retry_enabled:
        return tuple()

    exception_classes: list[type[BaseException]] = []
    # Define sensible defaults that cover common transient network/API issues.
    # aiohttp.ClientError is a base for many aiohttp exceptions like ClientConnectionError, ServerDisconnectedError.
    # aiohttp.ClientResponseError is raised by response.raise_for_status().
    default_exceptions = (
        asyncio.TimeoutError,
        aiohttp.ClientError,
        aiohttp.ClientResponseError,
    )

    if not settings.llm_retry_on_exception_names:
        logger.warning(
            "LLM retry enabled but 'llm_retry_on_exception_names' is empty in config. Using defaults: "
            f"{[e.__name__ for e in default_exceptions]}",
        )
        return default_exceptions

    for class_name_str in settings.llm_retry_on_exception_names:
        exc_class = _load_exception_class(class_name_str)
        if exc_class:
            exception_classes.append(exc_class)
        else:
            # _load_exception_class already logs a warning
            pass

    if not exception_classes:
        logger.warning(
            "No valid exception classes were successfully loaded from 'llm_retry_on_exception_names' in config. "
            f"Falling back to default retry exceptions: {[e.__name__ for e in default_exceptions]}",
        )
        return default_exceptions

    # Ensure the default_exceptions are included if not already covered by loaded classes
    # or if specific ones like ClientResponseError weren't explicitly named but ClientError was.
    final_exceptions_set = set(exception_classes) | set(default_exceptions)

    return tuple(final_exceptions_set)


# Type alias for the function that makes the actual API call
# This function is expected to:
# 1. Raise an exception from retry_exceptions_tuple if a retryable error occurs.
# 2. Return (None, error_message_str) if a non-retryable error occurs that it handles.
# 3. Return (data_dict, None) on success.
ApiRequestCallable = Callable[
    [],
    Awaitable[tuple[dict[str, Any] | None, str | None]],
]


async def call_llm_api_with_retry(
    api_request_func: ApiRequestCallable,
    settings: Settings,
    provider_name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Executes an LLM API request function with configured retry logic."""
    if not settings.llm_retry_enabled:
        logger.debug(
            f"{provider_name}: Retries disabled. Making single API call attempt.",
        )
        try:
            return await api_request_func()
        # Format errors consistently even if retries are disabled
        except TimeoutError as e:
            logger.error(f"{provider_name} API call timed out (no retry): {e}")
            return None, "API call timed out"
        except aiohttp.ClientResponseError as e:
            logger.error(
                f"{provider_name} API ClientResponseError (no retry): {e.status} - {e.message}",
            )
            return None, f"API error: {e.status} - {e.message}"
        except aiohttp.ClientError as e:  # Other client errors (connection, etc.)
            logger.error(
                f"{provider_name} API ClientError (no retry): {e}",
                exc_info=True,
            )
            return None, f"API client error: {e}"
        except Exception as e:  # pylint: disable=broad-except
            logger.error(
                f"{provider_name} unhandled API error (no retry): {e}",
                exc_info=True,
            )
            return (
                None,
                f"Unexpected API error: {e!s}",
            )  # Align with generic test expectation

    retry_exceptions_tuple: tuple[type[BaseException], ...] = get_retry_exceptions_tuple()
    # This check is more of a safeguard; get_retry_exceptions_tuple should always return defaults if empty.
    if not retry_exceptions_tuple:
        logger.error(
            f"{provider_name}: No retryable exception types configured, despite retries being enabled. Attempting single call.",
        )
        try:
            return await api_request_func()
        # Mirror the error handling from the "retries disabled" block for consistency
        except TimeoutError:
            return None, "API call timed out"
        except aiohttp.ClientResponseError as e:
            return None, f"API error: {e.status} - {e.message}"
        except aiohttp.ClientError as e:
            return None, f"API client error: {e}"
        except Exception as e:  # pylint: disable=broad-except
            return None, f"Unexpected API error: {e!s}"

    retryer = AsyncRetrying(
        stop=stop_after_attempt(settings.llm_retry_attempts),
        wait=wait_exponential(
            min=settings.llm_retry_wait_min_seconds,
            max=settings.llm_retry_wait_max_seconds,
        ),
        retry=retry_if_exception_type(retry_exceptions_tuple),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            f"{provider_name}: Retrying API call (attempt {rs.attempt_number + 1}) after error: {rs.outcome.exception() if rs.outcome else 'Unknown error'}",
        ),
    )

    try:
        # Use the proper async for pattern with AsyncRetrying
        # Each attempt will run api_request_func and either:
        # - Return its result if successful
        # - Retry if a retryable exception occurs
        # - Raise RetryError if max attempts are reached
        async for attempt in retryer:
            with attempt:
                return await api_request_func()

    except RetryError as e:
        last_exception = e.last_attempt.exception()
        logger.error(
            f"{provider_name} API call failed after {settings.llm_retry_attempts} retries: {last_exception}",
            exc_info=last_exception,
        )

        # Construct the error message with "(after retries)"
        if isinstance(last_exception, aiohttp.ClientResponseError):
            error_message = f"API error: {last_exception.status} - {last_exception.message} (after retries)"
        elif isinstance(last_exception, asyncio.TimeoutError):
            error_message = "API call timed out (after retries)"
        elif isinstance(
            last_exception,
            aiohttp.ClientError,
        ):  # More generic aiohttp client error
            error_message = f"API client error: {last_exception} (after retries)"
        elif last_exception:  # For other retryable exceptions
            error_message = f"API call failed after retries due to {type(last_exception).__name__}: {last_exception} (after retries)"
        else:  # Should ideally not happen if RetryError always has a last_exception
            error_message = f"API call failed after {settings.llm_retry_attempts} retries (unknown error type)"
        return None, error_message

    except Exception as e:  # pylint: disable=broad-except
        # This block catches:
        # 1. Exceptions from api_request_func if they were NOT in retry_exceptions_tuple
        #    (meaning api_request_func raised something unexpected instead of returning an error tuple).
        # 2. Potentially, errors from Tenacity itself if reraise=False was used (but it's True).
        # It's a safety net.
        logger.error(
            f"{provider_name}: Unexpected error propagated from API call processing: {e}",
            exc_info=True,
        )
        # Align with generic test expectation and no-retry path format
        if isinstance(e, asyncio.TimeoutError):
            return None, "API call timed out"
        if isinstance(e, aiohttp.ClientResponseError):
            return None, f"API error: {e.status} - {e.message}"
        if isinstance(e, aiohttp.ClientError):
            return None, f"API client error: {e}"
        return None, f"Unexpected API error: {e!s}"

    # The following line is unreachable but helps mypy understand all paths return
    return None, "Unreachable code path"  # pragma: no cover
