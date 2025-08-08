"""
Protocol definitions for the Transactional Outbox Pattern.

This module defines the behavioral contracts for the outbox pattern components,
enabling clean architecture and testability across all implementing services.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class OutboxEvent(Protocol):
    """
    Protocol representing an event stored in the outbox.

    This protocol defines the minimal interface that outbox events must implement,
    allowing services to work with events in a type-safe manner.
    """

    @property
    def id(self) -> UUID:
        """Unique identifier for the outbox event."""
        ...

    @property
    def aggregate_id(self) -> str:
        """ID of the aggregate this event relates to (e.g., batch_id, file_upload_id)."""
        ...

    @property
    def aggregate_type(self) -> str:
        """Type of aggregate (e.g., 'batch', 'file_upload', 'essay')."""
        ...

    @property
    def event_type(self) -> str:
        """Type of the event (e.g., 'huleedu.els.essay.slot.assigned.v1')."""
        ...

    @property
    def event_data(self) -> dict[str, Any]:
        """The event payload as a JSON-serializable dictionary."""
        ...

    @property
    def event_key(self) -> str | None:
        """Optional key for Kafka partitioning."""
        ...

    @property
    def topic(self) -> str:
        """Kafka topic to publish to."""
        ...

    @property
    def created_at(self) -> datetime:
        """Timestamp when the event was created."""
        ...

    @property
    def published_at(self) -> datetime | None:
        """Timestamp when the event was successfully published (None if unpublished)."""
        ...

    @property
    def retry_count(self) -> int:
        """Number of publication retry attempts."""
        ...

    @property
    def last_error(self) -> str | None:
        """Last error message if publication failed."""
        ...


class OutboxRepositoryProtocol(Protocol):
    """
    Protocol for outbox repository operations.

    This protocol defines the interface for storing and retrieving events
    from the outbox table, ensuring atomic transactions with business logic.
    """

    async def add_event(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data: dict[str, Any],
        topic: str,
        event_key: str | None = None,
        session: AsyncSession | None = None,
    ) -> UUID:
        """
        Add a new event to the outbox within the current transaction.

        This method should be called within the same database transaction
        as the business logic to ensure atomicity.

        Args:
            aggregate_id: ID of the aggregate this event relates to
            aggregate_type: Type of aggregate (e.g., 'batch', 'file_upload')
            event_type: Type of the event (e.g., 'huleedu.els.essay.slot.assigned.v1')
            event_data: The event payload (must be JSON-serializable)
            topic: Kafka topic name for publishing
            event_key: Optional key for Kafka partitioning
            session: Optional AsyncSession to use for transaction sharing.
                    If None, repository will create its own session.

        Returns:
            UUID: The ID of the created outbox event

        Raises:
            Exception: If the event cannot be stored
        """
        ...

    async def get_unpublished_events(self, limit: int = 100) -> list[OutboxEvent]:
        """
        Retrieve unpublished events from the outbox, ordered by creation time.

        This method is used by the relay worker to fetch events for publishing.
        Events that have failed but haven't exceeded max retries are included.

        Args:
            limit: Maximum number of events to retrieve

        Returns:
            List of unpublished outbox events, oldest first
        """
        ...

    async def mark_event_published(self, event_id: UUID) -> None:
        """
        Mark an event as successfully published.

        Args:
            event_id: The ID of the event to mark as published
        """
        ...

    async def mark_event_failed(self, event_id: UUID, error: str) -> None:
        """
        Mark an event as permanently failed (exceeded max retries).

        Args:
            event_id: The ID of the event to mark as failed
            error: The final error message
        """
        ...

    async def increment_retry_count(self, event_id: UUID, error: str) -> None:
        """
        Increment the retry count for a failed event and record the error.

        Args:
            event_id: The ID of the event that failed
            error: The error message from the failed attempt
        """
        ...

    async def get_event_by_id(self, event_id: UUID) -> OutboxEvent | None:
        """
        Retrieve a specific event by its ID.

        Args:
            event_id: The ID of the event to retrieve

        Returns:
            The outbox event if found, None otherwise
        """
        ...


class EventTypeMapperProtocol(Protocol):
    """
    Protocol for mapping event types to Kafka topics.

    Services can implement this protocol to provide custom event-to-topic
    mapping logic when the topic isn't stored directly in the event data.
    """

    def get_topic_for_event(self, event_type: str) -> str:
        """
        Map an event type to its corresponding Kafka topic.

        Args:
            event_type: The event type to map

        Returns:
            The Kafka topic name for this event type

        Raises:
            ValueError: If no mapping exists for the event type
        """
        ...
