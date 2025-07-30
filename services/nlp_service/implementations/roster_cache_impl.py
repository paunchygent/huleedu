"""Redis-based implementation of RosterCacheProtocol for NLP Service."""

from __future__ import annotations

import json
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.nlp_service.protocols import RosterCacheProtocol

logger = create_service_logger("nlp_service.roster_cache_impl")


class RedisRosterCache(RosterCacheProtocol):
    """Redis-based cache for class rosters with configurable TTL."""

    def __init__(
        self,
        redis_client: AtomicRedisClientProtocol,
        default_ttl_seconds: int = 3600,
    ) -> None:
        """Initialize Redis roster cache.
        
        Args:
            redis_client: Redis client for cache operations
            default_ttl_seconds: Default TTL for cached rosters (default: 1 hour)
        """
        self.redis_client = redis_client
        self.default_ttl_seconds = default_ttl_seconds
        self._key_prefix = "nlp:roster:"

    def _make_key(self, class_id: str) -> str:
        """Generate Redis key for a class roster.
        
        Args:
            class_id: ID of the class
            
        Returns:
            Redis key string
        """
        return f"{self._key_prefix}{class_id}"

    async def get_roster(self, class_id: str) -> list[dict] | None:
        """Get cached roster if available.
        
        Args:
            class_id: ID of the class
            
        Returns:
            List of student dictionaries if cached, None otherwise
        """
        key = self._make_key(class_id)
        
        try:
            cached_data = await self.redis_client.get(key)
            
            if cached_data is None:
                logger.debug(
                    f"Cache miss for class roster: {class_id}",
                    extra={"class_id": class_id},
                )
                return None
            
            # Parse JSON data
            roster = json.loads(cached_data)
            
            if not isinstance(roster, list):
                logger.warning(
                    f"Invalid cached roster format for class {class_id}, clearing cache",
                    extra={"class_id": class_id},
                )
                await self.redis_client.delete(key)
                return None
            
            logger.debug(
                f"Cache hit for class roster: {class_id} ({len(roster)} students)",
                extra={"class_id": class_id, "student_count": len(roster)},
            )
            
            return roster
            
        except json.JSONDecodeError as e:
            logger.warning(
                f"Failed to parse cached roster for class {class_id}: {e}",
                extra={"class_id": class_id},
            )
            # Clear corrupted cache entry
            await self.redis_client.delete(key)
            return None
            
        except Exception as e:
            logger.error(
                f"Error retrieving roster from cache for class {class_id}: {e}",
                exc_info=True,
                extra={"class_id": class_id},
            )
            # Return None on error to allow fallback to direct API call
            return None

    async def set_roster(
        self,
        class_id: str,
        roster: list[dict],
        ttl_seconds: int = 3600,
    ) -> None:
        """Cache roster with TTL.
        
        Args:
            class_id: ID of the class
            roster: List of student dictionaries to cache
            ttl_seconds: Time to live in seconds (default: 1 hour)
        """
        if ttl_seconds <= 0:
            ttl_seconds = self.default_ttl_seconds
            
        key = self._make_key(class_id)
        
        try:
            # Serialize roster to JSON
            roster_json = json.dumps(roster, ensure_ascii=False, sort_keys=True)
            
            # Store in Redis with TTL
            await self.redis_client.setex(key, ttl_seconds, roster_json)
            
            logger.debug(
                f"Cached roster for class {class_id} with TTL {ttl_seconds}s ({len(roster)} students)",
                extra={
                    "class_id": class_id,
                    "ttl_seconds": ttl_seconds,
                    "student_count": len(roster),
                },
            )
            
        except Exception as e:
            # Log error but don't raise - caching failure shouldn't break the flow
            logger.error(
                f"Failed to cache roster for class {class_id}: {e}",
                exc_info=True,
                extra={"class_id": class_id},
            )

    async def clear_roster(self, class_id: str) -> None:
        """Clear cached roster for a specific class.
        
        Args:
            class_id: ID of the class
        """
        key = self._make_key(class_id)
        
        try:
            result = await self.redis_client.delete(key)
            if result:
                logger.debug(
                    f"Cleared cached roster for class {class_id}",
                    extra={"class_id": class_id},
                )
            else:
                logger.debug(
                    f"No cached roster found for class {class_id}",
                    extra={"class_id": class_id},
                )
        except Exception as e:
            logger.error(
                f"Failed to clear cached roster for class {class_id}: {e}",
                exc_info=True,
                extra={"class_id": class_id},
            )