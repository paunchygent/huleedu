"""
Test-specific database models for CJ Assessment Service.

SQLite-compatible versions of the production models for testing.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from common_core.error_enums import ErrorCode
from common_core.status_enums import CJBatchStateEnum
from services.cj_assessment_service.enums_db import CJBatchStatusEnum


class TestBase(AsyncAttrs, DeclarativeBase):
    """Base class for test SQLAlchemy models."""


class TestCJBatchUpload(TestBase):
    """Test model for CJ batch uploads (SQLite compatible)."""

    __tablename__ = "cj_batch_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    bos_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    course_code: Mapped[str] = mapped_column(String(50), nullable=False)
    essay_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    expected_essay_count: Mapped[int] = mapped_column(nullable=False)

    # Status tracking
    status: Mapped[CJBatchStatusEnum] = mapped_column(
        SQLAlchemyEnum(
            CJBatchStatusEnum,
            name="cj_batch_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=CJBatchStatusEnum.PENDING,
        nullable=False,
        index=True,
    )

    # Timestamps (SQLite compatible)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Metadata for CJ processing
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    essays: Mapped[list["TestProcessedEssay"]] = relationship(
        back_populates="cj_batch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    comparison_pairs: Mapped[list["TestComparisonPair"]] = relationship(
        back_populates="cj_batch",
        cascade="all, delete-orphan",
    )

    # Add relationship to state
    batch_state: Mapped["TestCJBatchState"] = relationship(
        back_populates="batch_upload",
        cascade="all, delete-orphan",
        uselist=False,  # One-to-one
    )


class TestProcessedEssay(TestBase):
    """Test model for processed essays (SQLite compatible)."""

    __tablename__ = "cj_processed_essays"

    # Primary key is the ELS essay ID (string UUID)
    els_essay_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    cj_batch_id: Mapped[int] = mapped_column(
        ForeignKey("cj_batch_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Content storage references
    text_storage_id: Mapped[str] = mapped_column(String(256), nullable=False)
    assessment_input_text: Mapped[str] = mapped_column(Text, nullable=False)

    # CJ scoring results
    current_bt_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    comparison_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Timestamps (SQLite compatible)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Processing metadata
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    cj_batch: Mapped[TestCJBatchUpload] = relationship(back_populates="essays")
    comparison_pairs_a: Mapped[list["TestComparisonPair"]] = relationship(
        back_populates="essay_a",
        foreign_keys="TestComparisonPair.essay_a_els_id",
    )
    comparison_pairs_b: Mapped[list["TestComparisonPair"]] = relationship(
        back_populates="essay_b",
        foreign_keys="TestComparisonPair.essay_b_els_id",
    )


class TestComparisonPair(TestBase):
    """Test model for comparison pairs (SQLite compatible)."""

    __tablename__ = "cj_comparison_pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    cj_batch_id: Mapped[int] = mapped_column(
        ForeignKey("cj_batch_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Foreign keys to essays using ELS essay IDs
    essay_a_els_id: Mapped[str] = mapped_column(
        ForeignKey("cj_processed_essays.els_essay_id"),
        nullable=False,
        index=True,
    )
    essay_b_els_id: Mapped[str] = mapped_column(
        ForeignKey("cj_processed_essays.els_essay_id"),
        nullable=False,
        index=True,
    )

    # Comparison metadata
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Add correlation tracking for callbacks (SQLite compatible)
    request_correlation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True, doc="Links to LLM provider callback"
    )

    # Add timing information (SQLite compatible)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, doc="When sent to LLM provider"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, doc="When result received"
    )

    # Comparison results
    winner: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )  # "essay_a", "essay_b", "error"
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured error fields (SQLite compatible)
    error_code: Mapped[ErrorCode | None] = mapped_column(SQLAlchemyEnum(ErrorCode), nullable=True)
    error_correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_service: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps (SQLite compatible)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    # Processing metadata
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    cj_batch: Mapped[TestCJBatchUpload] = relationship(back_populates="comparison_pairs")
    essay_a: Mapped[TestProcessedEssay] = relationship(
        back_populates="comparison_pairs_a",
        foreign_keys=[essay_a_els_id],
    )
    essay_b: Mapped[TestProcessedEssay] = relationship(
        back_populates="comparison_pairs_b",
        foreign_keys=[essay_b_els_id],
    )


class TestCJBatchState(TestBase):
    """Test model for batch state (SQLite compatible)."""

    __tablename__ = "cj_batch_states"

    # Primary key linked to batch
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("cj_batch_uploads.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
        doc="Links to the main batch record",
    )

    # Current state
    state: Mapped[CJBatchStateEnum] = mapped_column(
        SQLAlchemyEnum(
            CJBatchStateEnum,
            name="cj_batch_state_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=CJBatchStateEnum.INITIALIZING,
        nullable=False,
        index=True,
        doc="Current processing state",
    )

    # Progress tracking
    total_comparisons: Mapped[int] = mapped_column(
        Integer, nullable=False, doc="Total comparisons to process"
    )
    submitted_comparisons: Mapped[int] = mapped_column(
        Integer, default=0, doc="Comparisons sent to LLM provider"
    )
    completed_comparisons: Mapped[int] = mapped_column(
        Integer, default=0, doc="Successfully completed comparisons"
    )
    failed_comparisons: Mapped[int] = mapped_column(
        Integer, default=0, doc="Failed comparison attempts"
    )

    # Monitoring fields (SQLite compatible)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
        nullable=False,
        doc="For timeout detection",
    )

    # Partial completion support
    partial_scoring_triggered: Mapped[bool] = mapped_column(
        Boolean, default=False, doc="Prevents duplicate partial scoring"
    )
    completion_threshold_pct: Mapped[int] = mapped_column(
        Integer, default=95, nullable=False, doc="Percentage threshold for partial completion"
    )

    # Processing metadata
    current_iteration: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, doc="Current comparison iteration"
    )
    processing_metadata: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, doc="Stores previous scores, settings, etc."
    )

    # Relationships
    batch_upload: Mapped[TestCJBatchUpload] = relationship(
        back_populates="batch_state",
        lazy="joined",  # Always load with state
    )