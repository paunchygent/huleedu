"""Retry manager implementation for LLM requests."""

import asyncio
from typing import Any, Awaitable, Callable, TypeVar

from huleedu_service_libs.logging_utils import create_service_logger
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from services.llm_provider_service.config import Settings
from services.llm_provider_service.protocols import LLMRetryManagerProtocol

logger = create_service_logger("llm_provider_service.retry_manager")

T = TypeVar("T")


class RetryManagerImpl(LLMRetryManagerProtocol):
    """Tenacity-based retry manager for LLM requests."""

    def __init__(self, settings: Settings):
        """Initialize retry manager.

        Args:
            settings: Service settings
        """
        self.settings = settings

        # Define retryable exceptions
        self.retryable_exceptions = (
            asyncio.TimeoutError,
            ConnectionError,
            # HTTP errors that should be retried
            # Will be caught as aiohttp.ClientResponseError with specific status codes
        )

    async def with_retry(
        self,
        operation: Callable[..., Awaitable[Any]],
        operation_name: str,
        **kwargs: Any,
    ) -> Any:
        """Execute operation with retry logic.

        Args:
            operation: Async operation to execute
            operation_name: Name of operation for logging
            **kwargs: Arguments to pass to operation

        Returns:
            Result from operation

        Raises:
            Original exception if all retries fail
        """
        # Create retry configuration
        retry_config = AsyncRetrying(
            stop=stop_after_attempt(3),  # Max 3 attempts
            wait=wait_exponential(multiplier=1, min=4, max=60),  # 4s, 8s, 16s...
            retry=retry_if_exception_type(self.retryable_exceptions),
            reraise=True,
        )

        attempt_number = 0

        async for attempt in retry_config:
            with attempt:
                attempt_number += 1
                if attempt_number > 1:
                    logger.warning(f"Retrying {operation_name} (attempt {attempt_number}/3)")

                try:
                    # Execute the operation
                    result = await operation(**kwargs)

                    if attempt_number > 1:
                        logger.info(
                            f"Successfully completed {operation_name} after "
                            f"{attempt_number} attempts"
                        )

                    return result

                except Exception as e:
                    # Check if this is an HTTP error with retryable status code
                    if hasattr(e, "status") and e.status in {429, 500, 502, 503, 504}:
                        logger.warning(
                            f"{operation_name} failed with retryable HTTP status "
                            f"{e.status}: {str(e)}"
                        )
                        raise  # Will be retried by tenacity

                    # Check if it's a known retryable exception
                    if isinstance(e, self.retryable_exceptions):
                        logger.warning(f"{operation_name} failed with retryable error: {str(e)}")
                        raise  # Will be retried by tenacity

                    # Non-retryable error
                    logger.error(f"{operation_name} failed with non-retryable error: {str(e)}")
                    raise  # Will not be retried

        # This should never be reached due to reraise=True, but just in case
        raise RuntimeError(f"Retry logic failed for {operation_name}")
