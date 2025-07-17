"""Database models for Result Aggregator Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from common_core.status_enums import BatchStatus, ProcessingStage
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SQLAlchemyEnum
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
    last_error: Mapped[Optional[str]] = mapped_column(String(500))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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

    # === Current Service Results ===

    # Spellcheck Phase Results
    spellcheck_status: Mapped[Optional[ProcessingStage]] = mapped_column(
        SQLAlchemyEnum(ProcessingStage)
    )
    spellcheck_correction_count: Mapped[Optional[int]] = mapped_column(Integer)
    spellcheck_corrected_text_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    spellcheck_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    spellcheck_error: Mapped[Optional[str]] = mapped_column(String(500))

    # CJ Assessment Phase Results
    cj_assessment_status: Mapped[Optional[ProcessingStage]] = mapped_column(
        SQLAlchemyEnum(ProcessingStage)
    )
    cj_rank: Mapped[Optional[int]] = mapped_column(Integer)
    cj_score: Mapped[Optional[float]] = mapped_column(Float)
    cj_comparison_count: Mapped[Optional[int]] = mapped_column(Integer)
    cj_assessment_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cj_assessment_error: Mapped[Optional[str]] = mapped_column(String(500))

    # === Future Service Placeholders (Commented for Phase 1) ===

    # NLP Analysis Phase Results
    # nlp_status: Mapped[Optional[ProcessingPhaseStatus]] = mapped_column(...)
    # nlp_lexical_diversity_score: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_cohesion_score: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_grammatical_error_rate: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_metrics_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
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
