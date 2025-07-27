"""
Redis client wrapper for HuleEdu microservices.

Provides minimal Redis operations needed for event idempotency patterns.
Follows the same lifecycle management pattern as KafkaBus.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis
import redis.client
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from huleedu_service_libs.redis_pubsub import RedisPubSub

logger = create_service_logger("redis-client")  # Use structured logger

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")


class RedisClient(AtomicRedisClientProtocol):
    """HuleEdu Redis client with lifecycle management for idempotency operations."""

    def __init__(self, *, client_id: str, redis_url: str = REDIS_URL):
        self.redis_url = redis_url
        self.client_id = client_id  # Store client_id for logging
        self.client = aioredis.from_url(
            self.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self._started = False
        self._pubsub: RedisPubSub | None = None

    async def start(self) -> None:
        """Initialize Redis connection with health verification."""
        if not self._started:
            try:
                await self.client.ping()
                self._started = True
                self._pubsub = RedisPubSub(self.client, self.client_id)
                logger.info(f"Redis client '{self.client_id}' connected to {self.redis_url}")
            except RedisConnectionError as e:
                logger.error(f"Redis client '{self.client_id}' failed to connect: {e}")
                raise
            except Exception as e:
                logger.error(f"Redis client '{self.client_id}' startup error: {e}")
                raise

    async def stop(self) -> None:
        """Clean shutdown of Redis connection."""
        if self._started:
            try:
                await self.client.aclose()
                self._started = False
                logger.info(f"Redis client '{self.client_id}' disconnected")
            except Exception as e:
                logger.error(
                    f"Error stopping Redis client '{self.client_id}': {e}",
                    exc_info=True,
                )

    async def set_if_not_exists(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Atomic SET if NOT EXISTS operation for idempotency.

        Args:
            key: Redis key for idempotency check
            value: Value to store (typically event processing marker)
            ttl_seconds: Optional TTL in seconds (recommended: 24-48 hours)

        Returns:
            True if key was set (first time processing), False if key already exists
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.set(key, value, ex=ttl_seconds, nx=True)
            success = bool(result)
            logger.debug(
                f"Redis SETNX by '{self.client_id}': key='{key}' "
                f"ttl={ttl_seconds}s result={'SET' if success else 'EXISTS'}",
            )
            return success
        except RedisTimeoutError:
            logger.error(f"Timeout on Redis operation by '{self.client_id}' for key '{key}'")
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def delete_key(self, key: str) -> int:
        """
        Delete a key from Redis.

        Args:
            key: Redis key to delete

        Returns:
            Number of keys deleted (0 or 1)
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            deleted_count = await self.client.delete(key)
            logger.debug(
                f"Redis DELETE by '{self.client_id}': key='{key}' deleted={deleted_count}",
            )
            return int(deleted_count)
        except Exception as e:
            logger.error(
                f"Error deleting Redis key '{key}' by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise

    async def get(self, key: str) -> str | None:
        """
        Get string value from Redis.

        Args:
            key: Redis key to retrieve

        Returns:
            String value if key exists, None otherwise
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            value = await self.client.get(key)
            logger.debug(
                f"Redis GET by '{self.client_id}': key='{key}' "
                f"result={'HIT' if value is not None else 'MISS'}",
            )
            return str(value) if value is not None else None
        except RedisTimeoutError:
            logger.error(f"Timeout on Redis GET operation by '{self.client_id}' for key '{key}'")
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis GET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

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
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.setex(key, ttl_seconds, value)
            success = bool(result)
            logger.debug(
                f"Redis SETEX by '{self.client_id}': key='{key}' "
                f"ttl={ttl_seconds}s result={'SUCCESS' if success else 'FAILED'}",
            )
            return success
        except RedisTimeoutError:
            logger.error(f"Timeout on Redis SETEX operation by '{self.client_id}' for key '{key}'")
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis SETEX operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def create_transaction_pipeline(self, *watch_keys: str):
        """
        Create a new pipeline for atomic transactions with optional key watching.
        This is the modern Redis transaction pattern.

        Args:
            watch_keys: Optional keys to watch for changes

        Returns:
            A Redis pipeline configured for transactions

        Example:
            pipeline = await redis.create_transaction_pipeline('key1', 'key2')
            pipeline.multi()
            pipeline.spop('key1')  # No await - queued
            pipeline.hset('key2', 'field', 'value')  # No await - queued
            results = await pipeline.execute()
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            # Create a new pipeline for this transaction
            pipeline = self.client.pipeline(transaction=True)

            # Watch keys if provided
            if watch_keys:
                await pipeline.watch(*watch_keys)
                logger.debug(
                    f"Redis transaction pipeline created by '{self.client_id}' "
                    f"watching keys: {watch_keys}"
                )
            else:
                logger.debug(
                    f"Redis transaction pipeline created by '{self.client_id}' "
                    f"without watching keys"
                )

            return pipeline
        except Exception as e:
            logger.error(
                f"Error creating transaction pipeline by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise

    async def scan_pattern(self, pattern: str) -> list[str]:
        """
        Scan for keys matching a pattern.

        Args:
            pattern: Redis pattern to match (e.g., "bcs:essay_state:batch_001:*")

        Returns:
            List of keys matching the pattern
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            keys = []
            cursor = 0
            while True:
                cursor, batch_keys = await self.client.scan(cursor=cursor, match=pattern, count=100)
                keys.extend(batch_keys)
                if cursor == 0:  # Scan complete
                    break

            logger.debug(
                f"Redis SCAN by '{self.client_id}': pattern='{pattern}' found={len(keys)} keys",
            )
            return keys
        except RedisTimeoutError:
            logger.error(
                f"Timeout on Redis SCAN operation by '{self.client_id}' for pattern '{pattern}'",
            )
            raise
        except Exception as e:
            logger.error(
                f"Error in Redis SCAN operation by '{self.client_id}' for pattern '{pattern}': {e}",
                exc_info=True,
            )
            raise

    # Set operations for slot management
    async def sadd(self, key: str, *members: str) -> int:
        """
        Add members to a Redis set.

        Args:
            key: Redis key for the set
            members: One or more string values to add

        Returns:
            Number of elements added to the set
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.sadd(key, *members)
            added_count = int(result)
            logger.debug(
                f"Redis SADD by '{self.client_id}': key='{key}' added={added_count} members",
            )
            return added_count
        except Exception as e:
            logger.error(
                f"Error in Redis SADD operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def spop(self, key: str) -> str | None:
        """
        Remove and return a random member from a Redis set.

        Args:
            key: Redis key for the set

        Returns:
            Random member from the set, or None if set is empty
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.spop(key)
            logger.debug(
                f"Redis SPOP by '{self.client_id}': key='{key}' "
                f"result={'REMOVED' if result else 'EMPTY'}",
            )
            return str(result) if result is not None else None
        except Exception as e:
            logger.error(
                f"Error in Redis SPOP operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def scard(self, key: str) -> int:
        """
        Get the number of members in a Redis set.

        Args:
            key: Redis key for the set

        Returns:
            Number of members in the set
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.scard(key)
            count = int(result)
            logger.debug(f"Redis SCARD by '{self.client_id}': key='{key}' count={count}")
            return count
        except Exception as e:
            logger.error(
                f"Error in Redis SCARD operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def smembers(self, key: str) -> set[str]:
        """
        Get all members of a Redis set.

        Args:
            key: Redis key for the set

        Returns:
            Set of all members
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.smembers(key)
            members = set(result) if result else set()
            logger.debug(
                f"Redis SMEMBERS by '{self.client_id}': key='{key}' count={len(members)}",
            )
            return members
        except Exception as e:
            logger.error(
                f"Error in Redis SMEMBERS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

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
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.hset(key, field, value)
            is_new = int(result) == 1
            logger.debug(
                f"Redis HSET by '{self.client_id}': key='{key}' field='{field}' "
                f"result={'NEW' if is_new else 'UPDATED'}",
            )
            return int(result)
        except Exception as e:
            logger.error(
                f"Error in Redis HSET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hget(self, key: str, field: str) -> str | None:
        """
        Get field value from a Redis hash.

        Args:
            key: Redis key for the hash
            field: Field name

        Returns:
            Field value or None if field doesn't exist
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.hget(key, field)
            value = result.decode() if isinstance(result, bytes) else result
            logger.debug(
                f"Redis HGET by '{self.client_id}': key='{key}' field='{field}' "
                f"result={'HIT' if value is not None else 'MISS'}",
            )
            return str(value) if value is not None else None
        except Exception as e:
            logger.error(
                f"Error in Redis HGET operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hlen(self, key: str) -> int:
        """
        Get the number of fields in a Redis hash.

        Args:
            key: Redis key for the hash

        Returns:
            Number of fields in the hash
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.hlen(key)
            count = int(result)
            logger.debug(f"Redis HLEN by '{self.client_id}': key='{key}' count={count}")
            return count
        except Exception as e:
            logger.error(
                f"Error in Redis HLEN operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hgetall(self, key: str) -> dict[str, str]:
        """
        Get all fields and values from a Redis hash.

        Args:
            key: Redis key for the hash

        Returns:
            Dictionary of all field-value pairs
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.hgetall(key)
            data = dict(result) if result else {}
            logger.debug(
                f"Redis HGETALL by '{self.client_id}': key='{key}' returned {len(data)} fields",
            )
            return data
        except Exception as e:
            logger.error(
                f"Error in Redis HGETALL operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def hexists(self, key: str, field: str) -> bool:
        """
        Check if field exists in a Redis hash.

        Args:
            key: Redis key for the hash
            field: Field name to check

        Returns:
            True if field exists in the hash, False otherwise
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.hexists(key, field)
            exists = bool(result)
            logger.debug(
                f"Redis HEXISTS by '{self.client_id}': key='{key}' field='{field}' exists={exists}",
            )
            return exists
        except Exception as e:
            logger.error(
                f"Error in Redis HEXISTS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """
        Set TTL for a Redis key.

        Args:
            key: Redis key
            ttl_seconds: TTL in seconds

        Returns:
            True if TTL was set successfully
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.expire(key, ttl_seconds)
            success = bool(result)
            logger.debug(
                f"Redis EXPIRE by '{self.client_id}': key='{key}' ttl={ttl_seconds}s "
                f"result={'SUCCESS' if success else 'KEY_NOT_FOUND'}",
            )
            return success
        except Exception as e:
            logger.error(
                f"Error in Redis EXPIRE operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

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
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.rpush(key, *values)
            length = int(result)
            logger.debug(
                f"Redis RPUSH by '{self.client_id}': key='{key}' "
                f"added={len(values)} values, new_length={length}",
            )
            return length
        except Exception as e:
            logger.error(
                f"Error in Redis RPUSH operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

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
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.lrange(key, start, stop)
            elements = result or []
            logger.debug(
                f"Redis LRANGE by '{self.client_id}': key='{key}' "
                f"range=[{start}:{stop}] returned {len(elements)} elements",
            )
            return elements
        except Exception as e:
            logger.error(
                f"Error in Redis LRANGE operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def llen(self, key: str) -> int:
        """
        Get the length of a Redis list.

        Args:
            key: Redis key for the list

        Returns:
            Length of the list
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.llen(key)
            length = int(result)
            logger.debug(f"Redis LLEN by '{self.client_id}': key='{key}' length={length}")
            return length
        except Exception as e:
            logger.error(
                f"Error in Redis LLEN operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def lpush(self, key: str, *values: str) -> int:
        """
        Prepend values to a Redis list.

        Args:
            key: Redis key for the list
            values: One or more values to prepend

        Returns:
            Length of the list after operation
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.lpush(key, *values)
            length = int(result)
            logger.debug(
                f"Redis LPUSH by '{self.client_id}': key='{key}' "
                f"added={len(values)} values, new_length={length}",
            )
            return length
        except Exception as e:
            logger.error(
                f"Error in Redis LPUSH operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def blpop(self, keys: list[str], timeout: float = 0) -> tuple[str, str] | None:
        """
        Remove and get the first element in a list, or block until one is available.

        Args:
            keys: List of keys to check
            timeout: Maximum time in seconds to block. 0 means block indefinitely.

        Returns:
            Tuple of (key, value) if an element was popped, None if timeout
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.blpop(keys, timeout=timeout)
            if result:
                key, value = result
                logger.debug(
                    f"Redis BLPOP by '{self.client_id}': keys={keys} "
                    f"timeout={timeout}s got value from key='{key}'",
                )
                return (key, value)
            else:
                logger.debug(
                    f"Redis BLPOP by '{self.client_id}': keys={keys} timeout={timeout}s timed out",
                )
                return None
        except Exception as e:
            logger.error(
                f"Error in Redis BLPOP operation by '{self.client_id}' for keys {keys}: {e}",
                exc_info=True,
            )
            raise

    async def ttl(self, key: str) -> int:
        """
        Get TTL of a Redis key in seconds.

        Args:
            key: Redis key

        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if key has no TTL
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.ttl(key)
            ttl_seconds = int(result)
            logger.debug(f"Redis TTL by '{self.client_id}': key='{key}' ttl={ttl_seconds}s")
            return ttl_seconds
        except Exception as e:
            logger.error(
                f"Error in Redis TTL operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def exists(self, key: str) -> int:
        """
        Check if key exists in Redis.

        Args:
            key: Redis key to check

        Returns:
            1 if key exists, 0 otherwise
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")

        try:
            result = await self.client.exists(key)
            exists_count = int(result)
            logger.debug(
                f"Redis EXISTS by '{self.client_id}': key='{key}' exists={exists_count > 0}",
            )
            return exists_count
        except Exception as e:
            logger.error(
                f"Error in Redis EXISTS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    # Missing AtomicRedisClientProtocol methods implementation
    async def ping(self) -> bool:
        """
        Health check method to verify Redis connectivity.

        Returns:
            True if Redis connection is healthy
        """
        if not self._started:
            logger.warning(f"Redis client '{self.client_id}' not started. Attempting to start.")
            await self.start()
            if not self._started:
                logger.error(
                    f"Cannot perform operation, Redis client '{self.client_id}' is not running.",
                )
                return False

        try:
            result = await self.client.ping()
            is_healthy = bool(result)
            logger.debug(f"Redis PING by '{self.client_id}': result={is_healthy}")
            return is_healthy
        except Exception as e:
            logger.error(
                f"Error in Redis PING operation by '{self.client_id}': {e}",
                exc_info=True,
            )
            return False

    async def publish(self, channel: str, message: str) -> int:
        """
        Publish a message to a Redis channel.

        Args:
            channel: The channel to publish to
            message: The message to publish

        Returns:
            Number of subscribers that received the message
        """
        if not self._pubsub:
            raise RuntimeError(
                f"Redis client '{self.client_id}' PubSub not initialized. "
                f"Ensure start() was called."
            )
        return await self._pubsub.publish(channel, message)

    async def subscribe(self, channel: str) -> AsyncGenerator[redis.client.PubSub, None]:
        """
        Subscribe to a Redis channel within an async context manager.

        Args:
            channel: The channel to subscribe to

        Returns:
            Async generator that yields a PubSub object
        """
        if not self._pubsub:
            raise RuntimeError(
                f"Redis client '{self.client_id}' PubSub not initialized. "
                f"Ensure start() was called."
            )
        async with self._pubsub.subscribe(channel) as pubsub:
            yield pubsub

    def get_user_channel(self, user_id: str) -> str:
        """
        Generate standardized user-specific channel name.

        Args:
            user_id: The user's ID

        Returns:
            Standardized channel name for the user
        """
        if not self._pubsub:
            raise RuntimeError(
                f"Redis client '{self.client_id}' PubSub not initialized. "
                f"Ensure start() was called."
            )
        return self._pubsub.get_user_channel(user_id)

    async def publish_user_notification(
        self, user_id: str, event_type: str, data: dict[str, Any]
    ) -> int:
        """
        Convenience method to publish structured notifications to user-specific channels.

        Args:
            user_id: The target user's ID
            event_type: The type of event
            data: The event data payload

        Returns:
            Number of subscribers that received the notification
        """
        if not self._pubsub:
            raise RuntimeError(
                f"Redis client '{self.client_id}' PubSub not initialized. "
                f"Ensure start() was called."
            )
        return await self._pubsub.publish_user_notification(user_id, event_type, data)

    # Lua script operations for atomic complex operations
    async def register_script(self, script_body: str) -> str:
        """
        Load a Lua script into Redis and return its SHA1 hash.

        Args:
            script_body: The Lua script as a string

        Returns:
            The SHA1 hash of the script for use with EVALSHA

        Raises:
            RuntimeError: If Redis client is not running
            Exception: If script registration fails
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")
        
        try:
            # The script_load method returns the SHA1 hash of the script
            sha = await self.client.script_load(script_body)
            logger.debug(f"Lua script registered by '{self.client_id}' with SHA: {sha}")
            return sha
        except Exception as e:
            logger.error(
                f"Error registering Lua script by '{self.client_id}': {e}",
                exc_info=True,
            )
            raise

    async def execute_script(self, sha: str, keys: list[str], args: list[Any]) -> Any:
        """
        Execute a pre-loaded Lua script by its SHA hash.

        Args:
            sha: The SHA1 hash of the script
            keys: A list of key names used by the script
            args: A list of argument values used by the script

        Returns:
            The result of the script execution

        Raises:
            RuntimeError: If Redis client is not running
            Exception: If script execution fails
        """
        if not self._started:
            raise RuntimeError(f"Redis client '{self.client_id}' is not running.")
        
        try:
            result = await self.client.evalsha(sha, len(keys), *keys, *args)
            logger.debug(
                f"Executed Lua script by '{self.client_id}' with SHA: {sha}, "
                f"keys: {keys}, args: {args}"
            )
            return result
        except Exception as e:
            logger.error(
                f"Error executing Lua script by '{self.client_id}' with SHA: {sha}: {e}",
                exc_info=True,
            )
            raise

    # PubSub management
    @property
    def pubsub(self) -> RedisPubSub | None:
        """Get the PubSub instance for this client."""
        return self._pubsub
