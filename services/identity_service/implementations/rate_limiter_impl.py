"""Rate limiter implementation using Redis."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.identity_service.protocols import RateLimiterProtocol

logger = create_service_logger("identity_service.rate_limiter")


class RateLimiterImpl(RateLimiterProtocol):
    """Redis-based rate limiter implementation."""

    def __init__(self, redis_client: AtomicRedisClientProtocol):
        """
        Initialize rate limiter with Redis client.

        Args:
            redis_client: Redis client for storing rate limit counters
        """
        self.redis = redis_client

    async def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check if a rate limit allows the operation.

        Args:
            key: The rate limit key (e.g., "login:ip:192.168.1.1")
            limit: Maximum number of attempts allowed
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed, remaining_attempts)
        """
        try:
            # Get current count
            current_value = await self.redis.get(key)

            if current_value is None:
                # Key doesn't exist, first attempt
                return True, limit - 1

            try:
                current_count = int(current_value)
            except (ValueError, TypeError):
                # Invalid value, reset
                await self.redis.delete_key(key)
                return True, limit - 1

            if current_count >= limit:
                # Rate limit exceeded
                logger.warning(
                    "Rate limit exceeded",
                    extra={
                        "key": key,
                        "current_count": current_count,
                        "limit": limit,
                        "window_seconds": window_seconds,
                    },
                )
                return False, 0

            # Under limit
            remaining = limit - current_count - 1
            return True, remaining

        except Exception as e:
            logger.error(f"Rate limit check failed: {e}", extra={"key": key, "error": str(e)})
            # On error, allow the request but log it
            return True, limit - 1

    async def increment(self, key: str, window_seconds: int) -> int:
        """
        Increment the counter for a rate limit key.

        Args:
            key: The rate limit key
            window_seconds: TTL for the key

        Returns:
            New count after increment
        """
        try:
            # Try to get current value first
            current_value = await self.redis.get(key)

            if current_value is None:
                # First attempt, set with TTL
                success = await self.redis.set_if_not_exists(key, "1", ttl_seconds=window_seconds)
                if success:
                    return 1
                else:
                    # Race condition, someone else set it first
                    # Try to get the value again
                    current_value = await self.redis.get(key)
                    if current_value:
                        try:
                            return int(current_value)
                        except (ValueError, TypeError):
                            return 1
                    return 1

            # Increment existing value
            try:
                current_count = int(current_value)
            except (ValueError, TypeError):
                # Invalid value, reset to 1
                await self.redis.setex(key, window_seconds, "1")
                return 1

            new_count = current_count + 1

            # Update with existing TTL (we can't easily get TTL, so we reset it)
            # In production, you might want to use a Lua script to preserve TTL
            await self.redis.setex(key, window_seconds, str(new_count))

            logger.debug(
                "Rate limit incremented",
                extra={
                    "key": key,
                    "new_count": new_count,
                    "window_seconds": window_seconds,
                },
            )

            return new_count

        except Exception as e:
            logger.error(f"Rate limit increment failed: {e}", extra={"key": key, "error": str(e)})
            # On error, return 1 (conservative approach)
            return 1

    async def reset(self, key: str) -> bool:
        """
        Reset a rate limit key.

        Args:
            key: The rate limit key to reset

        Returns:
            True if the key was deleted, False otherwise
        """
        try:
            result = await self.redis.delete_key(key)

            if result:
                logger.info("Rate limit reset", extra={"key": key})

            return bool(result)

        except Exception as e:
            logger.error(f"Rate limit reset failed: {e}", extra={"key": key, "error": str(e)})
            return False


def create_rate_limit_key(action: str, identifier: str, namespace: str = "identity") -> str:
    """
    Create a standardized rate limit key.

    Args:
        action: The action being rate limited (e.g., "login", "register")
        identifier: The identifier to rate limit (e.g., IP address, email)
        namespace: The namespace for the key (default: "identity")

    Returns:
        Formatted rate limit key
    """
    # Replace special characters to avoid Redis key issues
    safe_identifier = identifier.replace(":", "_").replace("@", "_at_")
    return f"{namespace}:rate_limit:{action}:{safe_identifier}"
