"""Redis-based cache manager implementation for LLM responses."""

import hashlib
import json
from typing import Any, Dict

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from services.llm_provider_service.config import Settings
from services.llm_provider_service.protocols import LLMCacheManagerProtocol

logger = create_service_logger("llm_provider_service.cache_manager")


class RedisCacheManagerImpl(LLMCacheManagerProtocol):
    """Redis-based implementation of LLM cache manager."""

    def __init__(self, redis_client: RedisClient, settings: Settings):
        """Initialize cache manager.

        Args:
            redis_client: Redis client instance
            settings: Service settings
        """
        self.redis_client = redis_client
        self.settings = settings
        self.cache_prefix = f"{settings.SERVICE_NAME}:cache:"

    async def get_cached_response(self, cache_key: str) -> Dict[str, Any] | None:
        """Get cached LLM response.

        Args:
            cache_key: Cache key for the response

        Returns:
            Cached response dict or None if not found
        """
        if not self.settings.LLM_CACHE_ENABLED:
            return None

        try:
            full_key = f"{self.cache_prefix}{cache_key}"
            cached_data = await self.redis_client.get(full_key)

            if cached_data:
                logger.debug(f"Cache hit for key: {cache_key}")
                result: Dict[str, Any] = json.loads(cached_data)
                return result

            logger.debug(f"Cache miss for key: {cache_key}")
            return None

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode cached data for key {cache_key}: {e}")
            # Delete corrupted cache entry
            await self.delete(cache_key)
            return None
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache get (key: {cache_key}): {e}")
            # Graceful degradation - return None instead of raising exception
            return None
        except Exception as e:
            logger.error(f"Cache get failed for key {cache_key}: {e}")
            # For non-Redis errors, still return None for graceful degradation
            return None

    async def cache_response(
        self, cache_key: str, response: Dict[str, Any], ttl: int = 3600
    ) -> None:
        """Cache LLM response.

        Args:
            cache_key: Cache key for the response
            response: Response to cache
            ttl: Time to live in seconds
        """
        if not self.settings.LLM_CACHE_ENABLED:
            return

        try:
            full_key = f"{self.cache_prefix}{cache_key}"
            ttl_seconds = ttl or self.settings.LLM_CACHE_TTL

            # Add caching metadata
            cache_data = {
                **response,
                "_cached_at": json.dumps(None),  # Would use datetime.utcnow().isoformat()
                "_cache_ttl": ttl_seconds,
            }

            await self.redis_client.setex(full_key, ttl_seconds, json.dumps(cache_data))
            logger.debug(f"Cached response for key: {cache_key}, TTL: {ttl_seconds}s")

        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache set (key: {cache_key}): {e}")
            # Graceful degradation - continue without caching
        except Exception as e:
            logger.error(f"Cache set failed for key {cache_key}: {e}")
            # Don't raise - caching failure shouldn't break the request

    def generate_cache_key(
        self, provider: str, user_prompt: str, essay_a: str, essay_b: str, **params: Any
    ) -> str:
        """Generate consistent cache key for LLM request.

        Args:
            provider: LLM provider name
            user_prompt: The comparison prompt
            essay_a: First essay to compare
            essay_b: Second essay to compare
            **params: Additional parameters affecting the response

        Returns:
            Cache key string
        """
        # Create a deterministic string from all inputs
        key_parts = [
            f"provider:{provider}",
            f"prompt:{user_prompt}",
            f"essay_a:{essay_a[:100]}",  # First 100 chars to keep key reasonable
            f"essay_b:{essay_b[:100]}",
        ]

        # Add any additional parameters that affect the response
        for param_name, param_value in sorted(params.items()):
            if param_value is not None:
                key_parts.append(f"{param_name}:{param_value}")

        # Create hash of the combined string
        combined = "|".join(key_parts)
        key_hash = hashlib.sha256(combined.encode()).hexdigest()

        return f"llm:{provider}:{key_hash[:16]}"

    async def delete(self, cache_key: str) -> None:
        """Delete value from cache.

        Args:
            cache_key: Cache key to delete
        """
        try:
            full_key = f"{self.cache_prefix}{cache_key}"
            await self.redis_client.delete_key(full_key)
            logger.debug(f"Deleted cache key: {cache_key}")
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache delete (key: {cache_key}): {e}")
            # Graceful degradation - continue without deleting
        except Exception as e:
            logger.error(f"Cache delete failed for key {cache_key}: {e}")

    async def clear(self) -> None:
        """Clear all cached values."""
        try:
            # Get all keys with our prefix
            pattern = f"{self.cache_prefix}*"
            keys = await self.redis_client.scan_pattern(pattern)

            # Delete each key individually since RedisClient doesn't support bulk delete
            deleted_count = 0
            for key in keys:
                await self.redis_client.delete_key(key)
                deleted_count += 1

            logger.info(f"Cleared {deleted_count} cached entries")
        except (RedisConnectionError, RedisTimeoutError) as e:
            logger.warning(f"Redis unavailable for cache clear: {e}")
            # Graceful degradation - continue without clearing
        except Exception as e:
            logger.error(f"Cache clear failed: {e}")
            # Don't raise - graceful degradation

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            # Get all keys with our prefix
            pattern = f"{self.cache_prefix}*"
            keys = await self.redis_client.scan_pattern(pattern)
            total_keys = len(keys)

            # Note: RedisClient doesn't expose info() method, so we can't get memory stats
            # This is a limitation of the abstraction

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
            logger.error(f"Failed to get cache stats: {e}")
            return {
                "total_keys": 0,
                "backend": "redis",
                "cache_enabled": self.settings.LLM_CACHE_ENABLED,
                "default_ttl": self.settings.LLM_CACHE_TTL,
                "error": str(e),
            }

    async def is_cache_healthy(self) -> Dict[str, Any]:
        """Check cache health status for monitoring."""
        try:
            # Simple health check using ping
            await self.redis_client.ping()
            return {
                "redis_available": True,
                "cache_mode": "healthy",
                "backend": "redis",
            }
        except (RedisConnectionError, RedisTimeoutError):
            return {
                "redis_available": False,
                "cache_mode": "degraded",
                "backend": "redis_unavailable",
            }
        except Exception as e:
            return {
                "redis_available": False,
                "cache_mode": "degraded",
                "backend": "redis_error",
                "error": str(e),
            }
