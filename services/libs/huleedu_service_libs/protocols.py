"""
Shared protocol definitions for huleedu_service_libs.

This module contains protocol interfaces that are used across multiple services
to ensure type safety and consistency. These protocols define the contracts for
shared infrastructure components provided by huleedu_service_libs.
"""

from __future__ import annotations

from typing import Any, Protocol


class RedisClientProtocol(Protocol):
    """Protocol for Redis client operations for idempotency patterns."""

    async def set_if_not_exists(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Atomic SET if NOT EXISTS operation for idempotency.

        Args:
            key: Redis key to set
            value: Value to store (will be serialized)
            ttl_seconds: Optional TTL in seconds (None for no expiration)

        Returns:
            True if key was set (first time processing), False if key already exists
        """
        ...

    async def delete_key(self, key: str) -> int:
        """
        Delete a key from Redis.

        Args:
            key: Redis key to delete

        Returns:
            Number of keys deleted (0 or 1)
        """
        ...
