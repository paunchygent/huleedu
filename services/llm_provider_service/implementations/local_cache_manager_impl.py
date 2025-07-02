"""In-memory LRU cache manager implementation for LLM responses."""

import time
from collections import OrderedDict
from typing import Any, Dict

from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import Settings
from services.llm_provider_service.protocols import LLMCacheRepositoryProtocol

logger = create_service_logger("llm_provider_service.local_cache")


class LocalCacheManagerImpl(LLMCacheRepositoryProtocol):
    """In-memory LRU cache implementation for LLM response fallback."""

    def __init__(self, settings: Settings):
        """Initialize local cache manager.

        Args:
            settings: Service settings
        """
        self.settings = settings
        self.max_size_mb = getattr(settings, "LOCAL_CACHE_SIZE_MB", 100)
        self.default_ttl = getattr(settings, "LOCAL_CACHE_TTL_SECONDS", 300)

        # Calculate max entries based on estimated average response size (20KB)
        estimated_response_size_kb = 20
        self.max_entries = (self.max_size_mb * 1024) // estimated_response_size_kb

        # LRU cache implementation using OrderedDict
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._access_times: Dict[str, float] = {}

        logger.info(
            f"Local cache initialized: max_size={self.max_size_mb}MB, "
            f"max_entries≈{self.max_entries}, default_ttl={self.default_ttl}s"
        )

    async def get(self, key: str) -> Dict[str, Any] | None:
        """Get value from local cache.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached response dict or None if not found/expired
        """
        if key not in self._cache:
            logger.debug(f"Local cache miss for key: {key}")
            return None

        # Check TTL
        entry = self._cache[key]
        stored_at = entry.get("_cached_at", 0)
        ttl = entry.get("_cache_ttl", self.default_ttl)

        if time.time() - stored_at > ttl:
            # Expired entry
            logger.debug(f"Local cache entry expired for key: {key}")
            await self._remove_entry(key)
            return None

        # Move to end (mark as recently used)
        self._cache.move_to_end(key)
        self._access_times[key] = time.time()

        logger.debug(f"Local cache hit for key: {key}")

        # Return copy without cache metadata
        result = {k: v for k, v in entry.items() if not k.startswith("_")}
        return result

    async def set(self, key: str, value: Dict[str, Any], ttl: int) -> None:
        """Set value in local cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        current_time = time.time()

        # Add cache metadata
        cache_entry = {
            **value,
            "_cached_at": current_time,
            "_cache_ttl": ttl,
        }

        # Remove existing entry if present
        if key in self._cache:
            await self._remove_entry(key)

        # Check if we need to evict entries
        await self._ensure_capacity()

        # Add new entry
        self._cache[key] = cache_entry
        self._access_times[key] = current_time

        logger.debug(f"Local cache set for key: {key}, TTL: {ttl}s")

    async def delete(self, key: str) -> None:
        """Delete value from local cache.

        Args:
            key: Cache key to delete
        """
        if key in self._cache:
            await self._remove_entry(key)
            logger.debug(f"Local cache deleted key: {key}")

    async def clear(self) -> None:
        """Clear all cached values."""
        entry_count = len(self._cache)
        self._cache.clear()
        self._access_times.clear()
        logger.info(f"Local cache cleared: {entry_count} entries removed")

    async def get_stats(self) -> Dict[str, Any]:
        """Get local cache statistics."""
        total_entries = len(self._cache)

        # Estimate memory usage (rough calculation)
        estimated_size_kb = total_entries * 20  # 20KB average per entry

        # Count expired entries
        current_time = time.time()
        expired_count = 0
        for entry in self._cache.values():
            stored_at = entry.get("_cached_at", 0)
            ttl = entry.get("_cache_ttl", self.default_ttl)
            if current_time - stored_at > ttl:
                expired_count += 1

        return {
            "backend": "local_memory",
            "total_keys": total_entries,
            "expired_keys": expired_count,
            "max_entries": self.max_entries,
            "estimated_size_kb": estimated_size_kb,
            "max_size_mb": self.max_size_mb,
            "default_ttl": self.default_ttl,
        }

    async def _remove_entry(self, key: str) -> None:
        """Remove entry and cleanup metadata."""
        self._cache.pop(key, None)
        self._access_times.pop(key, None)

    async def _ensure_capacity(self) -> None:
        """Ensure cache doesn't exceed capacity by evicting LRU entries."""
        while len(self._cache) >= self.max_entries:
            # Remove least recently used (first item in OrderedDict)
            lru_key = next(iter(self._cache))
            logger.debug(f"Evicting LRU entry: {lru_key}")
            await self._remove_entry(lru_key)

    async def cleanup_expired(self) -> int:
        """Remove expired entries and return count removed."""
        current_time = time.time()
        expired_keys = []

        for key, entry in self._cache.items():
            stored_at = entry.get("_cached_at", 0)
            ttl = entry.get("_cache_ttl", self.default_ttl)
            if current_time - stored_at > ttl:
                expired_keys.append(key)

        for key in expired_keys:
            await self._remove_entry(key)

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired local cache entries")

        return len(expired_keys)
