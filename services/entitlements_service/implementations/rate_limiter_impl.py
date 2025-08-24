"""Rate limiter implementation for Entitlements Service.

This module provides Redis-based sliding window rate limiting for
controlling operation frequency and preventing abuse.
"""

from __future__ import annotations

import time

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.entitlements_service.protocols import (
    PolicyLoaderProtocol,
    RateLimitCheck,
    RateLimiterProtocol,
)

logger = create_service_logger("entitlements_service.rate_limiter")


class RateLimiterImpl(RateLimiterProtocol):
    """Redis-based sliding window rate limiter implementation."""

    def __init__(
        self,
        redis_client: AtomicRedisClientProtocol,
        policy_loader: PolicyLoaderProtocol,
        enabled: bool = True,
    ) -> None:
        """Initialize rate limiter.

        Args:
            redis_client: Redis client for state management
            policy_loader: Policy loader for rate limit configuration
            enabled: Whether rate limiting is enabled
        """
        self.redis_client = redis_client
        self.policy_loader = policy_loader
        self.enabled = enabled
        self.key_prefix = "rate_limit"

    async def check_rate_limit(
        self,
        subject_id: str,
        metric: str,
        amount: int = 1,
    ) -> RateLimitCheck:
        """Check if operation is within rate limits.

        Uses Redis sorted sets for sliding window rate limiting.

        Args:
            subject_id: Subject performing the operation
            metric: Operation metric name
            amount: Number of operations requested

        Returns:
            RateLimitCheck with limit status and current usage
        """
        if not self.enabled:
            logger.debug("Rate limiting disabled, allowing operation")
            return RateLimitCheck(
                allowed=True,
                limit=0,
                window_seconds=0,
                current_count=0,
            )

        try:
            # Get rate limit configuration
            limit, window_seconds = await self.policy_loader.get_rate_limit(metric)

            # No limit configured
            if limit == 0 or window_seconds == 0:
                logger.debug(f"No rate limit for {metric}, allowing operation")
                return RateLimitCheck(
                    allowed=True,
                    limit=0,
                    window_seconds=0,
                    current_count=0,
                )

            # Create Redis key for this subject/metric combination
            key = f"{self.key_prefix}:{subject_id}:{metric}"

            # Calculate window start time
            current_time = time.time()
            window_start = current_time - window_seconds

            # Remove old entries outside the window using ZREMRANGEBYSCORE
            # This implements the sliding window cleanup
            pipeline = await self.redis_client.create_transaction_pipeline()
            pipeline.zremrangebyscore(key, "-inf", window_start)

            # Count current entries in the window
            pipeline.zcard(key)

            # Execute pipeline
            results = await pipeline.execute()
            current_count = results[1] if len(results) > 1 else 0

            # Check if adding new operations would exceed limit
            would_exceed = (current_count + amount) > limit

            logger.debug(
                f"Rate limit check for {subject_id}/{metric}: "
                f"{current_count}/{limit} in {window_seconds}s window",
                extra={
                    "subject_id": subject_id,
                    "metric": metric,
                    "current_count": current_count,
                    "limit": limit,
                    "amount_requested": amount,
                    "allowed": not would_exceed,
                },
            )

            return RateLimitCheck(
                allowed=not would_exceed,
                limit=limit,
                window_seconds=window_seconds,
                current_count=current_count,
            )

        except Exception as e:
            logger.error(f"Error checking rate limit: {e}", exc_info=True)
            # On error, fail open (allow the operation) to avoid blocking users
            return RateLimitCheck(
                allowed=True,
                limit=0,
                window_seconds=0,
                current_count=0,
            )

    async def record_usage(
        self,
        subject_id: str,
        metric: str,
        amount: int = 1,
    ) -> None:
        """Record usage for rate limiting calculations.

        Adds entries to Redis sorted set with current timestamp as score.

        Args:
            subject_id: Subject performing the operation
            metric: Operation metric name
            amount: Number of operations performed
        """
        if not self.enabled:
            logger.debug("Rate limiting disabled, not recording usage")
            return

        try:
            # Get rate limit configuration to set appropriate TTL
            limit, window_seconds = await self.policy_loader.get_rate_limit(metric)

            # Skip if no limit configured
            if limit == 0 or window_seconds == 0:
                logger.debug(f"No rate limit for {metric}, skipping usage recording")
                return

            # Create Redis key
            key = f"{self.key_prefix}:{subject_id}:{metric}"
            current_time = time.time()

            # Add entries to sorted set
            # Each entry has current timestamp as score for sliding window
            entries = {}
            for i in range(amount):
                # Add small offset to ensure unique entries
                timestamp = current_time + (i * 0.001)
                # Use timestamp + random suffix as member to ensure uniqueness
                member = f"{timestamp}:{i}"
                entries[member] = timestamp

            if entries:
                await self.redis_client.zadd(key, entries)

                # Set TTL to window_seconds + buffer to auto-cleanup old keys
                ttl_seconds = window_seconds + 3600  # Add 1 hour buffer
                await self.redis_client.expire(key, ttl_seconds)

            logger.debug(
                f"Recorded {amount} usage(s) for {subject_id}/{metric}",
                extra={
                    "subject_id": subject_id,
                    "metric": metric,
                    "amount": amount,
                    "window_seconds": window_seconds,
                },
            )

        except Exception as e:
            logger.error(f"Error recording usage: {e}", exc_info=True)
            # Don't raise - we don't want to block operations due to tracking failures

    async def reset_rate_limit(self, subject_id: str, metric: str) -> None:
        """Reset rate limit for subject/metric (admin operation).

        Removes all entries from the rate limit window.

        Args:
            subject_id: Subject identifier
            metric: Operation metric name
        """
        try:
            key = f"{self.key_prefix}:{subject_id}:{metric}"
            await self.redis_client.delete(key)

            logger.info(
                f"Reset rate limit for {subject_id}/{metric}",
                extra={"subject_id": subject_id, "metric": metric},
            )

        except Exception as e:
            logger.error(f"Error resetting rate limit: {e}", exc_info=True)
            raise

    async def get_current_usage(
        self,
        subject_id: str,
        metric: str,
    ) -> dict[str, int]:
        """Get current usage statistics for a subject/metric.

        Args:
            subject_id: Subject identifier
            metric: Operation metric name

        Returns:
            Dictionary with usage statistics
        """
        try:
            # Get rate limit configuration
            limit, window_seconds = await self.policy_loader.get_rate_limit(metric)

            if limit == 0 or window_seconds == 0:
                return {
                    "current_count": 0,
                    "limit": 0,
                    "window_seconds": 0,
                    "remaining": 0,
                }

            # Get current count
            key = f"{self.key_prefix}:{subject_id}:{metric}"
            current_time = time.time()
            window_start = current_time - window_seconds

            # Clean up old entries and count current ones
            pipeline = await self.redis_client.create_transaction_pipeline()
            pipeline.zremrangebyscore(key, "-inf", window_start)
            pipeline.zcard(key)

            results = await pipeline.execute()
            current_count = results[1] if len(results) > 1 else 0

            return {
                "current_count": current_count,
                "limit": limit,
                "window_seconds": window_seconds,
                "remaining": max(0, limit - current_count),
            }

        except Exception as e:
            logger.error(f"Error getting usage statistics: {e}", exc_info=True)
            return {
                "current_count": 0,
                "limit": 0,
                "window_seconds": 0,
                "remaining": 0,
            }
