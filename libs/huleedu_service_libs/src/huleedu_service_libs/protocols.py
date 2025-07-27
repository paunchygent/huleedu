"""
Shared protocol definitions for huleedu_service_libs.

This module contains protocol interfaces that are used across multiple services
to ensure type safety and consistency. These protocols define the contracts for
shared infrastructure components provided by huleedu_service_libs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Protocol, TypeVar

import redis.client
from common_core.events.envelope import EventEnvelope
from pydantic import BaseModel

T_EventPayload = TypeVar("T_EventPayload", bound=BaseModel)

__all__ = [
    "RedisClientProtocol",
    "AtomicRedisClientProtocol",
    "KafkaPublisherProtocol",
    "T_EventPayload",
]


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
        pass

    async def delete_key(self, key: str) -> int:
        """
        Delete a key from Redis.

        Args:
            key: Redis key to delete

        Returns:
            Number of keys deleted (0 or 1)
        """
        pass

    async def get(self, key: str) -> str | None:
        """
        Get string value from Redis.

        Args:
            key: Redis key to retrieve

        Returns:
            String value if key exists, None otherwise
        """
        pass

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
        pass

    async def ping(self) -> bool:
        """
        Health check method to verify Redis connectivity.

        Returns:
            True if Redis connection is healthy
        """
        pass


class AtomicRedisClientProtocol(RedisClientProtocol, Protocol):
    """
    Extended protocol for atomic Redis operations using WATCH/MULTI/EXEC pattern
    and Redis Pub/Sub for real-time communication.

    Extends basic RedisClientProtocol for services needing atomic transactions
    and/or pub/sub capabilities. Services using only idempotency can continue
    using RedisClientProtocol.
    """

    async def create_transaction_pipeline(self, *watch_keys: str):
        """
        Create a new pipeline for atomic transactions with optional key watching.
        This is the modern Redis transaction pattern.

        Args:
            watch_keys: Optional keys to watch for changes

        Returns:
            A Redis pipeline configured for transactions
        """
        pass

    async def scan_pattern(self, pattern: str) -> list[str]:
        """
        Scan for keys matching a pattern.

        Args:
            pattern: Redis pattern to match (e.g., "bcs:essay_state:batch_001:*")

        Returns:
            List of keys matching the pattern
        """
        pass

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
        pass

    def subscribe(self, channel: str) -> AsyncGenerator[redis.client.PubSub, None]:
        """
        Subscribe to a Redis channel within an async context manager, ensuring
        proper connection and disconnection.

        Args:
            channel: The channel to subscribe to.

        Yields:
            A PubSub object that can be iterated over to listen for messages.
        """
        pass

    def get_user_channel(self, user_id: str) -> str:
        """Generate standardized user-specific channel name."""
        pass

    async def publish_user_notification(self, user_id: str, event_type: str, data: dict) -> int:
        """Convenience method to publish structured notifications to user-specific channels."""
        pass

    # Set operations for atomic batch coordination
    async def sadd(self, key: str, *members: str) -> int:
        """
        Add one or more members to a Redis set.

        Args:
            key: Redis key for the set
            members: One or more string values to add

        Returns:
            Number of elements added to the set
        """
        pass

    async def spop(self, key: str) -> str | None:
        """
        Remove and return a random member from a Redis set.

        Args:
            key: Redis key for the set

        Returns:
            Random member from the set, or None if set is empty
        """
        pass

    async def scard(self, key: str) -> int:
        """
        Get the number of members in a Redis set.

        Args:
            key: Redis key for the set

        Returns:
            Number of members in the set
        """
        pass

    async def smembers(self, key: str) -> set[str]:
        """
        Get all members of a Redis set.

        Args:
            key: Redis key for the set

        Returns:
            Set of all members
        """
        pass

    # Hash operations for metadata storage
    async def hset(self, key: str, field: str, value: str) -> int:
        """
        Set field in a Redis hash.

        Args:
            key: Redis key for the hash
            field: Field name
            value: Field value

        Returns:
            1 if field is new, 0 if field was updated
        """
        pass

    async def hget(self, key: str, field: str) -> str | None:
        """
        Get field value from a Redis hash.

        Args:
            key: Redis key for the hash
            field: Field name

        Returns:
            Field value or None if field doesn't exist
        """
        pass

    async def hlen(self, key: str) -> int:
        """
        Get the number of fields in a Redis hash.

        Args:
            key: Redis key for the hash

        Returns:
            Number of fields in the hash
        """
        pass

    async def hgetall(self, key: str) -> dict[str, str]:
        """
        Get all fields and values from a Redis hash.

        Args:
            key: Redis key for the hash

        Returns:
            Dictionary of all field-value pairs
        """
        pass

    async def hexists(self, key: str, field: str) -> bool:
        """
        Check if field exists in a Redis hash.

        Args:
            key: Redis key for the hash
            field: Field name to check

        Returns:
            True if field exists in the hash, False otherwise
        """
        pass

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """
        Set TTL for a Redis key.

        Args:
            key: Redis key
            ttl_seconds: TTL in seconds

        Returns:
            True if TTL was set successfully
        """
        pass

    # List operations for validation failure tracking
    async def rpush(self, key: str, *values: str) -> int:
        """
        Append values to a Redis list.

        Args:
            key: Redis key for the list
            values: One or more values to append

        Returns:
            Length of the list after operation
        """
        pass

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        """
        Get range of elements from a Redis list.

        Args:
            key: Redis key for the list
            start: Start index (0-based)
            stop: Stop index (inclusive, -1 for end)

        Returns:
            List of elements in the specified range
        """
        pass

    async def llen(self, key: str) -> int:
        """
        Get the length of a Redis list.

        Args:
            key: Redis key for the list

        Returns:
            Length of the list
        """
        pass

    async def lpush(self, key: str, *values: str) -> int:
        """
        Prepend values to a Redis list (add to left/head).

        Args:
            key: Redis key for the list
            values: One or more values to prepend

        Returns:
            Length of the list after operation
        """
        pass

    async def blpop(self, keys: list[str], timeout: float) -> tuple[str, str] | None:
        """
        Blocking left pop from Redis lists with timeout.

        Args:
            keys: List of Redis keys to monitor
            timeout: Timeout in seconds (0 for infinite)

        Returns:
            Tuple of (key, value) if item available, None if timeout
        """
        pass

    # Key operations
    async def ttl(self, key: str) -> int:
        """
        Get time to live for a key in seconds.

        Args:
            key: Redis key

        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if no TTL
        """
        pass

    async def exists(self, key: str) -> int:
        """
        Check if a key exists.

        Args:
            key: Redis key to check

        Returns:
            1 if key exists, 0 otherwise
        """
        pass


class KafkaPublisherProtocol(Protocol):
    """
    Protocol for Kafka event publishing with lifecycle management.

    This protocol defines the common interface for both KafkaBus and ResilientKafkaPublisher,
    enabling proper dependency injection with type safety while supporting resilience patterns.
    """

    async def start(self) -> None:
        """Start the Kafka publisher and establish connections."""
        pass

    async def stop(self) -> None:
        """Stop the Kafka publisher and clean up resources."""
        pass

    async def publish(
        self,
        topic: str,
        envelope: "EventEnvelope[T_EventPayload]",
        key: str | None = None,
    ) -> None:
        """
        Publish an event envelope to a Kafka topic.

        Args:
            topic: Kafka topic to publish to
            envelope: Event envelope containing the event data
            key: Optional message key for partitioning

        Raises:
            KafkaError: If publishing fails
            CircuitBreakerError: If circuit breaker is open (for resilient implementations)
        """
        pass
