"""SQLAlchemy models for Entitlements Service.

This module defines database models following established patterns with proper
indexing, JSON columns, and outbox integration for reliable event publishing.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
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


class SubjectType(enum.Enum):
    """Subject type enumeration for credit system."""

    USER = "user"
    ORG = "org"


class OperationStatus(enum.Enum):
    """Credit operation status enumeration."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class CreditBalance(Base):
    """Credit balances per subject (user or organization).

    Tracks current credit balance for each user or organization.
    Supports dual credit system with org/user precedence.
    """

    __tablename__ = "credit_balances"

    # Composite primary key
    subject_type: Mapped[SubjectType] = mapped_column(
        SQLAlchemyEnum(
            SubjectType,
            name="subject_type_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        primary_key=True,
    )
    subject_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)

    # Credit information
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()"), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()"), onupdate=func.now()
    )

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_credit_balances_balance", "balance"),
        Index("ix_credit_balances_updated", "updated_at"),
    )


class CreditOperation(Base):
    """Detailed audit trail for all credit operations.

    Tracks every credit operation for compliance, debugging,
    and business analytics with full correlation support.
    """

    __tablename__ = "credit_operations"

    # Primary key
    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Subject identification
    subject_type: Mapped[SubjectType] = mapped_column(
        SQLAlchemyEnum(SubjectType, name="credit_op_subject_type_enum"),
        nullable=False,
        index=True,
    )
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Operation details
    metric: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Credits consumed/added
    batch_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    consumed_from: Mapped[SubjectType] = mapped_column(
        SQLAlchemyEnum(SubjectType, name="credit_op_consumed_from_enum"),
        nullable=False,
        index=True,
    )
    correlation_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Status tracking
    operation_status: Mapped[OperationStatus] = mapped_column(
        SQLAlchemyEnum(
            OperationStatus,
            name="operation_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        default=OperationStatus.COMPLETED,
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()"), index=True
    )

    # Composite indexes for efficient querying
    __table_args__ = (
        Index("ix_credit_operations_subject", "subject_type", "subject_id"),
        Index("ix_credit_operations_correlation", "correlation_id"),
        Index("ix_credit_operations_status_created", "operation_status", "created_at"),
        Index("ix_credit_operations_metric_created", "metric", "created_at"),
    )


class RateLimitBucket(Base):
    """Rate limiting sliding windows.

    Implements Redis-backed rate limiting with database persistence
    for sliding window calculations and monitoring.
    """

    __tablename__ = "rate_limit_buckets"

    # Composite primary key
    subject_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    metric: Mapped[str] = mapped_column(String(100), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    # Rate limiting data
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Optimization indexes
    __table_args__ = (
        Index("ix_rate_limit_window", "window_start"),
        Index("ix_rate_limit_subject_metric", "subject_id", "metric"),
        Index("ix_rate_limit_cleanup", "window_start", "metric"),  # For cleanup operations
    )


class EventOutbox(Base):
    """Outbox pattern for reliable event publishing.

    Ensures events are published reliably using transactional outbox pattern.
    Events are persisted in the same transaction as business operations.
    """

    __tablename__ = "event_outbox"

    # Primary key
    id: Mapped[UUID] = mapped_column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Event identification
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # Event data
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    topic: Mapped[str] = mapped_column(String(200), nullable=False, index=True)

    # Publishing status
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()"), index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Critical index for outbox processing
    __table_args__ = (
        Index(
            "ix_outbox_unpublished",
            "published_at",
            "topic",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id"),
        Index("ix_outbox_cleanup", "published_at", "created_at"),  # For cleanup
    )
