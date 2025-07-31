"""
Redis operations for managing pending content.

Handles content that arrives before batch registration.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Awaitable, Union

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol


async def _ensure_awaitable(result: Union[Awaitable[Any], Any]) -> Any:
    """Ensure a redis result is properly awaited if it's awaitable."""
    if hasattr(result, "__await__"):
        return await result
    return result


class RedisPendingContentOperations:
    """Manages pending content storage and retrieval in Redis."""

    def __init__(self, redis_client: AtomicRedisClientProtocol):
        self._redis = redis_client
        self._logger = create_service_logger("redis_pending_content")

    async def store_pending_content(
        self, batch_id: str, text_storage_id: str, content_metadata: dict[str, Any]
    ) -> None:
        """Store content as pending until batch registration arrives."""
        pending_key = f"pending_content:{batch_id}"

        # Add timestamp and storage ID to metadata
        metadata_with_storage = {
            **content_metadata,
            "text_storage_id": text_storage_id,
            "stored_at": datetime.now(UTC).isoformat(),
        }

        # Store in batch-specific set
        await _ensure_awaitable(self._redis.sadd(pending_key, json.dumps(metadata_with_storage)))

        # Add to global index for monitoring/cleanup (score = timestamp)
        index_key = "pending_content:index"
        score = datetime.now(UTC).timestamp()
        await _ensure_awaitable(self._redis.zadd(index_key, {batch_id: score}))

        # Set TTL (24 hours) to prevent indefinite storage
        await _ensure_awaitable(self._redis.expire(pending_key, 86400))

        self._logger.info(
            f"Stored pending content for batch {batch_id}: {text_storage_id}",
            extra={
                "batch_id": batch_id,
                "text_storage_id": text_storage_id,
                "has_ttl": True,
                "ttl_seconds": 86400,
            },
        )

    async def get_pending_content(self, batch_id: str) -> list[dict[str, Any]]:
        """Retrieve all pending content for a batch."""
        pending_key = f"pending_content:{batch_id}"

        # Get all pending content items
        pending_items = await _ensure_awaitable(self._redis.smembers(pending_key))

        if not pending_items:
            return []

        # Parse JSON metadata
        content_list = []
        for item in pending_items:
            try:
                metadata = json.loads(item)
                content_list.append(metadata)
            except json.JSONDecodeError:
                self._logger.error(
                    "Failed to parse pending content metadata",
                    extra={"batch_id": batch_id, "raw_item": item},
                )

        return content_list

    async def remove_pending_content(self, batch_id: str, text_storage_id: str) -> bool:
        """Remove specific pending content after it's been processed."""
        pending_key = f"pending_content:{batch_id}"

        # Find and remove the specific item
        pending_items = await _ensure_awaitable(self._redis.smembers(pending_key))

        for item in pending_items:
            try:
                metadata = json.loads(item)
                if metadata.get("text_storage_id") == text_storage_id:
                    await _ensure_awaitable(self._redis.srem(pending_key, item))

                    # Clean up index if batch has no more pending content
                    remaining = await _ensure_awaitable(self._redis.scard(pending_key))
                    if remaining == 0:
                        await _ensure_awaitable(self._redis.zrem("pending_content:index", batch_id))
                        await _ensure_awaitable(self._redis.delete(pending_key))

                    self._logger.info(
                        f"Removed pending content {text_storage_id} from batch {batch_id}",
                        extra={
                            "batch_id": batch_id,
                            "text_storage_id": text_storage_id,
                            "remaining_pending": remaining,
                        },
                    )
                    return True
            except json.JSONDecodeError:
                continue

        return False

    async def clear_all_pending(self, batch_id: str) -> int:
        """Clear all pending content for a batch. Returns count of items cleared."""
        pending_key = f"pending_content:{batch_id}"

        # Get count before deletion
        raw_count = await _ensure_awaitable(self._redis.scard(pending_key))
        count: int = int(raw_count) if raw_count is not None else 0

        # Delete the set and remove from index
        await _ensure_awaitable(self._redis.delete(pending_key))
        await _ensure_awaitable(self._redis.zrem("pending_content:index", batch_id))

        if count > 0:
            self._logger.info(
                f"Cleared {count} pending content items for batch {batch_id}",
                extra={"batch_id": batch_id, "cleared_count": count},
            )

        return count
