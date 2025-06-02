"""Cache manager implementation for LLM response caching."""

from __future__ import annotations

import hashlib
from typing import Any

from config import Settings
from diskcache import Cache
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import CacheProtocol

logger = create_service_logger("cj_assessment_service.cache_manager_impl")


class CacheManagerImpl(CacheProtocol):
    """Implementation of CacheProtocol using diskcache for persistent caching."""

    def __init__(self, settings: Settings) -> None:
        """Initialize cache manager with settings.

        Args:
            settings: Application settings containing cache configuration.
        """
        self.settings = settings

        # Initialize diskcache instance
        cache_dir = getattr(settings, "cache_directory", "cache")
        cache_size_limit = getattr(
            settings, "cache_size_limit_bytes", 100 * 1024 * 1024
        )  # 100MB default

        try:
            self.cache = Cache(cache_dir, size_limit=cache_size_limit)
            logger.info(
                f"Initialized disk cache at '{cache_dir}' with size limit {cache_size_limit} bytes"
            )
        except Exception as e:
            logger.error(f"Failed to initialize cache: {e}")
            raise

    def generate_hash(self, prompt: str) -> str:
        """Generate a hash key for a given prompt.

        Args:
            prompt: The prompt text to hash.

        Returns:
            A hexadecimal hash string that can be used as a cache key.
        """
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def get_from_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve data from cache using the provided key.

        Args:
            cache_key: The cache key to look up.

        Returns:
            The cached data if found, None otherwise.
        """
        try:
            cached_data = self.cache.get(cache_key)
            if cached_data is not None:
                logger.debug(f"Cache hit for key: {cache_key[:16]}...")
                # Type cast since we know this should be a dict[str, Any]
                # based on our caching pattern
                return dict(cached_data) if isinstance(cached_data, dict) else None
            else:
                logger.debug(f"Cache miss for key: {cache_key[:16]}...")
                return None
        except Exception as e:
            logger.warning(f"Error accessing cache for key {cache_key[:16]}...: {e}")
            return None

    def add_to_cache(self, cache_key: str, data: dict[str, Any]) -> None:
        """Add data to cache with the provided key.

        Args:
            cache_key: The key to store the data under.
            data: The data to cache.
        """
        try:
            self.cache.set(cache_key, data)
            logger.debug(f"Cached data for key: {cache_key[:16]}...")
        except Exception as e:
            logger.warning(f"Error adding to cache for key {cache_key[:16]}...: {e}")

    def clear_cache(self) -> None:
        """Clear all cached data."""
        try:
            self.cache.clear()
            logger.info("Cache cleared successfully")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary containing cache statistics.
        """
        try:
            stats = {
                "size": len(self.cache),
                "volume": self.cache.volume(),
                "hits": getattr(self.cache, "stats", {}).get("hits", "unknown"),
                "misses": getattr(self.cache, "stats", {}).get("misses", "unknown"),
            }
            return stats
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")
            return {"error": str(e)}

    def close(self) -> None:
        """Close the cache and release resources."""
        try:
            self.cache.close()
            logger.info("Cache closed successfully")
        except Exception as e:
            logger.warning(f"Error closing cache: {e}")

    def __enter__(self) -> CacheManagerImpl:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type, exc_val: Exception, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
