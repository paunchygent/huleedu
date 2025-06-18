"""
Shared protocol definitions for huleedu_service_libs.

This module contains protocol interfaces that are used across multiple services
to ensure type safety and consistency. These protocols define the contracts for
shared infrastructure components provided by huleedu_service_libs.
"""

from __future__ import annotations

from typing import Any, Protocol


class RedisClientProtocol(Protocol):
    """Protocol for Redis client operations for idempotency patterns and basic data operations."""

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

    async def get(self, key: str) -> str | None:
        """
        Get string value from Redis.

        Args:
            key: Redis key to retrieve

        Returns:
            String value if key exists, None otherwise
        """
        ...

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """
        Set string value with TTL.

        Args:
            key: Redis key to set
            ttl_seconds: TTL in seconds
            value: String value to store

        Returns:
            True if operation succeeded
        """
        ...


class AtomicRedisClientProtocol(RedisClientProtocol, Protocol):
    """
    Extended protocol for atomic Redis operations using WATCH/MULTI/EXEC pattern.

    Extends basic RedisClientProtocol for services needing atomic transactions.
    Services using only idempotency can continue using RedisClientProtocol.
    """

    async def watch(self, *keys: str) -> bool:
        """
        Watch one or more keys for changes during transaction.

        Args:
            keys: Redis keys to watch

        Returns:
            True if WATCH command succeeded
        """
        ...

    async def multi(self) -> bool:
        """
        Start a Redis transaction (MULTI).

        Returns:
            True if MULTI command succeeded
        """
        ...

    async def exec(self) -> list[Any] | None:
        """
        Execute a Redis transaction (EXEC).

        Returns:
            List of results if transaction succeeded, None if transaction was discarded
        """
        ...

    async def unwatch(self) -> bool:
        """
        Unwatch all keys (UNWATCH).

        Returns:
            True if UNWATCH command succeeded
        """
        ...

    async def scan_pattern(self, pattern: str) -> list[str]:
        """
        Scan for keys matching a pattern.

        Args:
            pattern: Redis pattern to match (e.g., "bcs:essay_state:batch_001:*")

        Returns:
            List of keys matching the pattern
        """
        ...
