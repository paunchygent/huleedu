"""
File management event models for enhanced file operations.

These events support file addition/removal operations
following the thin event principle with focused, essential data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BatchFileAddedV1(BaseModel):
    """Event published when file is added to existing batch."""

    event: str = Field(default="batch.file.added")
    batch_id: str = Field(description="Batch identifier")
    file_upload_id: str = Field(description="Unique identifier for this file upload")
    filename: str = Field(description="Original filename")
    user_id: str = Field(description="User who added the file")
    correlation_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BatchFileRemovedV1(BaseModel):
    """Event published when file is removed from batch."""

    event: str = Field(default="batch.file.removed")
    batch_id: str = Field(description="Batch identifier")
    file_upload_id: str = Field(description="File upload identifier to remove")
    filename: str = Field(description="Original filename")
    user_id: str = Field(description="User who removed the file")
    correlation_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
