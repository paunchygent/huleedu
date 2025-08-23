"""SQLAlchemy models for Email Service.

This module defines database models following established patterns with proper
indexing, JSON columns, and outbox integration for reliable event publishing.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""


class EmailStatus(enum.Enum):
    """Email processing status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"
    COMPLAINED = "complained"


class EmailRecord(Base):
    """Email record tracking table.

    Tracks all email processing attempts with full audit trail and correlation
    for debugging and monitoring purposes.
    """

    __tablename__ = "email_records"

    # Primary key and identification
    message_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Email addressing
    to_address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    from_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Email content metadata
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    template_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    variables: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Provider information
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Status tracking
    status: Mapped[EmailStatus] = mapped_column(
        SQLAlchemyEnum(
            EmailStatus,
            name="email_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=EmailStatus.PENDING,
        nullable=False,
        index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("NOW()"), index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Optimization indexes
    __table_args__ = (
        Index("ix_email_records_status_created", "status", "created_at"),
        Index("ix_email_records_category_created", "category", "created_at"),
        Index("ix_email_records_provider_status", "provider", "status"),
    )


class EventOutbox(Base):
    """Transactional Outbox table for reliable event publishing.

    Standard outbox pattern following established architecture across all services.
    Ensures events are published atomically with database transactions.
    """

    __tablename__ = "event_outbox"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )

    # Aggregate tracking
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # Event details
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    event_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    topic: Mapped[str] = mapped_column(String(255), nullable=False)

    # Publishing state
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Retry handling
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_event_outbox_unpublished_topic",
            "published_at",
            "topic",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        Index("ix_event_outbox_topic", "topic"),
        Index("ix_event_outbox_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_event_outbox_event_type", "event_type"),
    )


class EmailTemplate(Base):
    """Email template definitions.

    Stores template metadata for validation and tracking purposes.
    Actual template content is stored in filesystem for better version control.
    """

    __tablename__ = "email_templates"

    # Primary key
    template_id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Template metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subject_template: Mapped[str] = mapped_column(String(500), nullable=False)

    # Template status
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )

    # Optimization indexes
    __table_args__ = (Index("ix_email_templates_category_active", "category", "is_active"),)
