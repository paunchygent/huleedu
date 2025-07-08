"""
Queue infrastructure protocols for HuleEdu services.

This module contains protocol interfaces for queue-specific Redis operations,
separate from general-purpose Redis protocols. These protocols are designed
for reuse across services that need queue functionality.

Architecture:
- QueueRedisClientProtocol: Redis operations specific to queue implementations
- QueueRedisPipelineProtocol: Pipeline operations for batch queue processing

Usage:
    from huleedu_service_libs.queue_protocols import QueueRedisClientProtocol
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Literal, Optional, Protocol, overload

if TYPE_CHECKING:
    from huleedu_service_libs.queue_models import QueueItem


class QueueRedisClientProtocol(Protocol):
    """
    Protocol for Redis operations specifically needed by queue implementations.

    This protocol is specialized for queue use cases and should not be used
    for general Redis operations. Use RedisClientProtocol or AtomicRedisClientProtocol
    for general-purpose Redis operations.

    Key Features:
    - Sorted set operations for priority queue management
    - Hash operations for structured data storage
    - Pipeline operations for batch processing
    - Lifecycle management for connection handling
    """

    # Lifecycle Management
    async def start(self) -> None:
        """Initialize Redis connection with health verification."""
        ...

    async def stop(self) -> None:
        """Clean shutdown of Redis connection."""
        ...

    async def ping(self) -> bool:
        """Health check method to verify Redis connectivity."""
        ...

    # Sorted Set Operations (for priority queue management)
    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        """
        Add members to sorted set with scores.

        Args:
            key: Redis sorted set key
            mapping: Dictionary of member->score pairs

        Returns:
            Number of elements added
        """
        ...

    @overload
    async def zrange(
        self, key: str, start: int, end: int, *, withscores: Literal[False] = False
    ) -> List[str]:
        """Get range of members from sorted set (strings only)."""
        ...

    @overload
    async def zrange(
        self, key: str, start: int, end: int, *, withscores: Literal[True]
    ) -> List[tuple[str, float]]:
        """Get range of members from sorted set with scores."""
        ...

    async def zrange(
        self, key: str, start: int, end: int, *, withscores: bool = False
    ) -> List[str] | List[tuple[str, float]]:
        """
        Get range of members from sorted set by rank.

        Args:
            key: Redis sorted set key
            start: Start index (0-based)
            end: End index (-1 for end of set)
            withscores: Include scores in results

        Returns:
            List of members or (member, score) tuples
        """
        ...

    async def zrem(self, key: str, *members: str) -> int:
        """
        Remove members from sorted set.

        Args:
            key: Redis sorted set key
            members: Members to remove

        Returns:
            Number of members removed
        """
        ...

    async def zcard(self, key: str) -> int:
        """
        Get cardinality (count) of sorted set.

        Args:
            key: Redis sorted set key

        Returns:
            Number of elements in set
        """
        ...

    # Domain-Specific Queue Operations
    async def get_queue_items(self, queue_key: str, count: int) -> List[str]:
        """
        Get top priority queue item IDs.

        Domain-specific method for retrieving queue items without exposing
        low-level Redis sorted set operations. Provides type safety and
        clear intent for queue operations.

        Args:
            queue_key: Redis queue key (sorted set)
            count: Number of items to retrieve

        Returns:
            List of queue item IDs ordered by priority
        """
        ...

    async def get_queue_items_with_priorities(
        self, queue_key: str, count: int
    ) -> List["QueueItem"]:
        """
        Get top priority queue items with their priority scores.

        Domain-specific method returning structured QueueItem objects
        instead of raw Redis tuples. Provides type safety and domain
        alignment for queue operations requiring priority information.

        Args:
            queue_key: Redis queue key (sorted set)
            count: Number of items to retrieve

        Returns:
            List of QueueItem objects with IDs and priorities
        """
        ...

    # Hash Operations (for data storage)
    async def hset(self, key: str, field: str, value: str) -> int:
        """
        Set field in hash.

        Args:
            key: Redis hash key
            field: Field name
            value: Field value

        Returns:
            1 if field is new, 0 if field was updated
        """
        ...

    async def hget(self, key: str, field: str) -> Optional[str]:
        """
        Get field from hash.

        Args:
            key: Redis hash key
            field: Field name

        Returns:
            Field value or None if not exists
        """
        ...

    async def hdel(self, key: str, *fields: str) -> int:
        """
        Delete fields from hash.

        Args:
            key: Redis hash key
            fields: Field names to delete

        Returns:
            Number of fields deleted
        """
        ...

    async def hmget(self, key: str, *fields: str) -> List[Optional[str]]:
        """
        Get multiple fields from hash.

        Args:
            key: Redis hash key
            fields: Field names to get

        Returns:
            List of field values (None for non-existent fields)
        """
        ...

    async def hexists(self, key: str, field: str) -> bool:
        """
        Check if field exists in hash.

        Args:
            key: Redis hash key
            field: Field name

        Returns:
            True if field exists
        """
        ...

    async def hkeys(self, key: str) -> List[str]:
        """
        Get all field names from hash.

        Args:
            key: Redis hash key

        Returns:
            List of field names
        """
        ...

    async def hgetall(self, key: str) -> dict[str, str]:
        """
        Get all fields and values from hash.

        Args:
            key: Redis hash key

        Returns:
            Dictionary of field->value pairs
        """
        ...

    # Key Operations
    async def exists(self, key: str) -> bool:
        """
        Check if key exists.

        Args:
            key: Redis key

        Returns:
            True if key exists
        """
        ...

    async def delete(self, key: str) -> int:
        """
        Delete key.

        Args:
            key: Redis key

        Returns:
            Number of keys deleted (0 or 1)
        """
        ...

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """
        Set key with expiration.

        Args:
            key: Redis key
            ttl_seconds: TTL in seconds
            value: Key value

        Returns:
            True if operation succeeded
        """
        ...

    # Pipeline Operations for Batch Processing
    def pipeline(self) -> QueueRedisPipelineProtocol:
        """
        Create pipeline for batch operations.

        Returns:
            Pipeline object for queuing operations
        """
        ...


class QueueRedisPipelineProtocol(Protocol):
    """
    Protocol for Redis pipeline operations used by queue implementations.

    Provides batched execution of Redis commands for improved performance
    and atomicity in queue operations. All operations are queued and
    executed atomically when execute() is called.
    """

    # Sorted Set Operations in Pipeline
    def zadd(self, key: str, mapping: dict[str, float]) -> QueueRedisPipelineProtocol:
        """Queue zadd operation in pipeline."""
        ...

    def zrem(self, key: str, *members: str) -> QueueRedisPipelineProtocol:
        """Queue zrem operation in pipeline."""
        ...

    # Hash Operations in Pipeline
    def hset(self, key: str, field: str, value: str) -> QueueRedisPipelineProtocol:
        """Queue hset operation in pipeline."""
        ...

    def hdel(self, key: str, *fields: str) -> QueueRedisPipelineProtocol:
        """Queue hdel operation in pipeline."""
        ...

    # Key Operations in Pipeline
    def delete(self, key: str) -> QueueRedisPipelineProtocol:
        """Queue delete operation in pipeline."""
        ...

    def setex(self, key: str, ttl_seconds: int, value: str) -> QueueRedisPipelineProtocol:
        """Queue setex operation in pipeline."""
        ...

    # Pipeline Execution
    async def execute(self) -> List[Any]:
        """
        Execute all queued operations atomically.

        Returns:
            List of results from each operation
        """
        ...
