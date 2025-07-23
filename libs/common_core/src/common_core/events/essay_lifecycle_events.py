"""
Essay Lifecycle Service event models for HuleEdu microservices.

This module contains events related to essay slot assignment and lifecycle
management by the Essay Lifecycle Service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EssaySlotAssignedV1(BaseModel):
    """
    Event published by ELS when content is assigned to an essay slot.

    This event provides the critical mapping between file_upload_id (from File Service)
    and essay_id (from BOS pre-generated slots), enabling client-side traceability
    of individual file uploads through the entire processing pipeline.
    """

    event: str = Field(default="essay.slot.assigned", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    essay_id: str = Field(description="Assigned essay ID from pre-generated slots")
    file_upload_id: str = Field(description="Original upload tracking identifier")
    text_storage_id: str = Field(description="Storage ID of assigned content")
    correlation_id: UUID = Field(default_factory=uuid4, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

