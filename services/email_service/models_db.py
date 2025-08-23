"""SQLAlchemy models for Email Service.

This module defines database models following established patterns with proper
indexing, JSON columns, and outbox integration for reliable event publishing.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


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


class EmailOutboxEvent(Base):
    """Outbox pattern for reliable event publishing.

    Ensures email events are published atomically with database transactions
    following Rule 022 with topic column and proper indexing.
    """

    __tablename__ = "email_outbox_events"

    # Primary key
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID

    # Event metadata
    topic: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_service: Mapped[str] = mapped_column(String(50), nullable=False, default="email_service")
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Event payload
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Publishing status
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("NOW()")
    )

    # Optimization indexes per Rule 022
    __table_args__ = (
        Index(
            "ix_email_outbox_unpublished_priority",
            "published_at",
            "topic",
            "created_at",
        ),
        Index("ix_email_outbox_correlation", "correlation_id"),
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
