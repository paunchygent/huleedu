"""Resilient cache manager combining Redis and local cache for LLM responses."""

import hashlib
from typing import Any, Dict

from huleedu_service_libs.logging_utils import create_service_logger
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from common_core.observability_enums import CacheOperation
from services.llm_provider_service.config import Settings
from services.llm_provider_service.exceptions import CacheConnectionError
from services.llm_provider_service.implementations.local_cache_manager_impl import (
    LocalCacheManagerImpl,
)
from services.llm_provider_service.protocols import (
    LLMCacheManagerProtocol,
    LLMCacheRepositoryProtocol,
)

logger = create_service_logger("llm_provider_service.resilient_cache")


class ResilientCacheManagerImpl(LLMCacheManagerProtocol):
    """Resilient cache manager with Redis primary and local fallback."""

    def __init__(
        self,
        redis_cache: LLMCacheRepositoryProtocol,
        local_cache: LocalCacheManagerImpl,
        settings: Settings,
    ):
        """Initialize resilient cache manager.

        Args:
            redis_cache: Primary Redis cache implementation
            local_cache: Fallback local cache implementation
            settings: Service settings
        """
        self.redis_cache = redis_cache
        self.local_cache = local_cache
        self.settings = settings
        self.cache_prefix = f"{settings.SERVICE_NAME}:cache:"

        # Track Redis availability
        self._redis_available = True
        self._redis_failure_count = 0
        self._max_redis_failures = 3

    async def get_cached_response(self, cache_key: str) -> Dict[str, Any] | None:
        """Get cached LLM response with Redis primary, local fallback.

        Args:
            cache_key: Cache key for the response

        Returns:
            Cached response dict or None if not found
        """
        if not self.settings.LLM_CACHE_ENABLED:
            return None

        # Try Redis first (if available)
        if self._redis_available:
            try:
                result = await self._get_from_redis(cache_key)
                if result is not None:
                    logger.debug(
                        "Cache operation successful",
                        extra={
                            "operation": CacheOperation.GET,
                            "backend": "redis",
                            "cache_key": cache_key,
                            "result": "hit",
                        },
                    )
                    # Also populate local cache for future fallback
                    await self._set_local_cache_async(cache_key, result)
                    return result
                # Reset failure count on successful Redis operation
                self._redis_failure_count = 0
            except (RedisConnectionError, RedisTimeoutError, CacheConnectionError) as e:
                logger.warning(
                    "Redis cache failed, falling back to local cache",
                    extra={
                        "operation": CacheOperation.GET,
                        "backend": "redis",
                        "cache_key": cache_key,
                        "error": str(e),
                    },
                )
                await self._handle_redis_failure()

        # Fallback to local cache
        result = await self.local_cache.get(cache_key)
        if result is not None:
            logger.debug(
                "Cache operation successful",
                extra={
                    "operation": CacheOperation.GET,
                    "backend": "local",
                    "cache_key": cache_key,
                    "result": "hit",
                },
            )
            return result

        logger.debug(
            "Cache miss on both backends",
            extra={"operation": CacheOperation.GET, "cache_key": cache_key, "result": "miss"},
        )
        return None

    async def cache_response(
        self, cache_key: str, response: Dict[str, Any], ttl: int = 3600
    ) -> None:
        """Cache LLM response in both Redis and local cache.

        Args:
            cache_key: Cache key for the response
            response: Response to cache
            ttl: Time to live in seconds
        """
        if not self.settings.LLM_CACHE_ENABLED:
            return

        # Always cache locally for fast access
        try:
            await self.local_cache.set(cache_key, response, ttl)
            logger.debug(
                "Cache operation successful",
                extra={
                    "operation": CacheOperation.SET,
                    "backend": "local",
                    "cache_key": cache_key,
                    "ttl": ttl,
                },
            )
        except Exception as e:
            logger.error(
                "Local cache operation failed",
                extra={
                    "operation": CacheOperation.SET,
                    "backend": "local",
                    "cache_key": cache_key,
                    "error": str(e),
                },
            )

        # Try Redis if available
        if self._redis_available:
            try:
                await self._set_redis_cache(cache_key, response, ttl)
                logger.debug(
                    "Cache operation successful",
                    extra={
                        "operation": CacheOperation.SET,
                        "backend": "redis",
                        "cache_key": cache_key,
                        "ttl": ttl,
                    },
                )
                # Reset failure count on successful Redis operation
                self._redis_failure_count = 0
            except (RedisConnectionError, RedisTimeoutError, CacheConnectionError) as e:
                logger.warning(
                    "Redis cache operation failed, continuing with local only",
                    extra={
                        "operation": CacheOperation.SET,
                        "backend": "redis",
                        "cache_key": cache_key,
                        "error": str(e),
                    },
                )
                await self._handle_redis_failure()

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

    async def is_cache_healthy(self) -> Dict[str, Any]:
        """Check cache health status for monitoring."""
        return {
            "redis_available": self._redis_available,
            "local_cache_available": True,  # Local cache is always available
            "cache_mode": "degraded" if not self._redis_available else "healthy",
            "redis_failure_count": self._redis_failure_count,
        }

    async def _get_from_redis(self, cache_key: str) -> Dict[str, Any] | None:
        """Get from Redis cache with proper key prefix."""
        full_key = f"{self.cache_prefix}{cache_key}"
        cached_data = await self.redis_cache.get(full_key)

        if cached_data:
            # Remove cache metadata before returning
            result = {k: v for k, v in cached_data.items() if not k.startswith("_")}
            return result

        return None

    async def _set_redis_cache(self, cache_key: str, response: Dict[str, Any], ttl: int) -> None:
        """Set Redis cache with proper key prefix."""
        full_key = f"{self.cache_prefix}{cache_key}"
        await self.redis_cache.set(full_key, response, ttl)

    async def _set_local_cache_async(self, cache_key: str, response: Dict[str, Any]) -> None:
        """Asynchronously populate local cache with Redis hit."""
        try:
            # Use shorter TTL for local cache of Redis hits
            local_ttl = min(300, self.settings.LLM_CACHE_TTL // 2)
            await self.local_cache.set(cache_key, response, local_ttl)
        except Exception as e:
            logger.debug(f"Failed to populate local cache for key {cache_key}: {e}")

    async def _handle_redis_failure(self) -> None:
        """Handle Redis failure with circuit breaker logic."""
        self._redis_failure_count += 1

        if self._redis_failure_count >= self._max_redis_failures:
            if self._redis_available:
                logger.warning(
                    f"Redis marked as unavailable after {self._redis_failure_count} failures. "
                    "Switching to local cache only mode for cost protection."
                )
                self._redis_available = False
