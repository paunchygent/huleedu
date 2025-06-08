"""
SQLAlchemy database models for Essay Lifecycle Service PostgreSQL implementation.

Following the pattern established by BOS, with proper enum handling and
optimistic locking support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from common_core.enums import EssayStatus
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import ENUM as SQLAlchemyEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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
            values_callable=lambda obj: [e.value for e in obj]
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

    # Version field for optimistic locking
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Timestamps (PostgreSQL timezone-naive following BOS pattern)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )


class BatchEssayTracker(Base):
    """
    Database model for tracking batch coordination and essay slots.

    Supports the batch essay tracking functionality.
    """

    __tablename__ = "batch_essay_trackers"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Batch identification
    batch_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Slot and content tracking
    total_slots: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_slots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Batch metadata as JSON
    batch_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)

    # Status and readiness tracking
    is_ready: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
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
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
