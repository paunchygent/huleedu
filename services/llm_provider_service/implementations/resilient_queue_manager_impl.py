"""
Resilient queue manager with Redis primary and local fallback.

Provides seamless failover between Redis and local queue implementations
to ensure queue functionality during Redis outages.
"""

import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from common_core import QueueStatus
from huleedu_service_libs.logging_utils import create_service_logger

from services.llm_provider_service.config import Settings
from services.llm_provider_service.implementations.local_queue_manager_impl import (
    LocalQueueManagerImpl,
)
from services.llm_provider_service.implementations.redis_queue_repository_impl import (
    RedisQueueRepositoryImpl,
)
from services.llm_provider_service.protocols import QueueManagerProtocol
from services.llm_provider_service.queue_models import QueuedRequest, QueueStats

logger = create_service_logger("llm_provider_service.resilient_queue")


class ResilientQueueManagerImpl(QueueManagerProtocol):
    """Queue manager with Redis primary and local fallback."""

    def __init__(
        self,
        redis_queue: RedisQueueRepositoryImpl,
        local_queue: LocalQueueManagerImpl,
        settings: Settings,
    ):
        self.redis_queue = redis_queue
        self.local_queue = local_queue
        self.settings = settings

        # Health tracking
        self._redis_healthy = True
        self._redis_failure_count = 0
        self._max_redis_failures = 3
        self._last_redis_check = time.time()
        self._redis_check_interval = 30  # seconds

        # Migration tracking
        self._migrated_to_local: set[UUID] = set()  # Track items migrated to local

    async def _check_redis_health(self, force: bool = False) -> bool:
        """Check if Redis is available."""
        current_time = time.time()

        # Skip check if recently checked (unless forced)
        if not force and current_time - self._last_redis_check < self._redis_check_interval:
            return self._redis_healthy

        try:
            # Simple ping to check connection
            await self.redis_queue.redis.ping()

            # Reset failure count on success
            if self._redis_failure_count > 0:
                logger.info("Redis connection restored")
                self._redis_failure_count = 0

            self._redis_healthy = True
            self._last_redis_check = current_time
            return True

        except Exception as e:
            self._redis_failure_count += 1

            if self._redis_failure_count >= self._max_redis_failures:
                if self._redis_healthy:
                    logger.warning(
                        f"Redis marked unhealthy after {self._redis_failure_count} failures: {e}"
                    )
                self._redis_healthy = False
            else:
                logger.debug(f"Redis health check failed ({self._redis_failure_count}): {e}")

            self._last_redis_check = current_time
            return False

    async def enqueue(self, request: QueuedRequest) -> bool:
        """Enqueue with fallback to local if Redis unavailable."""
        # Calculate size if not set
        if request.size_bytes == 0:
            request.size_bytes = request.calculate_size()

        # Try Redis first if healthy
        if self._redis_healthy and await self._check_redis_health():
            try:
                result = await self.redis_queue.add(request)
                if result:
                    return True
                # Redis full or failed, try local
                logger.info(f"Redis queue full or failed for {request.queue_id}, trying local")
            except Exception as e:
                logger.warning(f"Redis enqueue failed: {e}")
                self._redis_failure_count += 1

        # Fallback to local queue
        logger.info(f"Using local queue for request {request.queue_id}")
        result = await self.local_queue.add(request)

        if result:
            self._migrated_to_local.add(request.queue_id)

        return result

    async def dequeue(self) -> Optional[QueuedRequest]:
        """Get next request from Redis or local."""
        # Try Redis first if healthy
        if self._redis_healthy and await self._check_redis_health():
            try:
                request = await self.redis_queue.get_next()
                if request:
                    return request
            except Exception as e:
                logger.warning(f"Redis dequeue failed: {e}")
                self._redis_failure_count += 1

        # Then try local
        request = await self.local_queue.get_next()
        if request:
            # Mark as migrated so we know to update in local
            self._migrated_to_local.add(request.queue_id)

        return request

    async def remove(self, queue_id: UUID) -> bool:
        """Remove a request from either backend."""
        removed = False

        # Try Redis first if healthy
        if self._redis_healthy and await self._check_redis_health():
            try:
                # Actually DELETE from Redis using the delete method
                removed = await self.redis_queue.delete(queue_id)
                if removed:
                    logger.debug(f"Removed request {queue_id} from Redis queue")
            except Exception as e:
                logger.warning(f"Redis remove failed: {e}")

        # Try local if not removed from Redis or if queue_id is in migrated set
        if not removed or queue_id in self._migrated_to_local:
            try:
                # LocalQueueManager has delete method
                removed = await self.local_queue.delete(queue_id) or removed
                if removed:
                    logger.debug(f"Removed request {queue_id} from local queue")
            except Exception as e:
                logger.warning(f"Local remove failed: {e}")

        # Clean up migration tracking
        if removed and queue_id in self._migrated_to_local:
            self._migrated_to_local.discard(queue_id)

        return removed

    async def get_status(self, queue_id: UUID) -> Optional[QueuedRequest]:
        """Get status from either backend."""
        # Check if we know it's in local
        if queue_id in self._migrated_to_local:
            request = await self.local_queue.get_by_id(queue_id)
            if request:
                return request

        # Check Redis first if healthy
        if self._redis_healthy and await self._check_redis_health():
            try:
                request = await self.redis_queue.get_by_id(queue_id)
                if request:
                    return request
            except Exception as e:
                logger.warning(f"Redis get_status failed: {e}")

        # Then check local
        return await self.local_queue.get_by_id(queue_id)

    async def update_status(
        self,
        queue_id: UUID,
        status: QueueStatus,
        message: Optional[str] = None,
        result_location: Optional[str] = None,
    ) -> bool:
        """Update status in appropriate backend."""
        # Get current request to find which backend
        request = await self.get_status(queue_id)
        if not request:
            logger.warning(f"Cannot update non-existent request: {queue_id}")
            return False

        # Update fields
        request.status = status
        # Note: QueuedRequest doesn't have error_message field
        # Error messages are handled separately in queue status tracking
        if result_location:
            request.result_location = result_location

        if status == QueueStatus.PROCESSING:
            request.processing_started_at = datetime.now(timezone.utc)
        elif status in (QueueStatus.COMPLETED, QueueStatus.FAILED):
            request.completed_at = datetime.now(timezone.utc)

        # Update in local if migrated
        if queue_id in self._migrated_to_local:
            return await self.local_queue.update(request)

        # Try to update in Redis first
        if self._redis_healthy and await self._check_redis_health():
            try:
                if await self.redis_queue.update(request):
                    return True
            except Exception as e:
                logger.warning(f"Redis update failed: {e}")

        # Fallback to local
        result = await self.local_queue.update(request)
        if result:
            self._migrated_to_local.add(queue_id)

        return result

    async def get_queue_stats(self) -> QueueStats:
        """Get combined stats from both backends."""
        redis_count = 0
        redis_memory = 0
        redis_queued = 0

        if self._redis_healthy and await self._check_redis_health():
            try:
                redis_count = await self.redis_queue.count()
                redis_memory = await self.redis_queue.get_memory_usage()
                redis_requests = await self.redis_queue.get_all_queued()
                redis_queued = len(redis_requests)
            except Exception as e:
                logger.warning(f"Failed to get Redis stats: {e}")

        local_count = await self.local_queue.count()
        local_memory = await self.local_queue.get_memory_usage()
        local_requests = await self.local_queue.get_all_queued()
        local_queued = len(local_requests)

        total_count = redis_count + local_count
        total_memory = redis_memory + local_memory
        total_queued = redis_queued + local_queued

        # Calculate usage based on combined metrics
        usage_percent = (total_count / self.settings.QUEUE_MAX_SIZE) * 100
        memory_usage_mb = total_memory / (1024 * 1024)

        # Determine if accepting requests
        local_health = self.local_queue.get_queue_health()
        is_accepting = local_health["is_accepting"]

        return QueueStats(
            current_size=total_count,
            max_size=self.settings.QUEUE_MAX_SIZE,
            memory_usage_mb=memory_usage_mb,
            max_memory_mb=self.settings.QUEUE_MAX_MEMORY_MB,
            usage_percent=usage_percent,
            queued_count=total_queued,
            is_accepting_requests=is_accepting,
            rejection_reason=("Queue at capacity" if not is_accepting else None),
        )

    async def cleanup_expired(self) -> int:
        """Cleanup expired from both backends."""
        total_cleaned = 0

        # Cleanup Redis if healthy
        if self._redis_healthy and await self._check_redis_health():
            try:
                total_cleaned += await self.redis_queue.cleanup_expired()
            except Exception as e:
                logger.warning(f"Redis cleanup failed: {e}")

        # Always cleanup local
        total_cleaned += await self.local_queue.cleanup_expired()

        # Clean up migration tracking for expired items
        if total_cleaned > 0:
            # TODO This is a simple cleanup - in production might want more sophisticated tracking
            current_ids: set[UUID] = set()

            # Get all current IDs
            if self._redis_healthy:
                try:
                    redis_requests = await self.redis_queue.get_all_queued()
                    current_ids.update(r.queue_id for r in redis_requests)
                except Exception:
                    pass

            local_requests = await self.local_queue.get_all_queued()
            current_ids.update(r.queue_id for r in local_requests)

            # Remove IDs no longer in any queue
            self._migrated_to_local = self._migrated_to_local.intersection(current_ids)

        return total_cleaned

    async def get_health_status(self) -> dict:
        """Get detailed health status for monitoring."""
        local_health = self.local_queue.get_queue_health()

        return {
            "redis_healthy": self._redis_healthy,
            "redis_failure_count": self._redis_failure_count,
            "local_queue": local_health,
            "migrated_count": len(self._migrated_to_local),
            "mode": "redis" if self._redis_healthy else "local",
        }
