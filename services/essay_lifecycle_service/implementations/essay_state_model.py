"""
Essay state data model for tracking essay processing lifecycle.

This model represents the complete state of an essay as it progresses
through the HuleEdu processing pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from pydantic import BaseModel, ConfigDict, Field


class EssayState(BaseModel):
    """
    Essay state data model for tracking essay processing lifecycle.

    This model represents the complete state of an essay as it progresses
    through the HuleEdu processing pipeline.
    """

    essay_id: str
    batch_id: str | None = None
    current_status: EssayStatus
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    timeline: dict[str, datetime] = Field(default_factory=dict)
    storage_references: dict[ContentType, str] = Field(default_factory=dict)
    text_storage_id: str | None = None  # Added for student association tracking
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Pydantic v2 configuration (replaces class Config)
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
        }
    )

    def update_status(
        self, new_status: EssayStatus, metadata: dict[str, Any] | None = None
    ) -> None:
        """Update essay status and metadata."""
        self.current_status = new_status
        self.updated_at = datetime.now(UTC)
        self.timeline[new_status.value] = self.updated_at

        if metadata:
            self.processing_metadata.update(metadata)
