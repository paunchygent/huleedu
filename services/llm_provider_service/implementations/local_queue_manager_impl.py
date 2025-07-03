"""
Local in-memory queue implementation with capacity management.

Provides a fallback queue when Redis is unavailable, with strict
capacity limits and no silent eviction of requests.
"""

import asyncio
import heapq
import time
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from common_core import QueueStatus
from services.llm_provider_service.config import Settings
from services.llm_provider_service.protocols import QueueRepositoryProtocol
from services.llm_provider_service.queue_models import QueuedRequest, QueueHealthMetrics

logger = create_service_logger("llm_provider_service.local_queue")


class LocalQueueManagerImpl(QueueRepositoryProtocol):
    """In-memory queue with strict capacity limits and no eviction."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.max_size = settings.QUEUE_MAX_SIZE
        self.max_memory_mb = settings.QUEUE_MAX_MEMORY_MB
        self.high_watermark = settings.QUEUE_HIGH_WATERMARK
        self.low_watermark = settings.QUEUE_LOW_WATERMARK

        # Storage structures
        self._queue: List[Tuple[float, str, QueuedRequest]] = []  # Min heap
        self._data: Dict[str, QueuedRequest] = {}

        # Capacity tracking
        self._memory_bytes = 0
        self._at_capacity = False
        self._last_cleanup = time.time()

        # Thread safety
        self._lock = asyncio.Lock()

    def _calculate_priority_score(self, request: QueuedRequest) -> float:
        """Calculate score for heap ordering (lower score = higher priority)."""
        # Negative priority for max heap behavior in min heap
        # Add timestamp for FIFO within same priority
        timestamp_component = request.queued_at.timestamp() / 1e10
        return -request.priority + timestamp_component

    def _check_capacity(self) -> bool:
        """Check if we're at capacity using watermarks."""
        size_percent = (len(self._data) / self.max_size) * 100 if self.max_size > 0 else 100
        memory_mb = self._memory_bytes / (1024 * 1024)
        memory_percent = (memory_mb / self.max_memory_mb) * 100 if self.max_memory_mb > 0 else 100
        usage_percent = max(size_percent, memory_percent)

        if self._at_capacity:
            # At capacity, wait until we drop below low watermark
            if usage_percent < self.low_watermark * 100:
                self._at_capacity = False
                logger.info(
                    f"Queue capacity recovered: {usage_percent:.1f}% "
                    f"({len(self._data)} items, {memory_mb:.1f}MB)"
                )
        else:
            # Not at capacity, check if we exceed high watermark
            if usage_percent >= self.high_watermark * 100:
                self._at_capacity = True
                logger.warning(
                    f"Queue at capacity: {usage_percent:.1f}% "
                    f"({len(self._data)} items, {memory_mb:.1f}MB)"
                )

        return not self._at_capacity

    async def add(self, request: QueuedRequest) -> bool:
        """Add request if capacity allows."""
        async with self._lock:
            # Periodic cleanup of expired requests
            current_time = time.time()
            if current_time - self._last_cleanup > 60:  # Cleanup every minute
                await self._cleanup_expired_internal()
                self._last_cleanup = current_time

            if not self._check_capacity():
                logger.warning(
                    f"Queue full: {len(self._data)}/{self.max_size} items, "
                    f"{self._memory_bytes/1024/1024:.1f}/{self.max_memory_mb}MB"
                )
                return False

            queue_id_str = str(request.queue_id)

            # Check if already exists
            if queue_id_str in self._data:
                logger.warning(f"Request {queue_id_str} already in queue")
                return False

            # Calculate size if not provided
            if request.size_bytes == 0:
                request.size_bytes = request.calculate_size()

            # Add to storage
            self._data[queue_id_str] = request
            score = self._calculate_priority_score(request)
            heapq.heappush(self._queue, (score, queue_id_str, request))

            # Update memory tracking
            self._memory_bytes += request.size_bytes

            logger.debug(
                f"Added request {queue_id_str} to local queue "
                f"(priority={request.priority}, size={request.size_bytes})"
            )
            return True

    async def get_next(self) -> Optional[QueuedRequest]:
        """Get highest priority request."""
        async with self._lock:
            while self._queue:
                _, queue_id_str, _ = heapq.heappop(self._queue)

                # Check if still in data (might have been deleted)
                if queue_id_str in self._data:
                    request = self._data[queue_id_str]

                    # Check expiration
                    if request.is_expired():
                        await self._delete_internal(request.queue_id)
                        continue

                    # Only return QUEUED requests
                    if request.status == QueueStatus.QUEUED:
                        return request

            return None

    async def get_by_id(self, queue_id: UUID) -> Optional[QueuedRequest]:
        """Get specific request."""
        async with self._lock:
            request = self._data.get(str(queue_id))

            if request and request.is_expired():
                await self._delete_internal(queue_id)
                return None

            return request

    async def update(self, request: QueuedRequest) -> bool:
        """Update existing request."""
        async with self._lock:
            queue_id_str = str(request.queue_id)

            if queue_id_str not in self._data:
                logger.warning(f"Cannot update non-existent request: {queue_id_str}")
                return False

            old_request = self._data[queue_id_str]

            # Update memory tracking
            self._memory_bytes -= old_request.size_bytes
            self._memory_bytes += request.size_bytes

            # Update data
            self._data[queue_id_str] = request

            logger.debug(f"Updated request {queue_id_str} with status {request.status}")
            return True

    async def delete(self, queue_id: UUID) -> bool:
        """Remove request."""
        async with self._lock:
            return await self._delete_internal(queue_id)

    async def _delete_internal(self, queue_id: UUID) -> bool:
        """Internal delete without lock."""
        queue_id_str = str(queue_id)

        if queue_id_str not in self._data:
            return False

        request = self._data.pop(queue_id_str)
        self._memory_bytes -= request.size_bytes

        # Note: Item remains in heap but will be skipped in get_next
        logger.debug(f"Deleted request {queue_id_str} from local queue")
        return True

    async def get_all_queued(self) -> List[QueuedRequest]:
        """Get all QUEUED requests."""
        async with self._lock:
            requests = []
            for request in self._data.values():
                if request.status == QueueStatus.QUEUED and not request.is_expired():
                    requests.append(request)

            # Sort by priority and queued time
            requests.sort(
                key=lambda r: (-r.priority, r.queued_at.timestamp())
            )

            return requests

    async def count(self) -> int:
        """Get queue size."""
        async with self._lock:
            return len(self._data)

    async def get_memory_usage(self) -> int:
        """Get memory usage in bytes."""
        async with self._lock:
            return self._memory_bytes

    async def cleanup_expired(self) -> int:
        """Remove expired requests."""
        async with self._lock:
            return await self._cleanup_expired_internal()

    async def _cleanup_expired_internal(self) -> int:
        """Internal cleanup without lock."""
        expired_ids = []

        for _, request in self._data.items():
            if request.is_expired():
                expired_ids.append(request.queue_id)

        for queue_id in expired_ids:
            await self._delete_internal(queue_id)

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired requests from local queue")

        return len(expired_ids)

    def get_queue_health(self) -> QueueHealthMetrics:
        """Get queue health metrics for monitoring."""
        size_percent = (len(self._data) / self.max_size) * 100 if self.max_size > 0 else 0
        memory_mb = self._memory_bytes / (1024 * 1024)
        memory_percent = (memory_mb / self.max_memory_mb) * 100 if self.max_memory_mb > 0 else 0

        return {
            "type": "local",
            "is_accepting": not self._at_capacity,
            "current_size": len(self._data),
            "max_size": self.max_size,
            "size_percent": round(size_percent, 1),
            "memory_usage_mb": round(memory_mb, 2),
            "max_memory_mb": self.max_memory_mb,
            "memory_percent": round(memory_percent, 1),
            "at_capacity": self._at_capacity,
            "high_watermark": self.high_watermark,
            "low_watermark": self.low_watermark,
        }