"""Redis cache repository implementation for resilient cache manager."""

import json
from typing import Any, Dict

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from services.llm_provider_service.config import Settings
from services.llm_provider_service.protocols import LLMCacheRepositoryProtocol

logger = create_service_logger("llm_provider_service.redis_cache_repository")


class RedisCacheRepositoryImpl(LLMCacheRepositoryProtocol):
    """Redis cache repository implementation for the resilient cache manager."""

    def __init__(self, redis_client: RedisClient, settings: Settings):
        """Initialize Redis cache repository.

        Args:
            redis_client: Redis client instance
            settings: Service settings
        """
        self.redis_client = redis_client
        self.settings = settings
        self.cache_prefix = f"{settings.SERVICE_NAME}:cache:"

    async def get(self, key: str) -> Dict[str, Any] | None:
        """Get value from Redis cache.

        Args:
            key: Cache key to retrieve (should include prefix)

        Returns:
            Cached response dict or None if not found
        """
        try:
            cached_data = await self.redis_client.get(key)

            if cached_data:
                logger.debug(f"Redis cache hit for key: {key}")
                result: Dict[str, Any] = json.loads(cached_data)
                return result

            logger.debug(f"Redis cache miss for key: {key}")
            return None

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode Redis cached data for key {key}: {e}")
            # Delete corrupted cache entry
            await self.redis_client.delete_key(key)
            return None
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache get (key: {key}): {e}")
            raise  # Re-raise to let resilient manager handle
        except Exception as e:
            logger.error(f"Redis cache get failed for key {key}: {e}")
            return None

    async def set(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        """Set value in Redis cache with TTL.

        Args:
            key: Cache key (should include prefix)
            value: Value to cache
            ttl: Time to live in seconds
        """
        try:
            # Add caching metadata
            cache_data = {
                **value,
                "_cached_at": None,  # Would use datetime.utcnow().isoformat()
                "_cache_ttl": ttl,
            }

            await self.redis_client.setex(key, ttl, json.dumps(cache_data))
            logger.debug(f"Redis cached response for key: {key}, TTL: {ttl}s")

        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache set (key: {key}): {e}")
            raise  # Re-raise to let resilient manager handle
        except Exception as e:
            logger.error(f"Redis cache set failed for key {key}: {e}")
            # Don't raise - caching failure shouldn't break the request

    async def delete(self, key: str) -> None:
        """Delete value from Redis cache.

        Args:
            key: Cache key to delete (should include prefix)
        """
        try:
            await self.redis_client.delete_key(key)
            logger.debug(f"Deleted Redis cache key: {key}")
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache delete (key: {key}): {e}")
            raise  # Re-raise to let resilient manager handle
        except Exception as e:
            logger.error(f"Redis cache delete failed for key {key}: {e}")

    async def clear(self) -> None:
        """Clear all cached values from Redis."""
        try:
            # Get all keys with our prefix
            pattern = f"{self.cache_prefix}*"
            keys = await self.redis_client.scan_pattern(pattern)

            # Delete each key individually since RedisClient doesn't support bulk delete
            deleted_count = 0
            for key in keys:
                await self.redis_client.delete_key(key)
                deleted_count += 1

            logger.info(f"Cleared {deleted_count} Redis cached entries")
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache clear: {e}")
            raise  # Re-raise to let resilient manager handle
        except Exception as e:
            logger.error(f"Redis cache clear failed: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        try:
            # Get all keys with our prefix
            pattern = f"{self.cache_prefix}*"
            keys = await self.redis_client.scan_pattern(pattern)
            total_keys = len(keys)

            return {
                "total_keys": total_keys,
                "backend": "redis",
                "cache_enabled": self.settings.LLM_CACHE_ENABLED,
                "default_ttl": self.settings.LLM_CACHE_TTL,
            }
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache stats: {e}")
            return {
                "total_keys": 0,
                "backend": "redis",
                "cache_enabled": self.settings.LLM_CACHE_ENABLED,
                "default_ttl": self.settings.LLM_CACHE_TTL,
                "status": "redis_unavailable",
            }
        except Exception as e:
            logger.error(f"Failed to get Redis cache stats: {e}")
            return {
                "total_keys": 0,
                "backend": "redis",
                "cache_enabled": self.settings.LLM_CACHE_ENABLED,
                "default_ttl": self.settings.LLM_CACHE_TTL,
                "error": str(e),
            }
