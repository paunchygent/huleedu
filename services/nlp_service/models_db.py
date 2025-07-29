"""Database models for NLP Service."""

from __future__ import annotations

import uuid
from datetime import datetime

from common_core.status_enums import ProcessingStatus
from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class NlpAnalysisJob(Base):
    """NLP analysis job tracking."""

    __tablename__ = "nlp_analysis_jobs"
    __table_args__ = (
        UniqueConstraint("batch_id", "essay_id", "analysis_type", name="uq_batch_essay_type"),
        Index("ix_nlp_analysis_jobs_status", "status"),
        Index("ix_nlp_analysis_jobs_batch_id", "batch_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    essay_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ProcessingStatus] = mapped_column(
        String(20), nullable=False, default=ProcessingStatus.PENDING
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    error_detail: Mapped[dict | None] = mapped_column(JSONB)

    # Relationships
    match_results: Mapped[list["StudentMatchResult"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class StudentMatchResult(Base):
    """Student match results from NLP analysis."""

    __tablename__ = "student_match_results"
    __table_args__ = (
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 1"),
        Index("ix_student_match_results_job_id", "job_id"),
        Index("ix_student_match_results_confidence", "confidence_score"),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nlp_analysis_jobs.job_id", ondelete="CASCADE")
    )
    student_id: Mapped[str] = mapped_column(String(255), nullable=False)
    student_name: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_reason: Mapped[str] = mapped_column(String(50), nullable=False)
    match_metadata: Mapped[dict | None] = mapped_column(JSONB)

    # Relationships
    job: Mapped["NlpAnalysisJob"] = relationship(back_populates="match_results")
