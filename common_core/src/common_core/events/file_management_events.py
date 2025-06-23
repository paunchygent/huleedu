"""
File management event models for enhanced file operations.

These events support file addition/removal operations and student parsing
following the thin event principle with focused, essential data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StudentParsingCompletedV1(BaseModel):
    """Event published when File Service completes student parsing for a batch."""

    event: str = Field(default="student.parsing.completed")
    batch_id: str = Field(description="Batch identifier")
    # Direct data - parsing results populate Class Management Service DB
    parsing_results: list[dict] = Field(
        description=(
            "List of parsing results: [{essay_id, filename, first_name, last_name, "
            "student_email, confidence}]"
        )
    )
    parsed_count: int = Field(description="Number of essays with parsed student info")
    total_count: int = Field(description="Total number of essays processed")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BatchFileAddedV1(BaseModel):
    """Event published when file is added to existing batch."""

    event: str = Field(default="batch.file.added")
    batch_id: str = Field(description="Batch identifier")
    essay_id: str = Field(description="New essay identifier")
    filename: str = Field(description="Original filename")
    user_id: str = Field(description="User who added the file")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BatchFileRemovedV1(BaseModel):
    """Event published when file is removed from batch."""

    event: str = Field(default="batch.file.removed")
    batch_id: str = Field(description="Batch identifier")
    essay_id: str = Field(description="Removed essay identifier")
    filename: str = Field(description="Original filename")
    user_id: str = Field(description="User who removed the file")
    correlation_id: UUID | None = Field(default=None)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
