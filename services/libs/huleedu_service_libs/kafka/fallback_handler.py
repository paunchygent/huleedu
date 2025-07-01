"""
Fallback message handler for Kafka circuit breaker resilience.

This module provides queuing and retry logic for messages that fail to publish
to Kafka due to circuit breaker trips or connection issues.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, TypeVar

from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel

from common_core.events.envelope import EventEnvelope

logger = create_service_logger("fallback_handler")

T_EventPayload = TypeVar("T_EventPayload", bound=BaseModel)


@dataclass
class QueuedMessage:
    """Represents a message queued for retry."""

    topic: str
    envelope: EventEnvelope[T_EventPayload]
    key: Optional[str]
    queued_at: datetime
    retry_count: int = 0


class FallbackMessageHandler:
    """
    Handler for queuing and retrying failed Kafka messages.

    Features:
    - In-memory queue for failed messages
    - Configurable queue size limits
    - Retry logic with attempt tracking
    - Message dropping after max retries
    """

    def __init__(
        self,
        max_queue_size: int = 1000,
        retry_interval: int = 30,
        max_retries: int = 5,
    ):
        """
        Initialize fallback handler.

        Args:
            max_queue_size: Maximum number of messages to queue
            retry_interval: Seconds between retry attempts
            max_retries: Maximum retry attempts per message
        """
        self.max_queue_size = max_queue_size
        self.retry_interval = retry_interval
        self.max_retries = max_retries

        # Use asyncio.Queue for thread-safe operations
        self._queue: asyncio.Queue[QueuedMessage] = asyncio.Queue(maxsize=max_queue_size)

        # Metrics
        self._total_queued = 0
        self._total_dropped = 0
        self._total_processed = 0

    async def queue_message(self, message: QueuedMessage) -> None:
        """
        Queue a message for retry.

        Args:
            message: The message to queue

        Raises:
            Exception: If queue is full and message cannot be queued
        """
        try:
            # Try to add to queue without blocking
            self._queue.put_nowait(message)
            self._total_queued += 1

            logger.debug(
                f"Queued message for retry: topic='{message.topic}', "
                f"event_id={message.envelope.event_id}, "
                f"queue_size={self.queue_size()}"
            )

        except asyncio.QueueFull:
            # Queue is full, drop the message
            self._total_dropped += 1
            logger.error(
                f"Fallback queue is full ({self.max_queue_size}), "
                f"dropping message: topic='{message.topic}', "
                f"event_id={message.envelope.event_id}"
            )
            raise Exception("Fallback queue is full, message dropped")

    async def get_next_message(self) -> Optional[QueuedMessage]:
        """
        Get the next message from the queue.

        Returns:
            The next queued message, or None if queue is empty
        """
        try:
            # Get message without blocking
            message = self._queue.get_nowait()
            self._total_processed += 1

            logger.debug(
                f"Retrieved message from queue: topic='{message.topic}', "
                f"event_id={message.envelope.event_id}, "
                f"retry_count={message.retry_count}"
            )

            return message

        except asyncio.QueueEmpty:
            return None

    def has_queued_messages(self) -> bool:
        """Check if there are messages in the queue."""
        return not self._queue.empty()

    def queue_size(self) -> int:
        """Get current queue size."""
        return self._queue.qsize()

    def get_metrics(self) -> dict:
        """Get handler metrics."""
        return {
            "current_queue_size": self.queue_size(),
            "max_queue_size": self.max_queue_size,
            "total_queued": self._total_queued,
            "total_processed": self._total_processed,
            "total_dropped": self._total_dropped,
            "queue_utilization": self.queue_size() / self.max_queue_size,
        }

    async def clear_queue(self) -> int:
        """
        Clear all messages from the queue.

        Returns:
            Number of messages that were cleared
        """
        cleared_count = 0

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                cleared_count += 1
            except asyncio.QueueEmpty:
                break

        if cleared_count > 0:
            logger.warning(f"Cleared {cleared_count} messages from fallback queue")

        return cleared_count

    def is_message_expired(self, message: QueuedMessage, max_age_seconds: int = 3600) -> bool:
        """
        Check if a message has expired based on queue time.

        Args:
            message: The message to check
            max_age_seconds: Maximum age in seconds (default: 1 hour)

        Returns:
            True if message has expired
        """
        age = datetime.now(timezone.utc) - message.queued_at
        return age.total_seconds() > max_age_seconds

    async def cleanup_expired_messages(self, max_age_seconds: int = 3600) -> int:
        """
        Remove expired messages from the queue.

        Args:
            max_age_seconds: Maximum age in seconds

        Returns:
            Number of expired messages removed
        """
        if self._queue.empty():
            return 0

        # This is a simplified cleanup - in production, you might want
        # a more sophisticated approach that doesn't require recreating the queue
        messages_to_keep = []
        expired_count = 0

        # Process all messages
        while not self._queue.empty():
            try:
                message = self._queue.get_nowait()
                if self.is_message_expired(message, max_age_seconds):
                    expired_count += 1
                    logger.debug(
                        f"Expired message removed: topic='{message.topic}', "
                        f"event_id={message.envelope.event_id}"
                    )
                else:
                    messages_to_keep.append(message)
            except asyncio.QueueEmpty:
                break

        # Re-queue non-expired messages
        for message in messages_to_keep:
            try:
                self._queue.put_nowait(message)
            except asyncio.QueueFull:
                # This shouldn't happen since we're putting back the same number
                logger.error("Queue full during cleanup - this should not happen")
                break

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired messages from fallback queue")

        return expired_count
