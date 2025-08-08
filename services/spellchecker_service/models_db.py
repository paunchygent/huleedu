"""SQLAlchemy models and metadata for spellchecker_service persistence.

This module defines tables `spellcheck_jobs` and `spellcheck_tokens` used by the
PostgreSQL repository.  It mirrors patterns already established in other
services (e.g. essay_lifecycle_service.models_db) to guarantee consistency:

• Declarative Base is created locally to keep service-level ownership.
• Enums are defined as ``str`` subclasses to ease JSON serialisation.
• Relationship between job and tokens uses ``cascade='all, delete-orphan'`` so
  removing a job automatically cleans up tokens.
• EventOutbox model is imported from shared library for transactional outbox pattern.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List

# Import shared enum to avoid drift across services
from common_core.status_enums import SpellcheckJobStatus as SCJobStatus

# Removed import of EventOutbox - using local definition for proper SQLAlchemy inheritance
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm.decl_api import DeclarativeBase


class Base(DeclarativeBase):
    pass


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
    id: Mapped[uuid.UUID] = mapped_column(
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
        comment="ID of the aggregate (spellcheck_job_id) that generated this event",
    )
    aggregate_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Type of aggregate (spellcheck_job) for categorization",
    )

    # Event details
    event_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Type/topic of the event (e.g., spellcheck.result.v1)",
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


class SpellcheckJob(Base):
    """Parent row representing a spell-check run for a single essay."""

    __tablename__ = "spellcheck_jobs"
    __table_args__ = (
        UniqueConstraint("batch_id", "essay_id", name="uq_batch_essay"),
        Index("ix_spellcheck_jobs_status", "status"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    essay_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    language: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    total_tokens: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[SCJobStatus] = mapped_column(
        Enum(SCJobStatus), nullable=False, default=SCJobStatus.PENDING
    )
    error_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    processing_ms: Mapped[int | None] = mapped_column(
        Integer, CheckConstraint("processing_ms >= 0")
    )

    created_at: Mapped[datetime] = mapped_column(
        "created_at",
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at",
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tokens: Mapped[List["SpellcheckToken"]] = relationship(
        "SpellcheckToken",
        back_populates="job",
        cascade="all, delete-orphan",
    )


class SpellcheckToken(Base):
    """Individual misspelling found during a spell-check job."""

    __tablename__ = "spellcheck_tokens"
    __table_args__ = (
        Index(
            "ix_spellcheck_tokens_token",
            "token",
            postgresql_using="gin",
            postgresql_ops={"token": "gin_trgm_ops"},
        ),
    )

    token_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spellcheck_jobs.job_id", ondelete="CASCADE")
    )

    token: Mapped[str] = mapped_column(String(128), nullable=False)
    suggestions: Mapped[list[str] | None] = mapped_column(PG_ARRAY(String), nullable=True)
    position: Mapped[int | None] = mapped_column(Integer)
    sentence: Mapped[str | None] = mapped_column(Text)

    job: Mapped["SpellcheckJob"] = relationship("SpellcheckJob", back_populates="tokens")
