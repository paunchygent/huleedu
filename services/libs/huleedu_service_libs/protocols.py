"""
Shared protocol definitions for huleedu_service_libs.

This module contains protocol interfaces that are used across multiple services
to ensure type safety and consistency. These protocols define the contracts for
shared infrastructure components provided by huleedu_service_libs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Protocol

import redis.client


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
    Extended protocol for atomic Redis operations using WATCH/MULTI/EXEC pattern
    and Redis Pub/Sub for real-time communication.

    Extends basic RedisClientProtocol for services needing atomic transactions
    and/or pub/sub capabilities. Services using only idempotency can continue
    using RedisClientProtocol.
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

    async def publish(self, channel: str, message: str) -> int:
        """
        Publish a message to a Redis channel. This is a "fire-and-forget"
        operation that sends the message to all active subscribers of the channel.

        Args:
            channel: The channel to publish to (e.g., "ws:user_123").
            message: The message payload to publish, typically a JSON string.

        Returns:
            The integer number of clients that received the message.
        """
        ...

    def subscribe(self, channel: str) -> AsyncGenerator[redis.client.PubSub, None]:
        """
        Subscribe to a Redis channel within an async context manager, ensuring
        proper connection and disconnection.

        Args:
            channel: The channel to subscribe to.

        Yields:
            A PubSub object that can be iterated over to listen for messages.
        """
        ...

    def get_user_channel(self, user_id: str) -> str:
        """Generate standardized user-specific channel name."""
        ...

    async def publish_user_notification(self, user_id: str, event_type: str, data: dict) -> int:
        """Convenience method to publish structured notifications to user-specific channels."""
        ...
