"""
PostgreSQL implementation of the OutboxRepositoryProtocol.

This module provides a generic, reusable repository for managing outbox events
in PostgreSQL. It handles all database operations for the outbox pattern.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from huleedu_service_libs.logging_utils import create_service_logger

from .models import EventOutbox
from .monitoring import OutboxMetrics
from .protocols import OutboxEvent

logger = create_service_logger("outbox_repository")


class OutboxEventImpl:
    """
    Implementation of the OutboxEvent protocol wrapping the SQLAlchemy model.

    This class provides a clean interface for working with outbox events
    without exposing SQLAlchemy-specific details.
    """

    def __init__(self, db_event: EventOutbox) -> None:
        """Initialize with a SQLAlchemy EventOutbox instance."""
        self._db_event = db_event

    @property
    def id(self) -> UUID:
        """Unique identifier for the outbox event."""
        return self._db_event.id

    @property
    def aggregate_id(self) -> str:
        """ID of the aggregate this event relates to."""
        return self._db_event.aggregate_id

    @property
    def aggregate_type(self) -> str:
        """Type of aggregate."""
        return self._db_event.aggregate_type

    @property
    def event_type(self) -> str:
        """Type of the event."""
        return self._db_event.event_type

    @property
    def event_data(self) -> dict[str, Any]:
        """The event payload as a dictionary."""
        return self._db_event.event_data

    @property
    def event_key(self) -> str | None:
        """Optional key for Kafka partitioning."""
        return self._db_event.event_key

    @property
    def created_at(self) -> datetime:
        """Timestamp when the event was created."""
        return self._db_event.created_at

    @property
    def published_at(self) -> datetime | None:
        """Timestamp when the event was successfully published."""
        return self._db_event.published_at

    @property
    def retry_count(self) -> int:
        """Number of publication retry attempts."""
        return self._db_event.retry_count

    @property
    def last_error(self) -> str | None:
        """Last error message if publication failed."""
        return self._db_event.last_error


class PostgreSQLOutboxRepository:
    """
    PostgreSQL implementation of the OutboxRepositoryProtocol.

    This repository manages all database operations for the transactional outbox
    pattern, ensuring atomic transactions and reliable event storage.
    """

    def __init__(self, engine: AsyncEngine, service_name: str = "unknown", enable_metrics: bool = True) -> None:
        """
        Initialize the repository with a database engine.

        Args:
            engine: SQLAlchemy async engine for database connections
            service_name: Name of the service for metric labels
            enable_metrics: Whether to enable Prometheus metrics collection
        """
        self._session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
        # Initialize metrics if enabled
        self.metrics = OutboxMetrics(service_name) if enable_metrics else None
        logger.info("Initialized PostgreSQL outbox repository")

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

        Args:
            aggregate_id: ID of the aggregate this event relates to
            aggregate_type: Type of aggregate (e.g., 'batch', 'file_upload')
            event_type: Type of the event
            event_data: The event payload (must be JSON-serializable)
            topic: Kafka topic name for publishing
            event_key: Optional key for Kafka partitioning
            session: Optional AsyncSession to use for transaction sharing.
                    If None, repository will create its own session.

        Returns:
            UUID: The ID of the created outbox event
        """
        # Store topic in event_data for the relay worker
        event_data_with_topic = event_data.copy()
        event_data_with_topic["topic"] = topic

        if session is not None:
            # Use provided session for transaction sharing
            return await self._add_event_with_session(
                session, aggregate_id, aggregate_type, event_type, 
                event_data_with_topic, event_key
            )
        else:
            # Create own session (existing behavior)
            async with self._session_factory() as session:
                event_id = await self._add_event_with_session(
                    session, aggregate_id, aggregate_type, event_type,
                    event_data_with_topic, event_key
                )
                await session.commit()
                return event_id

    async def _add_event_with_session(
        self,
        session: AsyncSession,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data_with_topic: dict[str, Any],
        event_key: str | None,
    ) -> UUID:
        """
        Helper method to add event using a specific session.
        
        Args:
            session: The database session to use
            aggregate_id: ID of the aggregate this event relates to
            aggregate_type: Type of aggregate
            event_type: Type of the event
            event_data_with_topic: Event data with topic included
            event_key: Optional key for Kafka partitioning
            
        Returns:
            UUID: The ID of the created outbox event
        """
        outbox_event = EventOutbox(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            event_data=event_data_with_topic,
            event_key=event_key,
        )
        session.add(outbox_event)
        await session.flush()  # Get the ID but don't commit yet

        logger.info(
            "Added event to outbox",
            extra={
                "outbox_id": str(outbox_event.id),
                "aggregate_id": aggregate_id,
                "aggregate_type": aggregate_type,
                "event_type": event_type,
            },
        )
        
        # Record metrics if enabled
        if self.metrics:
            self.metrics.increment_events_added(event_type)
        
        return outbox_event.id

    async def get_unpublished_events(self, limit: int = 100) -> list[OutboxEvent]:
        """
        Retrieve unpublished events from the outbox, ordered by creation time.

        Args:
            limit: Maximum number of events to retrieve

        Returns:
            List of unpublished outbox events, oldest first
        """
        async with self._session_factory() as session:
            stmt = (
                select(EventOutbox)
                .where(EventOutbox.published_at.is_(None))
                .order_by(EventOutbox.created_at)
                .limit(limit)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            logger.info(
                f"Retrieved {len(events)} unpublished events from outbox",
                extra={"event_count": len(events), "limit": limit},
            )

            return [OutboxEventImpl(event) for event in events]

    async def mark_event_published(self, event_id: UUID) -> None:
        """
        Mark an event as successfully published.

        Args:
            event_id: The ID of the event to mark as published
        """
        async with self._session_factory() as session:
            stmt = (
                update(EventOutbox)
                .where(EventOutbox.id == event_id)
                .values(published_at=datetime.now(UTC))
            )
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount == 0:
                logger.warning(
                    "No outbox event found to mark as published",
                    extra={"event_id": str(event_id)},
                )
            else:
                logger.info(
                    "Marked outbox event as published",
                    extra={"event_id": str(event_id)},
                )

    async def mark_event_failed(self, event_id: UUID, error: str) -> None:
        """
        Mark an event as permanently failed (exceeded max retries).

        Args:
            event_id: The ID of the event to mark as failed
            error: The final error message
        """
        # Truncate error message if too long
        max_error_length = 1000
        if len(error) > max_error_length:
            error = error[:max_error_length]

        async with self._session_factory() as session:
            stmt = (
                update(EventOutbox)
                .where(EventOutbox.id == event_id)
                .values(last_error=error)
            )
            result = await session.execute(stmt)
            await session.commit()

            if result.rowcount > 0:
                logger.warning(
                    "Marked outbox event as permanently failed",
                    extra={"event_id": str(event_id), "error": error},
                )

    async def increment_retry_count(self, event_id: UUID, error: str) -> None:
        """
        Increment the retry count for a failed event and record the error.

        Args:
            event_id: The ID of the event that failed
            error: The error message from the failed attempt
        """
        # Truncate error message if too long
        max_error_length = 1000
        if len(error) > max_error_length:
            error = error[:max_error_length]

        async with self._session_factory() as session:
            # Get current retry count
            stmt = select(EventOutbox).where(EventOutbox.id == event_id)
            result = await session.execute(stmt)
            event = result.scalar_one_or_none()

            if event:
                new_retry_count = event.retry_count + 1
                update_stmt = (
                    update(EventOutbox)
                    .where(EventOutbox.id == event_id)
                    .values(retry_count=new_retry_count, last_error=error)
                )
                await session.execute(update_stmt)
                await session.commit()

                logger.info(
                    "Incremented retry count for outbox event",
                    extra={
                        "event_id": str(event_id),
                        "new_retry_count": new_retry_count,
                        "error": error,
                    },
                )
            else:
                logger.warning(
                    "Outbox event not found for retry increment",
                    extra={"event_id": str(event_id)},
                )

    async def get_event_by_id(self, event_id: UUID) -> OutboxEvent | None:
        """
        Retrieve a specific event by its ID.

        Args:
            event_id: The ID of the event to retrieve

        Returns:
            The outbox event if found, None otherwise
        """
        async with self._session_factory() as session:
            stmt = select(EventOutbox).where(EventOutbox.id == event_id)
            result = await session.execute(stmt)
            event = result.scalar_one_or_none()

            if event:
                return OutboxEventImpl(event)
            return None