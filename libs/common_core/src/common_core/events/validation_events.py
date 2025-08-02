"""
Student validation workflow events for Class Management Service integration.

These events support the NLP Service Phase 1 student matching integration where:
1. NLP Service suggests essay-student matches
2. Class Management Service presents matches for human validation
3. Teacher validates associations with timeout fallback
4. Class Management Service publishes confirmed associations to ELS
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from ..event_enums import ProcessingEvent
from ..events.base_event_models import BaseEventData


class StudentAssociation(BaseModel):
    """Legacy student association model - kept for backward compatibility."""

    essay_id: str = Field(description="Essay identifier")
    student_first_name: str = Field(description="Parsed student first name")
    student_last_name: str = Field(description="Parsed student last name")
    student_email: str | None = Field(default=None, description="Parsed student email")
    confidence_score: float = Field(description="Parsing confidence 0.0-1.0")
    is_confirmed: bool = Field(description="Teacher confirmation status")


class StudentAssociationConfirmation(BaseModel):
    """Individual essay-student association confirmation for NLP Phase 1 integration."""

    essay_id: str = Field(description="Essay identifier")
    student_id: str | None = Field(description="Student ID if matched, None if no match")
    confidence_score: float = Field(description="Match confidence score 0.0-1.0")
    validation_method: Literal["human", "timeout", "auto"] = Field(
        description="How the association was validated"
    )
    validated_by: str | None = Field(
        description="User ID if human validated, None for timeout/auto"
    )
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When the association was validated"
    )


class StudentAssociationsConfirmedV1(BaseEventData):
    """
    Confirmed student-essay associations after human validation.

    Publisher: Class Management Service
    Consumer: Essay Lifecycle Service (ELS)
    Topic: student.associations.confirmed
    Handler: ELS - StudentAssociationHandler.handle_student_associations_confirmed()

    Flow (REGULAR batches only):
    1. Class Management receives BatchAuthorMatchesSuggestedV1 from NLP
    2. Teacher validates associations via UI (or 24hr timeout triggers)
    3. Class Management publishes this event with all confirmations
    4. ELS updates essay records with student associations
    5. ELS publishes BatchEssaysReady to BOS
    6. BOS transitions batch to READY_FOR_PIPELINE_EXECUTION

    This completes Phase 1 student matching, allowing REGULAR batches to proceed
    to Phase 2 pipeline processing with proper student attribution.
    """

    event_name: ProcessingEvent = Field(
        default=ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED, description="Event type identifier"
    )
    batch_id: str = Field(description="Batch identifier")
    class_id: str = Field(description="Class identifier where associations were validated")
    associations: list[StudentAssociationConfirmation] = Field(
        description="All essay-student association confirmations"
    )
    timeout_triggered: bool = Field(
        default=False, description="Whether validation timeout triggered auto-confirmation"
    )
    validation_summary: dict[str, int] = Field(
        description="Count of associations by validation_method"
    )


class ValidationTimeoutProcessedV1(BaseEventData):
    """Event published when validation timeout triggers automatic processing."""

    event_name: ProcessingEvent = Field(
        default=ProcessingEvent.VALIDATION_TIMEOUT_PROCESSED, description="Event type identifier"
    )
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
