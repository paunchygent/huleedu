"""SQLAlchemy models and metadata for spell_checker_service persistence.

This module defines tables `spellcheck_jobs` and `spellcheck_tokens` used by the
PostgreSQL repository.  It mirrors patterns already established in other
services (e.g. essay_lifecycle_service.models_db) to guarantee consistency:

• Declarative Base is created locally to keep service-level ownership.
• Enums are defined as ``str`` subclasses to ease JSON serialisation.
• Relationship between job and tokens uses ``cascade='all, delete-orphan'`` so
  removing a job automatically cleans up tokens.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import List

from sqlalchemy import (
    JSON,
    ARRAY,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY as PG_ARRAY
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()


# Import shared enum to avoid drift across services
from common_core.status_enums import SpellcheckJobStatus as SCJobStatus


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
    error_message: Mapped[str | None] = mapped_column(Text)
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
    __table_args__ = (Index(
        "ix_spellcheck_tokens_token",
        "token",
        postgresql_using="gin",
        postgresql_ops={"token": "gin_trgm_ops"},
    ),)

    token_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("spellcheck_jobs.job_id", ondelete="CASCADE")
    )

    token: Mapped[str] = mapped_column(String(128), nullable=False)
    suggestions: Mapped[list[str] | None] = mapped_column(PG_ARRAY(String), nullable=True)
    position: Mapped[int | None] = mapped_column(Integer)
    sentence: Mapped[str | None] = mapped_column(Text)

    job: Mapped["SpellcheckJob"] = relationship("SpellcheckJob", back_populates="tokens")
