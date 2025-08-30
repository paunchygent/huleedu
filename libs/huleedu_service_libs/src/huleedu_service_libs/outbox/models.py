"""
SQLAlchemy models for the Transactional Outbox Pattern.

This module provides a generic EventOutbox model that can be used by any service
implementing the outbox pattern. Services should include this model in their
database migrations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PostgreSQL_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for outbox models."""

    pass


class EventOutbox(Base):
    """
    Generic event outbox table for reliable event publishing.

    This table stores events that need to be published to Kafka, ensuring
    that database updates and event publications are atomic. Events are
    written to this table in the same transaction as business logic updates.

    The event relay worker polls this table and publishes events to Kafka,
    marking them as published upon success.

    Attributes:
        id: Unique identifier for the outbox entry
        aggregate_id: ID of the aggregate this event relates to (e.g., batch_id, file_upload_id)
        aggregate_type: Type of aggregate (e.g., 'batch', 'file_upload', 'essay')
        event_type: Type of the event (e.g., 'huleedu.els.essay.slot.assigned.v1')
        event_data: JSON payload containing the full event envelope
        event_key: Optional key for Kafka partitioning
        created_at: Timestamp when the event was created
        published_at: Timestamp when the event was successfully published (NULL if unpublished)
        retry_count: Number of publication attempts (for retry logic)
        last_error: Last error message if publication failed

    Indexes:
        - unpublished_events_idx: For efficient polling of unpublished events
        - aggregate_lookup_idx: For querying events by aggregate
        - event_type_idx: For monitoring and debugging by event type
    """

    __tablename__ = "event_outbox"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgreSQL_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
        comment="Unique identifier for the outbox entry",
    )

    # Aggregate information
    aggregate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="ID of the aggregate this event relates to",
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of aggregate (e.g., 'batch', 'file_upload')",
    )

    # Event information
    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Type of the event (e.g., 'huleedu.els.essay.slot.assigned.v1')",
    )
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="JSON payload containing the full event envelope",
    )
    event_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Optional key for Kafka partitioning",
    )

    # Kafka targeting
    topic: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Kafka topic to publish to",
    )

    # Publishing state
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Timestamp when the event was created",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when the event was successfully published",
    )

    # Retry handling
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Number of publication attempts",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message if publication failed",
    )

    # Indexes for performance
    __table_args__ = (
        # Index for polling unpublished events efficiently
        Index(
            "ix_event_outbox_unpublished",
            "published_at",
            "created_at",
            postgresql_where="published_at IS NULL",
        ),
        # Index for looking up events by aggregate
        Index(
            "ix_event_outbox_aggregate",
            "aggregate_type",
            "aggregate_id",
        ),
        # Index for monitoring/debugging by event type
        Index(
            "ix_event_outbox_event_type",
            "event_type",
        ),
    )

    def __repr__(self) -> str:
        """String representation for debugging."""
        return (
            f"<EventOutbox(id={self.id}, "
            f"aggregate_type={self.aggregate_type}, "
            f"aggregate_id={self.aggregate_id}, "
            f"event_type={self.event_type}, "
            f"published={'Yes' if self.published_at else 'No'})>"
        )
