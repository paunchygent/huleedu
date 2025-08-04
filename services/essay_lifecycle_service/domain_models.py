"""
Domain models for Essay Lifecycle Service.

This module contains pure domain entities that are independent of any
infrastructure or storage implementation, following DDD principles.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from pydantic import BaseModel, ConfigDict, Field


class EssayState(BaseModel):
    """
    Domain model for essay state, independent of storage implementation.

    This represents the complete state of an essay as it progresses
    through the HuleEdu processing pipeline. As a domain model, it contains
    only data and domain logic, with no infrastructure dependencies.

    Attributes:
        essay_id: Unique identifier for the essay
        batch_id: Optional batch identifier for grouped processing
        current_status: Current processing status from EssayStatus enum
        processing_metadata: Additional metadata about processing state
        timeline: Status transition history with timestamps
        storage_references: Maps content types to storage identifiers
        text_storage_id: Storage ID for text content (Phase 1 student matching)
        student_id: Associated student identifier (Phase 1 matching)
        association_confirmed_at: When student association was confirmed
        association_method: Method used for student association
        created_at: When the essay record was created
        updated_at: When the essay record was last updated
    """

    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat(),
            ContentType: lambda v: v.value,
            EssayStatus: lambda v: v.value,
        },
        validate_assignment=True,
    )

    essay_id: str
    batch_id: str | None = None
    current_status: EssayStatus
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    timeline: dict[str, datetime] = Field(default_factory=dict)
    storage_references: dict[ContentType, str] = Field(default_factory=dict)
    text_storage_id: str | None = None
    student_id: str | None = None
    association_confirmed_at: datetime | None = None
    association_method: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def update_status(self, new_status: EssayStatus, metadata: dict[str, Any]) -> None:
        """
        Update essay status with timeline tracking.

        This method encapsulates the domain logic for status transitions,
        ensuring timeline consistency and metadata updates.

        Args:
            new_status: The new status from EssayStatus enum
            metadata: Additional metadata to merge into processing_metadata
        """
        self.current_status = new_status
        self.timeline[new_status.value] = datetime.now(UTC)
        self.processing_metadata.update(metadata)
        self.updated_at = datetime.now(UTC)

    def update_student_association(
        self, student_id: str, association_method: str, confirmed_at: datetime | None = None
    ) -> None:
        """
        Update student association information.

        Args:
            student_id: The associated student's identifier
            association_method: Method used (e.g., "name_match", "manual")
            confirmed_at: When the association was confirmed (defaults to now)
        """
        self.student_id = student_id
        self.association_method = association_method
        self.association_confirmed_at = confirmed_at or datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def add_storage_reference(self, content_type: ContentType, storage_id: str) -> None:
        """
        Add or update a storage reference for a content type.

        Args:
            content_type: The type of content from ContentType enum
            storage_id: The storage identifier for this content
        """
        self.storage_references[content_type] = storage_id
        self.updated_at = datetime.now(UTC)

    def is_in_phase(self, phase_name: str) -> bool:
        """
        Check if essay is currently in a specific processing phase.

        Args:
            phase_name: Name of the phase to check

        Returns:
            True if essay's metadata indicates it's in this phase
        """
        current_phase = self.processing_metadata.get("current_phase")
        commanded_phases = self.processing_metadata.get("commanded_phases", [])

        return current_phase == phase_name or phase_name in commanded_phases
