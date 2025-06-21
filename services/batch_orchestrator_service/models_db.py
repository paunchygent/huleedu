"""Database models for Batch Orchestrator Service."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from common_core.enums import BatchStatus
from services.batch_orchestrator_service.enums_db import (
    PhaseStatusEnum,
    PipelinePhaseEnum,
)


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class Batch(Base):
    """Model representing a batch upload and its overall processing state."""

    __tablename__ = "batches"

    # Primary key - using UUID string from BOS
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Correlation tracking
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    # Batch metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[BatchStatus] = mapped_column(
        SQLAlchemyEnum(
            BatchStatus,
            name="batch_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=BatchStatus.AWAITING_CONTENT_VALIDATION,
        nullable=False,
        index=True,
    )

    # Processing configuration - stored as JSON
    requested_pipelines: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    pipeline_configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Processing progress tracking
    total_essays: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_essays: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Version field for optimistic locking
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Processing metadata
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    phase_logs: Mapped[list["PhaseStatusLog"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="PhaseStatusLog.created_at",
    )
    configuration_snapshots: Mapped[list["ConfigurationSnapshot"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="ConfigurationSnapshot.created_at",
    )
    essays: Mapped[list["BatchEssay"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="BatchEssay.created_at",
    )


class PhaseStatusLog(Base):
    """Model representing the status history of pipeline phases for a batch."""

    __tablename__ = "phase_status_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Phase identification
    phase: Mapped[PipelinePhaseEnum] = mapped_column(
        SQLAlchemyEnum(
            PipelinePhaseEnum,
            name="pipeline_phase_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        index=True,
    )

    # Status tracking
    status: Mapped[PhaseStatusEnum] = mapped_column(
        SQLAlchemyEnum(
            PhaseStatusEnum,
            name="phase_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        index=True,
    )

    # Timing information
    phase_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    phase_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Processing details
    essays_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    essays_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Event correlation
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Metadata and additional context
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )

    # Relationships
    batch: Mapped["Batch"] = relationship(back_populates="phase_logs")


class ConfigurationSnapshot(Base):
    """Model for storing configuration snapshots of pipeline definitions."""

    __tablename__ = "configuration_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Configuration metadata
    snapshot_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Configuration content
    pipeline_definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    configuration_version: Mapped[str] = mapped_column(String(50), nullable=False)

    # Validation and status
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(50), nullable=False, default="valid")
    validation_errors: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Provenance tracking
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_system: Mapped[str] = mapped_column(String(100), nullable=False, default="BOS")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )

    # Additional metadata
    additional_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    batch: Mapped["Batch"] = relationship(back_populates="configuration_snapshots")


class BatchEssay(Base):
    """Model for storing essay data from BatchEssaysReady events for pipeline processing."""

    __tablename__ = "batch_essays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Essay identification
    essay_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Essay content reference
    content_reference: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Student metadata
    student_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Processing metadata
    processing_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=text("NOW()"), onupdate=text("NOW()")
    )

    # Relationships
    batch: Mapped["Batch"] = relationship(back_populates="essays")
