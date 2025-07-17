"""
Student validation workflow events for Class Management Service integration.

These events support the two-stage student association workflow where:
1. File Service parses potential student names/emails from files
2. Teacher manually validates associations via API Gateway
3. Class Management Service stores final associations and triggers processing
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from ..events.base_event_models import BaseEventData


class StudentAssociation(BaseModel):
    """Individual student association with confidence scoring."""

    essay_id: str = Field(description="Essay identifier")
    student_first_name: str = Field(description="Parsed student first name")
    student_last_name: str = Field(description="Parsed student last name")
    student_email: str | None = Field(default=None, description="Parsed student email")
    confidence_score: float = Field(description="Parsing confidence 0.0-1.0")
    is_confirmed: bool = Field(description="Teacher confirmation status")


class StudentAssociationsConfirmedV1(BaseEventData):
    """Event published when teacher confirms student associations for a batch."""

    batch_id: str = Field(description="Batch identifier")
    user_id: str = Field(description="Teacher/user ID who confirmed")
    class_id: str = Field(description="Target class ID in Class Management Service")
    confirmed_associations: list[StudentAssociation] = Field(
        description="Student associations confirmed by teacher"
    )
    rejected_associations: list[StudentAssociation] = Field(
        description="Student associations rejected by teacher"
    )
    total_essays: int = Field(description="Total essays in batch")
    confirmation_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationTimeoutProcessedV1(BaseEventData):
    """Event published when validation timeout triggers automatic processing."""

    batch_id: str = Field(description="Batch identifier")
    user_id: str = Field(description="Teacher/user ID")
    timeout_hours: int = Field(description="Configured timeout period in hours")
    auto_confirmed_associations: list[StudentAssociation] = Field(
        description="High-confidence associations auto-confirmed"
    )
    guest_essays: list[str] = Field(
        description="Essay IDs treated as GUEST (low confidence or no match)"
    )
    guest_class_created: bool = Field(description="Whether a guest class was created")
    guest_class_id: str | None = Field(default=None, description="Created guest class ID")
    processing_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
