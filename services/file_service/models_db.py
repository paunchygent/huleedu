"""SQLAlchemy models for File Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class FileUpload(Base):
    """Model for tracking file uploads with user attribution."""

    __tablename__ = "file_uploads"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    # Core identifiers
    file_upload_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    batch_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # File metadata
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Storage references
    raw_file_storage_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    text_storage_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Processing status
    processing_status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="PENDING", index=True
    )
    validation_error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    validation_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    upload_timestamp: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,
    )
    processed_timestamp: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Tracing
    correlation_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True), nullable=True
    )

    def __repr__(self) -> str:
        """String representation of FileUpload."""
        return (
            f"<FileUpload("
            f"file_upload_id={self.file_upload_id}, "
            f"batch_id={self.batch_id}, "
            f"user_id={self.user_id}, "
            f"filename={self.filename}, "
            f"status={self.processing_status}"
            f")>"
        )


class EventOutbox(Base):
    """
    Event outbox table for reliable event publishing using Transactional Outbox Pattern.

    This table stores events that need to be published to Kafka, ensuring
    that database updates and event publications are atomic. Events are
    written to this table in the same transaction as business logic updates.

    Based on huleedu_service_libs.outbox.models.EventOutbox template.
    """

    __tablename__ = "event_outbox"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
        comment="Unique identifier for the outbox entry",
    )

    # Aggregate tracking
    aggregate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="ID of the aggregate (file_upload_id, batch_id) that generated this event",
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of aggregate (file_upload, batch) for categorization",
    )

    # Event details
    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Type/topic of the event (e.g., essay.content.provisioned)",
    )
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="The complete event data as JSON (EventEnvelope)",
    )
    event_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Kafka message key for partitioning",
    )

    # Kafka targeting
    topic: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Kafka topic to publish to",
    )

    # Processing state
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        comment="When the event was created",
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="When the event was successfully published to Kafka",
    )

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of publish attempts",
    )
    last_error: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Last error message if publishing failed",
    )

    # Indexes for performance
    __table_args__ = (
        # Topic-aware index for unpublished events (relay worker efficiency)
        Index(
            "ix_event_outbox_unpublished_topic",
            "published_at", "topic", "created_at",
            postgresql_where=text("published_at IS NULL")
        ),
        # Topic index for filtering and queries
        Index("ix_event_outbox_topic", "topic"),
        # Legacy indexes
        Index("ix_event_outbox_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_event_outbox_event_type", "event_type"),
    )

    def __repr__(self) -> str:
        """String representation of EventOutbox."""
        return (
            f"<EventOutbox("
            f"id={self.id}, "
            f"aggregate_id={self.aggregate_id}, "
            f"event_type={self.event_type}, "
            f"published_at={self.published_at}"
            f")>"
        )
