"""Fake queue bus for unit testing - in-memory implementation."""

from typing import List, Optional
from uuid import UUID

from services.llm_provider_service.queue_models import QueuedRequest, QueueStats


class FakeQueueBus:
    """In-memory queue for unit testing."""

    def __init__(self, max_size: int = 1000) -> None:
        """Initialize fake queue.

        Args:
            max_size: Maximum queue size for testing capacity limits
        """
        self.enqueued_requests: List[QueuedRequest] = []
        self.processed_requests: List[UUID] = []
        self.failed_requests: List[UUID] = []
        self.max_size = max_size

    async def enqueue(self, request: QueuedRequest) -> bool:
        """Enqueue a request.

        Args:
            request: Request to enqueue

        Returns:
            True if enqueued successfully, False if queue is full
        """
        if len(self.enqueued_requests) >= self.max_size:
            return False

        self.enqueued_requests.append(request)
        return True

    async def dequeue(self) -> Optional[QueuedRequest]:
        """Dequeue the next request.

        Returns:
            Next request or None if queue is empty
        """
        if self.enqueued_requests:
            return self.enqueued_requests.pop(0)
        return None

    async def get_queue_stats(self) -> QueueStats:
        """Get current queue statistics.

        Returns:
            Queue statistics for testing
        """
        current_size = len(self.enqueued_requests)
        usage_percent = (current_size / self.max_size) * 100

        return QueueStats(
            current_size=current_size,
            max_size=self.max_size,
            memory_usage_mb=float(current_size * 0.1),  # Approximate 0.1MB per request
            max_memory_mb=float(self.max_size * 0.1),
            usage_percent=usage_percent,
            estimated_wait_minutes=max(1, current_size // 10),  # Rough estimate
            is_accepting_requests=current_size < self.max_size,
        )

    async def mark_processed(self, queue_id: UUID) -> None:
        """Mark a request as processed.

        Args:
            queue_id: ID of processed request
        """
        self.processed_requests.append(queue_id)

    async def mark_failed(self, queue_id: UUID) -> None:
        """Mark a request as failed.

        Args:
            queue_id: ID of failed request
        """
        self.failed_requests.append(queue_id)

    def clear(self) -> None:
        """Clear all queues for test isolation."""
        self.enqueued_requests.clear()
        self.processed_requests.clear()
        self.failed_requests.clear()

    def get_request_by_id(self, queue_id: UUID) -> Optional[QueuedRequest]:
        """Find a request by ID.

        Args:
            queue_id: Request ID to find

        Returns:
            Request if found, None otherwise
        """
        for request in self.enqueued_requests:
            if request.queue_id == queue_id:
                return request
        return None

    @property
    def size(self) -> int:
        """Get current queue size."""
        return len(self.enqueued_requests)

    @property
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self.enqueued_requests) == 0

    @property
    def is_full(self) -> bool:
        """Check if queue is at capacity."""
        return len(self.enqueued_requests) >= self.max_size
