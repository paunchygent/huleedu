"""
PostgreSQL implementation of OutboxRepositoryProtocol.

Implements the Transactional Outbox Pattern for reliable event publishing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

if TYPE_CHECKING:
    from services.essay_lifecycle_service.models_db import EventOutbox as EventOutboxDB
    from services.essay_lifecycle_service.protocols import OutboxEvent

from services.essay_lifecycle_service.models_db import EventOutbox as EventOutboxDB
from services.essay_lifecycle_service.protocols import OutboxRepositoryProtocol

logger = create_service_logger("outbox_repository")


class OutboxEventImpl:
    """
    Implementation of OutboxEvent protocol.

    Wraps the SQLAlchemy model to satisfy the protocol interface.
    """

    def __init__(self, db_model: EventOutboxDB) -> None:
        """Initialize from database model."""
        self.id = db_model.id
        self.aggregate_id = db_model.aggregate_id
        self.aggregate_type = db_model.aggregate_type
        self.event_type = db_model.event_type
        self.event_data = db_model.event_data
        self.event_key = db_model.event_key
        self.created_at = db_model.created_at
        self.published_at = db_model.published_at
        self.retry_count = db_model.retry_count
        self.last_error = db_model.last_error


class PostgreSQLOutboxRepository(OutboxRepositoryProtocol):
    """
    PostgreSQL implementation of event outbox repository.

    Provides transactional event storage for reliable publishing.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        """
        Initialize with async engine.

        Args:
            engine: AsyncEngine for database connections
        """
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        logger.info("Initialized PostgreSQL outbox repository")

    async def add_event(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data: dict[str, Any],
        event_key: str | None = None,
    ) -> UUID:
        """
        Add event to outbox within current transaction.

        Args:
            aggregate_id: ID of the aggregate that produced the event
            aggregate_type: Type of aggregate (e.g., "essay", "batch")
            event_type: Full event type name (e.g., "huleedu.els.essay.slot.assigned.v1")
            event_data: Serialized event envelope data
            event_key: Optional Kafka partition key

        Returns:
            UUID of the created outbox entry
        """
        async with self._session_factory() as session:
            try:
                # Create new outbox entry
                outbox_event = EventOutboxDB(
                    aggregate_id=aggregate_id,
                    aggregate_type=aggregate_type,
                    event_type=event_type,
                    event_data=event_data,
                    event_key=event_key,
                )

                session.add(outbox_event)
                await session.commit()

                logger.info(
                    "Added event to outbox",
                    extra={
                        "outbox_id": str(outbox_event.id),
                        "aggregate_id": aggregate_id,
                        "aggregate_type": aggregate_type,
                        "event_type": event_type,
                    },
                )

                return outbox_event.id

            except Exception as e:
                await session.rollback()
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="add_event_to_outbox",
                    message=f"Failed to add event to outbox: {e.__class__.__name__}",
                    external_service="database",
                    correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                    aggregate_id=aggregate_id,
                    event_type=event_type,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def get_unpublished_events(self, limit: int = 100) -> list[OutboxEvent]:
        """
        Retrieve unpublished events for relay.

        Args:
            limit: Maximum number of events to retrieve

        Returns:
            List of unpublished events ordered by creation time
        """
        async with self._session_factory() as session:
            try:
                # Query unpublished events
                stmt = (
                    select(EventOutboxDB)
                    .where(EventOutboxDB.published_at.is_(None))
                    .order_by(EventOutboxDB.created_at)
                    .limit(limit)
                )

                result = await session.execute(stmt)
                db_events = result.scalars().all()

                # Convert to protocol objects
                events: list[OutboxEvent] = [OutboxEventImpl(event) for event in db_events]

                if events:
                    logger.info(
                        f"Retrieved {len(events)} unpublished events from outbox",
                        extra={"event_count": len(events), "limit": limit},
                    )

                return events

            except Exception as e:
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="get_unpublished_events",
                    message=f"Failed to retrieve unpublished events: {e.__class__.__name__}",
                    external_service="database",
                    correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                    limit=limit,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def mark_published(self, event_id: UUID) -> None:
        """
        Mark event as successfully published.

        Args:
            event_id: ID of the outbox event to mark as published
        """
        async with self._session_factory() as session:
            try:
                # Update published timestamp
                stmt = (
                    update(EventOutboxDB)
                    .where(EventOutboxDB.id == event_id)
                    .values(published_at=datetime.now(UTC).replace(tzinfo=None))
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

            except Exception as e:
                await session.rollback()
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="mark_published",
                    message=f"Failed to mark event as published: {e.__class__.__name__}",
                    external_service="database",
                    correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                    event_id=str(event_id),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def record_error(self, event_id: UUID, error_message: str) -> None:
        """
        Record publishing error and increment retry count.

        Args:
            event_id: ID of the outbox event that failed
            error_message: Error details for debugging
        """
        async with self._session_factory() as session:
            try:
                # Update error info and increment retry count
                stmt = (
                    update(EventOutboxDB)
                    .where(EventOutboxDB.id == event_id)
                    .values(
                        retry_count=EventOutboxDB.retry_count + 1,
                        last_error=error_message[:1000],  # Truncate to fit column
                    )
                )

                result = await session.execute(stmt)
                await session.commit()

                if result.rowcount == 0:
                    logger.warning(
                        "No outbox event found to record error",
                        extra={"event_id": str(event_id)},
                    )
                else:
                    logger.warning(
                        "Recorded error for outbox event",
                        extra={
                            "event_id": str(event_id),
                            "error_message": error_message[:200],  # Log truncated error
                        },
                    )

            except Exception as e:
                await session.rollback()
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="record_error",
                    message=f"Failed to record error for event: {e.__class__.__name__}",
                    external_service="database",
                    correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                    event_id=str(event_id),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def get_event_by_id(self, event_id: UUID) -> OutboxEvent | None:
        """
        Retrieve specific outbox event by ID.

        Args:
            event_id: ID of the outbox event

        Returns:
            Outbox event or None if not found
        """
        async with self._session_factory() as session:
            try:
                # Query by ID
                stmt = select(EventOutboxDB).where(EventOutboxDB.id == event_id)

                result = await session.execute(stmt)
                db_event = result.scalar_one_or_none()

                if db_event:
                    return OutboxEventImpl(db_event)

                return None

            except Exception as e:
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="get_event_by_id",
                    message=f"Failed to retrieve event by ID: {e.__class__.__name__}",
                    external_service="database",
                    correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                    event_id=str(event_id),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def mark_event_failed(self, event_id: UUID, error: str) -> None:
        """
        Mark an event as permanently failed after exceeding max retries.

        Args:
            event_id: ID of the outbox event
            error: Final error message
        """
        async with self._session_factory() as session:
            try:
                # Update event with final error and leave published_at as None
                stmt = (
                    update(EventOutboxDB)
                    .where(EventOutboxDB.id == event_id)
                    .values(
                        last_error=error,
                        updated_at=datetime.now(UTC),
                    )
                )

                await session.execute(stmt)
                await session.commit()

                logger.warning(
                    "Marked outbox event as permanently failed",
                    extra={
                        "event_id": str(event_id),
                        "error": error,
                    },
                )

            except Exception as e:
                await session.rollback()
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="mark_event_failed",
                    message=f"Failed to mark event as failed: {e.__class__.__name__}",
                    external_service="database",
                    correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                    event_id=str(event_id),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def mark_event_published(self, event_id: UUID) -> None:
        """
        Mark an event as successfully published.

        Args:
            event_id: ID of the outbox event
        """
        async with self._session_factory() as session:
            try:
                # Update event with published timestamp
                stmt = (
                    update(EventOutboxDB)
                    .where(EventOutboxDB.id == event_id)
                    .values(
                        published_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )

                await session.execute(stmt)
                await session.commit()

                logger.info(
                    "Marked outbox event as published",
                    extra={"event_id": str(event_id)},
                )

            except Exception as e:
                await session.rollback()
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="mark_event_published",
                    message=f"Failed to mark event as published: {e.__class__.__name__}",
                    external_service="database",
                    correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                    event_id=str(event_id),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def increment_retry_count(self, event_id: UUID, error: str) -> None:
        """
        Increment retry count and record error for a failed event.

        Args:
            event_id: ID of the outbox event
            error: Error message from the failed attempt
        """
        async with self._session_factory() as session:
            try:
                # First get current retry count
                stmt = select(EventOutboxDB).where(EventOutboxDB.id == event_id)
                result = await session.execute(stmt)
                db_event = result.scalar_one_or_none()

                if not db_event:
                    logger.warning(
                        "Outbox event not found for retry increment",
                        extra={"event_id": str(event_id)},
                    )
                    return

                # Update with incremented retry count and error
                update_stmt = (
                    update(EventOutboxDB)
                    .where(EventOutboxDB.id == event_id)
                    .values(
                        retry_count=db_event.retry_count + 1,
                        last_error=error,
                        updated_at=datetime.now(UTC),
                    )
                )

                await session.execute(update_stmt)
                await session.commit()

                logger.info(
                    "Incremented retry count for outbox event",
                    extra={
                        "event_id": str(event_id),
                        "new_retry_count": db_event.retry_count + 1,
                        "error": error,
                    },
                )

            except Exception as e:
                await session.rollback()
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="increment_retry_count",
                    message=f"Failed to increment retry count: {e.__class__.__name__}",
                    external_service="database",
                    correlation_id=UUID("00000000-0000-0000-0000-000000000000"),
                    event_id=str(event_id),
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )
