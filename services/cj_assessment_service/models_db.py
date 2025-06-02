"""Database models for the CJ Assessment Service.

This module defines SQLAlchemy ORM models for CJ Assessment data persistence.
Adapted from the original prototype to focus on CJ assessment workflow with
string-based ELS essay IDs and BOS batch integration.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text, text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .enums_db import CJBatchStatusEnum


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class CJBatchUpload(Base):
    """Model representing a CJ assessment batch linked to a BOS batch."""

    __tablename__ = "cj_batch_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    bos_batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Metadata for CJ processing
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    essays: Mapped[list["ProcessedEssay"]] = relationship(
        back_populates="cj_batch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    comparison_pairs: Mapped[list["ComparisonPair"]] = relationship(
        back_populates="cj_batch",
        cascade="all, delete-orphan",
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
    comparison_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )

    # Processing metadata
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    cj_batch: Mapped["CJBatchUpload"] = relationship(back_populates="essays")
    comparison_pairs_a: Mapped[list["ComparisonPair"]] = relationship(
        back_populates="essay_a",
        foreign_keys="ComparisonPair.essay_a_els_id",
    )
    comparison_pairs_b: Mapped[list["ComparisonPair"]] = relationship(
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
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Comparison results
    winner: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # "essay_a", "essay_b", "error"
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))

    # Processing metadata
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    cj_batch: Mapped["CJBatchUpload"] = relationship(back_populates="comparison_pairs")
    essay_a: Mapped["ProcessedEssay"] = relationship(
        back_populates="comparison_pairs_a",
        foreign_keys=[essay_a_els_id],
    )
    essay_b: Mapped["ProcessedEssay"] = relationship(
        back_populates="comparison_pairs_b",
        foreign_keys=[essay_b_els_id],
    )
