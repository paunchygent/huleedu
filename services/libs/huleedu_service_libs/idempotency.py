"""
Idempotency decorator for Kafka message handlers.

Provides DRY implementation of event idempotency using Redis SETNX operations.
Follows the same architectural patterns as other service library components.

TODO: Future retry enhancement integration - see 045-retry-logic.mdc for details
on how this decorator may be extended to support explicit retry categorization
and retry count tracking while maintaining the current natural retry behavior.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from aiokafka import ConsumerRecord

from .event_utils import generate_deterministic_event_id
from .logging_utils import create_service_logger
from .protocols import RedisClientProtocol

logger = create_service_logger("idempotency-decorator")

# Type variable for the handler function
P = TypeVar("P")
T = TypeVar("T")


def idempotent_consumer(
    redis_client: RedisClientProtocol,
    ttl_seconds: int = 86400,  # 24 hours default
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any | None]]]:
    """
    Decorator to make a Kafka message handler idempotent using Redis.

    Uses deterministic event ID generation from common_core to create Redis keys
    for duplicate detection. Implements atomic SETNX operations with TTL.

    Args:
        redis_client: An active Redis client implementing RedisClientProtocol
        ttl_seconds: Time-to-live for idempotency keys in Redis (default: 24 hours)

    Returns:
        Decorator function that wraps message handlers with idempotency logic

    Example:
        ```python
        @idempotent_consumer(redis_client=redis_client, ttl_seconds=3600)
        async def handle_message(msg: ConsumerRecord) -> Any:
            # Process message logic here
            return result
        ```
    """

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any | None]]:
        @functools.wraps(func)
        async def wrapper(msg: ConsumerRecord, *args: Any, **kwargs: Any) -> Any | None:
            # Generate deterministic ID from message content
            deterministic_id = generate_deterministic_event_id(msg.value)
            key = f"huleedu:events:seen:{deterministic_id}"

            logger.debug(f"Checking idempotency for event {deterministic_id}")

            # Atomically set the key if it does not exist
            # If set_if_not_exists returns False, the key already existed (duplicate)
            try:
                is_first_time = await redis_client.set_if_not_exists(
                    key,
                    "1",
                    ttl_seconds=ttl_seconds,
                )

                if not is_first_time:
                    logger.warning(
                        f"Duplicate event skipped: {deterministic_id} (Redis key: {key})",
                    )
                    return None  # Signal to caller that this was a duplicate

                logger.debug(f"Processing first-time event: {deterministic_id}")

                # Execute the actual business logic
                try:
                    result = await func(msg, *args, **kwargs)
                    logger.debug(f"Successfully processed event: {deterministic_id}")
                    return result

                except Exception as processing_error:
                    # If processing fails, release the lock so the event can be retried
                    logger.error(
                        f"Processing failed for event {deterministic_id}. "
                        f"Releasing idempotency lock for retry.",
                        exc_info=True,
                    )

                    try:
                        await redis_client.delete_key(key)
                        logger.debug(f"Released idempotency key: {key}")
                    except Exception as cleanup_error:
                        logger.error(
                            f"Failed to cleanup idempotency key {key} after "
                            f"processing failure: {cleanup_error}",
                            exc_info=True,
                        )

                    # Re-raise the original processing exception
                    raise processing_error

            except Exception as redis_error:
                logger.error(
                    f"Redis operation failed for idempotency check of event "
                    f"{deterministic_id}: {redis_error}",
                    exc_info=True,
                )
                # In case of Redis failure, let the message process
                # (fail-open approach to avoid blocking the pipeline)
                logger.warning(
                    f"Processing event {deterministic_id} without idempotency "
                    f"protection due to Redis error",
                )
                return await func(msg, *args, **kwargs)

        return wrapper

    return decorator
