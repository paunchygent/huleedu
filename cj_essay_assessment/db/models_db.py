"""Database models for the CJ Essay Assessment system.

This module defines SQLAlchemy ORM models for data persistence,
including User, BatchUpload, ProcessedEssay, and ComparisonPair.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import Float, ForeignKey, String, Text, text
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class User(Base):
    """User model for authentication and tracking."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    batch_uploads: Mapped[list["BatchUpload"]] = relationship(back_populates="user")


class BatchStatusEnum(enum.Enum):
    """Enum representing the possible states of a BatchUpload."""

    PENDING = "PENDING"
    PROCESSING_ESSAYS = "PROCESSING_ESSAYS"
    ERROR_ESSAY_PROCESSING = "ERROR_ESSAY_PROCESSING"
    ALL_ESSAYS_READY = "ALL_ESSAYS_READY"
    PROCESSING_NLP = "PROCESSING_NLP"
    ERROR_NLP = "ERROR_NLP"
    READY_FOR_COMPARISON = "READY_FOR_COMPARISON"
    PERFORMING_COMPARISONS = "PERFORMING_COMPARISONS"
    ERROR_COMPARISON = "ERROR_COMPARISON"
    COMPLETE_STABLE = "COMPLETE_STABLE"
    COMPLETE_MAX_COMPARISONS = "COMPLETE_MAX_COMPARISONS"

    def __str__(self) -> str:
        return self.value


class ProcessedEssayStatusEnum(enum.Enum):
    """Enum representing the processing state of an individual essay."""

    UPLOADED = "UPLOADED"
    TEXT_EXTRACTED = "TEXT_EXTRACTED"
    TEXT_CLEANED = "TEXT_CLEANED"
    SPELLCHECKED = "SPELLCHECKED"
    READY_FOR_PAIRING = "READY_FOR_PAIRING"
    ERROR_PROCESSING = "ERROR_PROCESSING"
    ERROR_UNSUPPORTED_FILE_TYPE = "ERROR_UNSUPPORTED_FILE_TYPE"
    ERROR_FILE_READ = "ERROR_FILE_READ"
    ERROR_SPELLCHECK = "ERROR_SPELLCHECK"
    ERROR_NLP_ANALYSIS = "ERROR_NLP_ANALYSIS"

    def __str__(self) -> str:
        return self.value


class BatchUpload(Base):
    """Model representing a batch of essays uploaded together."""

    __tablename__ = "batch_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    # States: PENDING, PROCESSING_ESSAYS, ALL_ESSAYS_READY, READY_FOR_COMPARISON,
    # PERFORMING_COMPARISONS, COMPARISON_COMPLETE, BATCH_ERROR, PARTIAL_COMPLETE
    status: Mapped[BatchStatusEnum] = mapped_column(
        SQLAlchemyEnum(
            BatchStatusEnum,
            name="batch_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=BatchStatusEnum.PENDING,
        nullable=False,
        index=True,
    )
    json_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="batch_uploads")
    essays: Mapped[list["ProcessedEssay"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProcessedEssay(Base):
    """Model representing a processed essay with its content and scores."""

    __tablename__ = "processed_essays"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batch_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    internal_filename: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )  # Added for system-managed filenames
    original_content: Mapped[str] = mapped_column(Text)
    processed_content: Mapped[str] = mapped_column(Text)
    text_content_corrected: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking with enum for type safety
    status: Mapped[ProcessedEssayStatusEnum] = mapped_column(
        SQLAlchemyEnum(
            ProcessedEssayStatusEnum,
            name="processed_essay_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=ProcessedEssayStatusEnum.UPLOADED,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )
    current_bt_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    nlp_features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    nlp_analysis_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    # Relationships
    batch: Mapped["BatchUpload"] = relationship(back_populates="essays")
    comparison_pairs_a: Mapped[list["ComparisonPair"]] = relationship(
        back_populates="essay_a",
        foreign_keys="ComparisonPair.essay_a_id",
    )
    comparison_pairs_b: Mapped[list["ComparisonPair"]] = relationship(
        back_populates="essay_b",
        foreign_keys="ComparisonPair.essay_b_id",
    )


class ComparisonPair(Base):
    """Model representing a comparison between two essays."""

    __tablename__ = "comparison_pairs"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("batch_uploads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    essay_a_id: Mapped[int] = mapped_column(ForeignKey("processed_essays.id"))
    essay_b_id: Mapped[int] = mapped_column(ForeignKey("processed_essays.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    prompt_text: Mapped[str] = mapped_column(Text)
    prompt_hash: Mapped[str] = mapped_column(String(64))
    # Values: "essay_a", "essay_b", "error"
    winner: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    from_cache: Mapped[bool] = mapped_column(Boolean, default=False)
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    essay_a: Mapped["ProcessedEssay"] = relationship(
        back_populates="comparison_pairs_a",
        foreign_keys=[essay_a_id],
    )
    essay_b: Mapped["ProcessedEssay"] = relationship(
        back_populates="comparison_pairs_b",
        foreign_keys=[essay_b_id],
    )
