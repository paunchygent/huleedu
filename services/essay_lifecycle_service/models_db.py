"""
SQLAlchemy database models for Essay Lifecycle Service PostgreSQL implementation.

Following the pattern established by BOS, with proper enum handling and
optimistic locking support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from common_core.status_enums import EssayStatus
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class EssayStateDB(Base):
    """
    Database model for essay state persistence.

    Maps to the EssayState protocol with proper PostgreSQL types and indexing.
    """

    __tablename__ = "essay_states"

    # Primary key
    essay_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Batch relationship
    batch_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Status tracking with proper enum handling
    current_status: Mapped[EssayStatus] = mapped_column(
        SQLAlchemyEnum(
            EssayStatus,
            name="essay_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        index=True,
    )

    # Processing metadata as JSON
    processing_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Timeline tracking as JSON (stored as ISO strings)
    timeline: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)

    # Storage references as JSON
    storage_references: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)

    # Extracted text storage ID for content idempotency (ELS-002 Phase 1)
    text_storage_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Version field for optimistic locking
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Timestamps (PostgreSQL timezone-naive following BOS pattern)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )

    # Table-level constraints for data integrity (ELS-002 Phase 1)
    # Note: Content idempotency is enforced by partial unique index in migration 20250720_0004
    # This allows multiple essays with NULL text_storage_id while preventing duplicate assignments
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id"],
            ["batch_essay_trackers.batch_id"],
            name="fk_essay_states_batch_id",
            ondelete="SET NULL",
        ),
    )


class BatchEssayTracker(Base):
    """
    Database model for tracking batch coordination and essay slots.

    Enhanced to support batch expectations persistence for robustness against service restarts.
    Stores the complete batch expectation state including course context and slot tracking.
    """

    __tablename__ = "batch_essay_trackers"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Batch identification
    batch_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Batch expectation data
    expected_essay_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    available_slots: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Course context from BOS
    course_code: Mapped[str] = mapped_column(String(50), nullable=False)
    essay_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Event correlation
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Timeout configuration
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, default=86400, nullable=False
    )  # 24 hours for complex processing

    # Legacy fields (maintained for compatibility)
    total_slots: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_slots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Additional metadata as JSON
    batch_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )

    # Relationship to slot assignments
    slot_assignments: Mapped[list[SlotAssignmentDB]] = relationship(
        "SlotAssignmentDB", back_populates="batch_tracker", cascade="all, delete-orphan"
    )


class SlotAssignmentDB(Base):
    """
    Database model for individual slot assignments within batch expectations.

    Stores the assignment of content (text storage) to internal essay ID slots.
    Normalized relationship with BatchEssayTracker for efficient querying.
    """

    __tablename__ = "slot_assignments"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Foreign key to batch tracker
    batch_tracker_id: Mapped[int] = mapped_column(
        ForeignKey("batch_essay_trackers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Slot assignment data
    internal_essay_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    text_storage_id: Mapped[str] = mapped_column(String(255), nullable=False)
    original_file_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Assignment timestamp
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))

    # Relationship back to batch tracker
    batch_tracker: Mapped[BatchEssayTracker] = relationship(
        "BatchEssayTracker", back_populates="slot_assignments"
    )


class EssayProcessingLog(Base):
    """
    Database model for logging essay processing events.

    Provides audit trail for essay state changes and processing events.
    """

    __tablename__ = "essay_processing_logs"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Essay and batch relationship
    essay_id: Mapped[str] = mapped_column(
        ForeignKey("essay_states.essay_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Event tracking
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_status: Mapped[str] = mapped_column(String(100), nullable=False)

    # Event metadata
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))


class EventOutbox(Base):
    """
    Database model for transactional outbox pattern.

    Stores events to be published to Kafka, ensuring reliable delivery
    even when Kafka is temporarily unavailable.
    """

    __tablename__ = "event_outbox"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Aggregate information
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Event data
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    event_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Publishing metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("NOW()")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Indexes for efficient querying
    __table_args__ = (
        # Partial index for unpublished events
        Index(
            "idx_outbox_unpublished", "published_at", postgresql_where=text("published_at IS NULL")
        ),
        Index("idx_outbox_created", "created_at"),
        Index("idx_outbox_aggregate", "aggregate_id", "aggregate_type"),
    )
