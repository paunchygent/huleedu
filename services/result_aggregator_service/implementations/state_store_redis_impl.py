"""Redis implementation of state store."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, cast

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

from services.result_aggregator_service.protocols import StateStoreProtocol

logger = create_service_logger("result_aggregator.state_store")


class StateStoreRedisImpl(StateStoreProtocol):
    """Redis implementation for caching and state management."""

    def __init__(self, redis_client: RedisClientProtocol, cache_ttl: int = 300):
        """Initialize with Redis client."""
        self.redis = redis_client
        self.cache_ttl = cache_ttl

    async def get_batch_state(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get batch processing state from cache."""
        cache_key = f"ras:state:{batch_id}"
        try:
            data = await self.redis.get(cache_key)
            if data:
                # Parse JSON and explicitly cast to expected return type
                parsed_data = json.loads(data)
                return cast(Dict[str, Any], parsed_data)
            return None
        except Exception as e:
            logger.warning(
                "Failed to get batch state",
                batch_id=batch_id,
                error=str(e),
            )
            return None

    async def set_batch_state(self, batch_id: str, state: Dict[str, Any], ttl: int = 300) -> bool:
        """Set batch processing state in cache."""
        cache_key = f"ras:state:{batch_id}"
        try:
            data = json.dumps(state)
            await self.redis.setex(cache_key, ttl, data)
            return True
        except Exception as e:
            logger.warning(
                "Failed to set batch state",
                batch_id=batch_id,
                error=str(e),
            )
            return False

    async def invalidate_batch(self, batch_id: str) -> bool:
        """Invalidate cached batch data."""
        try:
            # Invalidate multiple cache keys:
            # 1. State cache
            # 2. API-level batch status cache
            # 3. User batches cache (pattern match)

            keys_to_delete = [
                f"ras:state:{batch_id}",
                f"api:batch:{batch_id}",
            ]

            # Delete exact keys
            for key in keys_to_delete:
                await self.redis.delete_key(key)

            # Also need to invalidate user batch caches, but we don't know the user_id
            # This is a limitation of the current design
            # TODO: Consider adding user_id to batch events or maintaining a batch->user mapping

            logger.debug("Invalidated batch cache", batch_id=batch_id, keys=keys_to_delete)
            return True
        except Exception as e:
            logger.warning(
                "Failed to invalidate batch cache",
                batch_id=batch_id,
                error=str(e),
            )
            return False

    async def record_processing(self, event_id: str, ttl: int = 86400) -> bool:
        """Record event processing for idempotency."""
        key = f"ras:processed:{event_id}"
        try:
            # Use SET NX (set if not exists) for atomic operation
            result = await self.redis.set_if_not_exists(key, "1", ttl)
            return result
        except Exception as e:
            logger.error(
                "Failed to record processing",
                event_id=event_id,
                error=str(e),
            )
            # Fail open - allow processing to continue
            return True
