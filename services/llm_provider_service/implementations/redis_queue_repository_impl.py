"""
Redis-based queue repository implementation.

Uses Redis sorted sets for priority-based queue management and
hashes for request data storage.
"""

from typing import List, Optional
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.redis_client import RedisClient

from common_core import QueueStatus
from services.llm_provider_service.config import Settings
from services.llm_provider_service.protocols import QueueRepositoryProtocol
from services.llm_provider_service.queue_models import QueuedRequest

logger = create_service_logger("llm_provider_service.redis_queue")


class RedisQueueRepositoryImpl(QueueRepositoryProtocol):
    """Redis-based queue repository with sorted sets for priority."""

    def __init__(self, redis_client: RedisClient, settings: Settings):
        self.redis = redis_client
        self.settings = settings
        self.prefix = f"{settings.SERVICE_NAME}:queue"

        # Key patterns
        self.queue_key = f"{self.prefix}:requests"  # Sorted set for ordering
        self.data_key = f"{self.prefix}:data"  # Hash for request data
        self.stats_key = f"{self.prefix}:stats"  # Hash for statistics

    async def add(self, request: QueuedRequest) -> bool:
        """Add request to Redis queue."""
        try:
            # Serialize request
            request_json = request.model_dump_json()
            queue_id_str = str(request.queue_id)

            # Calculate score for sorted set (higher priority = lower score)
            # Format: -priority.timestamp (negative for descending priority)
            timestamp = request.queued_at.timestamp()
            score = -request.priority + (timestamp / 1e10)  # Ensure timestamp doesn't dominate

            # Use pipeline for atomic operations
            pipe = self.redis.client.pipeline()

            # Add to sorted set for ordering
            pipe.zadd(self.queue_key, {queue_id_str: score})

            # Store data in hash
            pipe.hset(self.data_key, queue_id_str, request_json)

            # Set expiration on the data key based on TTL
            ttl_seconds = int(request.ttl.total_seconds())
            data_expire_key = f"{self.data_key}:{queue_id_str}"
            pipe.setex(data_expire_key, ttl_seconds, "1")  # Marker for expiration tracking

            # Execute pipeline
            results = await pipe.execute()

            if all(results):
                logger.info(
                    f"Queued request {queue_id_str} with priority {request.priority}, "
                    f"TTL {ttl_seconds}s"
                )
                return True
            else:
                logger.error(f"Failed to queue request {queue_id_str}: Pipeline failed")
                return False

        except Exception as e:
            logger.error(f"Failed to add request to Redis queue: {e}")
            return False

    async def get_next(self) -> Optional[QueuedRequest]:
        """Get highest priority queued request."""
        try:
            # Get the highest priority item (lowest score)
            items = await self.redis.client.zrange(
                self.queue_key, 0, 0, withscores=False
            )

            if not items:
                return None

            queue_id_str = items[0]

            # Get the request data
            request_json = await self.redis.client.hget(self.data_key, queue_id_str)
            if not request_json:
                # Data missing, remove from queue
                await self.redis.client.zrem(self.queue_key, queue_id_str)
                logger.warning(f"Removed orphaned queue entry: {queue_id_str}")
                return None

            # Parse the request
            request = QueuedRequest.model_validate_json(request_json)

            # Check if expired
            if request.is_expired():
                await self.delete(request.queue_id)
                logger.info(f"Removed expired request: {queue_id_str}")
                # Recursively get next non-expired request
                return await self.get_next()

            # Only return if status is QUEUED
            if request.status == QueueStatus.QUEUED:
                return request

            # If not QUEUED, try next item
            return await self.get_next()

        except Exception as e:
            logger.error(f"Failed to get next request: {e}")
            return None

    async def get_by_id(self, queue_id: UUID) -> Optional[QueuedRequest]:
        """Get specific request by ID."""
        try:
            queue_id_str = str(queue_id)
            request_json = await self.redis.client.hget(self.data_key, queue_id_str)

            if not request_json:
                return None

            request = QueuedRequest.model_validate_json(request_json)

            # Check if expired
            if request.is_expired():
                await self.delete(queue_id)
                return None

            return request

        except Exception as e:
            logger.error(f"Failed to get request {queue_id}: {e}")
            return None

    async def update(self, request: QueuedRequest) -> bool:
        """Update existing request."""
        try:
            queue_id_str = str(request.queue_id)

            # Check if exists
            exists = await self.redis.client.hexists(self.data_key, queue_id_str)
            if not exists:
                logger.warning(f"Cannot update non-existent request: {queue_id_str}")
                return False

            # Update data
            request_json = request.model_dump_json()
            await self.redis.client.hset(self.data_key, queue_id_str, request_json)

            logger.debug(f"Updated request {queue_id_str} with status {request.status}")
            return True

        except Exception as e:
            logger.error(f"Failed to update request {request.queue_id}: {e}")
            return False

    async def delete(self, queue_id: UUID) -> bool:
        """Remove request from queue."""
        try:
            queue_id_str = str(queue_id)

            # Use pipeline for atomic deletion
            pipe = self.redis.client.pipeline()
            pipe.zrem(self.queue_key, queue_id_str)
            pipe.hdel(self.data_key, queue_id_str)
            pipe.delete(f"{self.data_key}:{queue_id_str}")  # Remove expiration marker

            results = await pipe.execute()

            success = any(results)  # At least one operation succeeded
            if success:
                logger.debug(f"Deleted request {queue_id_str}")

            return success

        except Exception as e:
            logger.error(f"Failed to delete request {queue_id}: {e}")
            return False

    async def get_all_queued(self) -> List[QueuedRequest]:
        """Get all QUEUED status requests."""
        try:
            # Get all queue IDs from sorted set
            queue_ids = await self.redis.client.zrange(self.queue_key, 0, -1)

            if not queue_ids:
                return []

            # Get all data in batch
            requests = []
            for queue_id_str in queue_ids:
                request_json = await self.redis.client.hget(self.data_key, queue_id_str)
                if request_json:
                    try:
                        request = QueuedRequest.model_validate_json(request_json)
                        if request.status == QueueStatus.QUEUED and not request.is_expired():
                            requests.append(request)
                    except Exception as e:
                        logger.warning(f"Failed to parse request {queue_id_str}: {e}")

            return requests

        except Exception as e:
            logger.error(f"Failed to get queued requests: {e}")
            return []

    async def count(self) -> int:
        """Get total queue size."""
        try:
            count = await self.redis.client.zcard(self.queue_key)
            return count or 0
        except Exception as e:
            logger.error(f"Failed to get queue count: {e}")
            return 0

    async def get_memory_usage(self) -> int:
        """Get approximate memory usage in bytes."""
        try:
            # Get all queue IDs
            queue_ids = await self.redis.client.hkeys(self.data_key)

            total_bytes = 0
            for queue_id_str in queue_ids:
                request_json = await self.redis.client.hget(self.data_key, queue_id_str)
                if request_json:
                    try:
                        request = QueuedRequest.model_validate_json(request_json)
                        total_bytes += request.size_bytes
                    except Exception:
                        # If we can't parse, estimate from JSON size
                        total_bytes += len(request_json)

            return total_bytes

        except Exception as e:
            logger.error(f"Failed to calculate memory usage: {e}")
            return 0

    async def cleanup_expired(self) -> int:
        """Clean up expired requests from queue."""
        try:
            # Get all queue IDs
            queue_ids = await self.redis.client.zrange(self.queue_key, 0, -1)

            if not queue_ids:
                return 0

            expired_count = 0
            for queue_id_str in queue_ids:
                # Check if expiration marker exists
                marker_exists = await self.redis.client.exists(
                    f"{self.data_key}:{queue_id_str}"
                )

                if not marker_exists:
                    # Marker expired, remove the request
                    request_json = await self.redis.client.hget(self.data_key, queue_id_str)
                    if request_json:
                        try:
                            request = QueuedRequest.model_validate_json(request_json)
                            if request.is_expired():
                                await self.delete(request.queue_id)
                                expired_count += 1
                        except Exception:
                            # Can't parse, remove it
                            await self.delete(UUID(queue_id_str))
                            expired_count += 1

            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired requests")

            return expired_count

        except Exception as e:
            logger.error(f"Failed to cleanup expired requests: {e}")
            return 0