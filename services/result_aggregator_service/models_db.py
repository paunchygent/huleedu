"""Database models for Result Aggregator Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from common_core.status_enums import BatchStatus, ProcessingStage
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""

    pass


class BatchResult(Base):
    """Aggregated batch-level results."""

    __tablename__ = "batch_results"

    # Primary identification
    batch_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Status tracking
    overall_status: Mapped[BatchStatus] = mapped_column(
        SQLAlchemyEnum(BatchStatus),
        nullable=False,
        default=BatchStatus.AWAITING_CONTENT_VALIDATION,
    )

    # Metadata
    essay_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_essay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_essay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Processing metadata
    requested_pipeline: Mapped[Optional[str]] = mapped_column(String(100))
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    # Error tracking
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    batch_error_detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Additional metadata as JSON for flexibility
    batch_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, name="metadata"
    )

    # Relationships
    essays: Mapped[list["EssayResult"]] = relationship(
        "EssayResult", back_populates="batch", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_user_batch", "user_id", "batch_id"),
        Index("idx_batch_status", "overall_status"),
        Index("idx_batch_created", "created_at"),
    )


class EssayResult(Base):
    """Aggregated essay-level results from all processing phases."""

    __tablename__ = "essay_results"

    # Primary identification
    essay_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("batch_results.batch_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Core metadata
    filename: Mapped[Optional[str]] = mapped_column(String(255))
    original_text_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    file_upload_id: Mapped[Optional[str]] = mapped_column(
        String(255), index=True
    )  # Added for traceability

    # === Current Service Results ===

    # Spellcheck Phase Results
    spellcheck_status: Mapped[Optional[ProcessingStage]] = mapped_column(
        SQLAlchemyEnum(ProcessingStage)
    )
    spellcheck_correction_count: Mapped[Optional[int]] = mapped_column(Integer)
    spellcheck_corrected_text_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    spellcheck_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    spellcheck_error_detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # CJ Assessment Phase Results
    cj_assessment_status: Mapped[Optional[ProcessingStage]] = mapped_column(
        SQLAlchemyEnum(ProcessingStage)
    )
    cj_rank: Mapped[Optional[int]] = mapped_column(Integer)
    cj_score: Mapped[Optional[float]] = mapped_column(Float)
    cj_comparison_count: Mapped[Optional[int]] = mapped_column(Integer)
    cj_assessment_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cj_assessment_error_detail: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )

    # === Future Service Placeholders (Commented for Phase 1) ===

    # NLP Analysis Phase Results
    # nlp_status: Mapped[Optional[ProcessingPhaseStatus]] = mapped_column(...)
    # nlp_lexical_diversity_score: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_cohesion_score: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_grammatical_error_rate: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    # nlp_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # nlp_error: Mapped[Optional[str]] = mapped_column(String(500))

    # AI Feedback Phase Results
    # ai_feedback_status: Mapped[Optional[ProcessingPhaseStatus]] = mapped_column(...)
    # ai_feedback_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    # ai_feedback_summary: Mapped[Optional[str]] = mapped_column(String(1000))
    # ai_feedback_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # ai_feedback_error: Mapped[Optional[str]] = mapped_column(String(500))

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    # Relationships
    batch: Mapped["BatchResult"] = relationship("BatchResult", back_populates="essays")

    __table_args__ = (
        Index("idx_essay_batch", "batch_id", "essay_id"),
        Index("idx_essay_spellcheck_status", "spellcheck_status"),
        Index("idx_essay_cj_status", "cj_assessment_status"),
        UniqueConstraint("batch_id", "essay_id", name="uq_batch_essay"),
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
        comment="ID of the aggregate (batch_id, essay_id) that generated this event",
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of aggregate (batch, essay) for categorization",
    )

    # Event details
    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Type/topic of the event (e.g., huleedu.ras.batch.results.ready.v1)",
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
