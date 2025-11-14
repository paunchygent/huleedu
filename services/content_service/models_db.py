"""SQLAlchemy models for Content Service."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models for Content Service."""

    pass


class StoredContent(Base):
    """Persisted content bytes for Content Service."""

    __tablename__ = "stored_content"

    # Primary key: stable content identifier used by callers
    content_id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        nullable=False,
    )

    # Raw content bytes and size
    content_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_size: Mapped[int] = mapped_column(Integer, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True,
    )

    # Tracing
    correlation_id: Mapped[Optional[UUID]] = mapped_column(
        PostgresUUID(as_uuid=True),
        nullable=True,
    )

    # HTTP semantics
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
