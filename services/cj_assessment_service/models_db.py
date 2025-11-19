"""Database models for CJ Assessment Service."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from common_core.status_enums import CJBatchStateEnum
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from services.cj_assessment_service.enums_db import CJBatchStatusEnum


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class CJBatchUpload(Base):
    """Model representing a CJ assessment batch linked to a BOS batch."""

    __tablename__ = "cj_batch_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    bos_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    course_code: Mapped[str] = mapped_column(String(50), nullable=False)
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

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Metadata for CJ processing
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Assignment context for grade projection
    assignment_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Identity fields for credit attribution (Phase 3: Entitlements integration)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    org_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Relationships
    essays: Mapped[list[ProcessedEssay]] = relationship(
        back_populates="cj_batch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    comparison_pairs: Mapped[list[ComparisonPair]] = relationship(
        back_populates="cj_batch",
        cascade="all, delete-orphan",
    )

    # Add relationship to state
    batch_state: Mapped["CJBatchState"] = relationship(
        back_populates="batch_upload",
        cascade="all, delete-orphan",
        uselist=False,  # One-to-one
    )


class ProcessedEssay(Base):
    """Model representing an essay in CJ assessment with ELS integration."""

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
    current_bt_se: Mapped[float | None] = mapped_column(Float, nullable=True)  # Standard error
    comparison_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Anchor essay flag
    is_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )

    # Processing metadata
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    cj_batch: Mapped[CJBatchUpload] = relationship(back_populates="essays")
    comparison_pairs_a: Mapped[list[ComparisonPair]] = relationship(
        back_populates="essay_a",
        foreign_keys="ComparisonPair.essay_a_els_id",
    )
    comparison_pairs_b: Mapped[list[ComparisonPair]] = relationship(
        back_populates="essay_b",
        foreign_keys="ComparisonPair.essay_b_els_id",
    )


class ComparisonPair(Base):
    """Model representing a comparison between two essays in CJ assessment."""

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

    # Add correlation tracking for callbacks
    request_correlation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True, doc="Links to LLM provider callback"
    )

    # Add timing information
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="When sent to LLM provider"
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="When result received"
    )

    # Comparison results
    winner: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )  # "essay_a", "essay_b", "error"
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured error fields
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    error_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, doc="When error occurred"
    )
    error_service: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))

    # Processing metadata
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    cj_batch: Mapped[CJBatchUpload] = relationship(back_populates="comparison_pairs")
    essay_a: Mapped[ProcessedEssay] = relationship(
        back_populates="comparison_pairs_a",
        foreign_keys=[essay_a_els_id],
    )
    essay_b: Mapped[ProcessedEssay] = relationship(
        back_populates="comparison_pairs_b",
        foreign_keys=[essay_b_els_id],
    )


class CJBatchState(Base):
    """
    Real-time processing state for CJ assessment batches.
    Single source of truth for batch progress and health.
    """

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
    total_budget: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Original requested comparison budget (never overwritten)",
    )
    total_comparisons: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Cumulative comparisons submitted across all iterations",
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

    # Monitoring fields
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
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
        Integer,
        default=0,
        nullable=False,
        doc="Comparison iteration counter (0 before first submission)",
    )
    processing_metadata: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, doc="Stores previous scores, settings, etc."
    )

    # Relationships
    batch_upload: Mapped["CJBatchUpload"] = relationship(
        back_populates="batch_state",
        lazy="joined",  # Always load with state
    )

    def completion_denominator(self) -> int:
        """Return the denominator to use for completion math."""

        if self.total_budget and self.total_budget > 0:
            return self.total_budget
        if self.total_comparisons and self.total_comparisons > 0:
            return self.total_comparisons
        return 0

    def __repr__(self) -> str:  # pragma: no cover - string helper
        """String representation including key progress fields."""

        return (
            "<CJBatchState("
            f"batch_id={self.batch_id}, "
            f"state={self.state.value if self.state else 'unknown'}, "
            f"total_budget={self.total_budget}, "
            f"total_comparisons={self.total_comparisons}, "
            f"submitted={self.submitted_comparisons}, "
            f"completed={self.completed_comparisons}, "
            f"failed={self.failed_comparisons}, "
            f"current_iteration={self.current_iteration}"
            ")>"
        )


class EventOutbox(Base):
    """
    Event outbox table for reliable event publishing using Transactional Outbox Pattern.

    This table stores events that need to be published to Kafka, ensuring
    that database updates and event publications are atomic. Events are
    written to this table in the same transaction as business logic updates.

    Following the File Service pattern with explicit topic column for better
    query performance and clarity.
    """

    __tablename__ = "event_outbox"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        nullable=False,
        comment="Unique identifier for the outbox entry",
    )

    # Aggregate tracking
    aggregate_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="ID of the aggregate (batch_id, cj_batch_id) that generated this event",
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of aggregate (cj_batch, grade_projection) for categorization",
    )

    # Event details
    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Type/topic of the event (e.g., cj.assessment.completed.v1)",
    )
    event_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=False,
        comment="The complete event data as JSON (EventEnvelope)",
    )
    event_key: Mapped[str | None] = mapped_column(
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
        server_default=text("NOW()"),
        comment="When the event was created",
    )
    published_at: Mapped[datetime | None] = mapped_column(
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
        server_default=text("0"),
        comment="Number of publish attempts",
    )
    last_error: Mapped[str | None] = mapped_column(
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
            f"topic={self.topic}, "
            f"published_at={self.published_at}"
            f")>"
        )


class AssessmentInstruction(Base):
    """Assignment-scoped assessment configuration (admin-only).

    Bridges two workflows:
    - **Admin**: Creates instructions/anchors/prompt refs centrally for assignment_id
    - **User**: Uploads prompts ad-hoc per batch, bypassing this table entirely

    Purpose: Enables assignment-based batches to inherit all assessment metadata
    (judge instructions, grade scale, anchors, student prompt, judge rubric) from a single
    assignment_id lookup in batch_preparation.py.

    Storage pattern: `student_prompt_storage_id` and `judge_rubric_storage_id` reference
    Content Service (text stored there, not here). Both optional - CJ runs without prompts.

    Scope: XOR constraint ensures exactly one of assignment_id or course_id per record.
    """

    __tablename__ = "assessment_instructions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    course_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    instructions_text: Mapped[str] = mapped_column(Text, nullable=False)
    grade_scale: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="swedish_8_anchor", index=True
    )
    student_prompt_storage_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    judge_rubric_storage_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "(assignment_id IS NOT NULL AND course_id IS NULL) OR "
            "(assignment_id IS NULL AND course_id IS NOT NULL)",
            name="chk_context_type",
        ),
    )


class AnchorEssayReference(Base):
    """References to anchor essays stored in Content Service.

    Anchor essays are pre-graded reference essays used to calibrate
    the grade projection system. The actual essay content is stored
    in the Content Service; this table just maintains references.
    """

    __tablename__ = "anchor_essay_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anchor_label: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    grade_scale: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="swedish_8_anchor", index=True
    )
    text_storage_id: Mapped[str] = mapped_column(String(255), nullable=False)
    assignment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "anchor_label",
            "grade_scale",
            name="uq_anchor_assignment_label_scale",
        ),
    )


class GradeProjection(Base):
    """Grade projections with statistical confidence.

    Stores the predicted grades for essays based on CJ rankings,
    along with confidence scores and metadata about the projection.
    """

    __tablename__ = "grade_projections"

    els_essay_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("cj_processed_essays.els_essay_id"), primary_key=True
    )
    cj_batch_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cj_batch_uploads.id"), primary_key=True
    )
    primary_grade: Mapped[str] = mapped_column(String(4), nullable=False)
    grade_scale: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="swedish_8_anchor", index=True
    )
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_label: Mapped[str] = mapped_column(String(10), nullable=False)
    calculation_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
    population_prior: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Model tracking fields
    assessment_method: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="cj_assessment"
    )
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normalized_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("idx_batch_grade", "cj_batch_id", "primary_grade"),)
