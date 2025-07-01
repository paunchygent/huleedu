"""
Redis SET operations for HuleEdu microservices.

Provides SET-based operations for cache key tracking and management.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("redis-set-ops")


class RedisSetOperations:
    """Redis SET operations for cache key tracking and management."""

    def __init__(self, client: aioredis.Redis, client_id: str) -> None:
        self.client = client
        self.client_id = client_id

    async def sadd(self, key: str, *members: str) -> int:
        """
        Add one or more members to a Redis SET.

        Args:
            key: Redis key for the SET
            members: One or more string values to add

        Returns:
            Number of elements added to the SET
        """
        try:
            result = self.client.sadd(key, *members)
            added_count = await result if hasattr(result, '__await__') else result
            logger.debug(
                f"Redis SADD by '{self.client_id}': key='{key}' added={added_count} members",
            )
            return int(added_count)
        except Exception as e:
            logger.error(
                f"Error in Redis SADD operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def smembers(self, key: str) -> set[str]:
        """
        Get all members of a Redis SET.

        Args:
            key: Redis key for the SET

        Returns:
            Set of string values
        """
        try:
            result = self.client.smembers(key)
            members = await result if hasattr(result, '__await__') else result
            logger.debug(
                f"Redis SMEMBERS by '{self.client_id}': key='{key}' "
                f"returned {len(members)} members",
            )
            return set(members)
        except Exception as e:
            logger.error(
                f"Error in Redis SMEMBERS operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    async def srem(self, key: str, *members: str) -> int:
        """
        Remove one or more members from a Redis SET.

        Args:
            key: Redis key for the SET
            members: One or more string values to remove

        Returns:
            Number of elements removed from the SET
        """
        try:
            result = self.client.srem(key, *members)
            removed_count = await result if hasattr(result, '__await__') else result
            logger.debug(
                f"Redis SREM by '{self.client_id}': key='{key}' removed={removed_count} members",
            )
            return int(removed_count)
        except Exception as e:
            logger.error(
                f"Error in Redis SREM operation by '{self.client_id}' for key '{key}': {e}",
                exc_info=True,
            )
            raise

    @asynccontextmanager
    async def pipeline(self):
        """
        Create a Redis pipeline for atomic operations.

        Usage:
            async with set_ops.pipeline() as pipe:
                await pipe.setex(key1, ttl, value1)
                await pipe.sadd(key2, member)
                results = await pipe.execute()
        """
        pipe = self.client.pipeline()
        try:
            yield pipe
        finally:
            pass
