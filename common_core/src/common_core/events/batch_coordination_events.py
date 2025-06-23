"""
Batch coordination event models for HuleEdu microservices.

These events enable count-based aggregation pattern for batch readiness coordination:
- BOS registers batch expectations with ELS
- ELS aggregates and reports batch readiness back to BOS
- ELS handles excess content that cannot be assigned to batch slots
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_core.events.file_events import EssayValidationFailedV1
from uuid import UUID

from pydantic import BaseModel, Field

from ..metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)


class BatchEssaysRegistered(BaseModel):
    """
    Event sent by BOS to ELS to register batch processing expectations.

    This establishes the count-based coordination contract between BOS and ELS.
    """

    event: str = Field(default="batch.essays.registered", description="Event type identifier")
    batch_id: str = Field(description="Unique batch identifier")
    expected_essay_count: int = Field(description="Number of essays expected in this batch")
    essay_ids: list[str] = Field(description="List of essay IDs that will be processed")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")


class BatchEssaysReady(BaseModel):
    """
    Event sent by ELS to BOS when all essays in a batch are ready for processing.

    Enhanced for lean registration: includes educational context from Class Management Service
    that was deferred from the initial batch registration. Processing services receive complete
    context at the right time rather than prematurely during upload.
    """

    event: str = Field(default="batch.essays.ready", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    ready_essays: list[EssayProcessingInputRefV1] = Field(
        description="List of essays ready for processing with their content references",
    )
    batch_entity: EntityReference = Field(description="Batch entity reference")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")

    # Enhanced context from Class Management Service (lean registration refactoring)
    course_code: str = Field(description="Course code from BOS lean registration")
    course_language: str = Field(description="Language inferred from course_code")
    essay_instructions: str = Field(description="Essay instructions from BOS lean registration")

    # Educational context from Class Management Service
    class_type: str = Field(description="GUEST or REGULAR - determines processing behavior")
    teacher_first_name: str | None = Field(
        default=None, description="Teacher first name from Class Management Service (REGULAR only)"
    )
    teacher_last_name: str | None = Field(
        default=None, description="Teacher last name from Class Management Service (REGULAR only)"
    )

    # Legacy validation failure support
    validation_failures: list[EssayValidationFailedV1] | None = Field(
        default=None,
        description="List of essays that failed validation (EssayValidationFailedV1 events)",
    )
    total_files_processed: int | None = Field(
        default=None,
        description="Total number of files processed (successful + failed)",
    )


class BatchReadinessTimeout(BaseModel):
    """
    Event sent by ELS to BOS when batch readiness times out.

    Allows BOS to handle partial batches or retry logic.
    """

    event: str = Field(default="batch.readiness.timeout", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    ready_essays: list[EssayProcessingInputRefV1] = Field(description="Essays that are ready")
    missing_essay_ids: list[str] = Field(description="Essays still pending")
    expected_count: int = Field(description="Originally expected essay count")
    actual_count: int = Field(description="Actual ready essay count")
    timeout_duration_seconds: int = Field(description="How long ELS waited")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")


class ExcessContentProvisionedV1(BaseModel):
    """
    Event sent by ELS when content cannot be assigned to any available slot.

    This occurs when more files are uploaded than expected_essay_count for a batch.
    """

    event: str = Field(default="excess.content.provisioned", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    original_file_name: str = Field(description="Original uploaded file name")
    text_storage_id: str = Field(description="Content Service storage ID")
    reason: str = Field(description="Reason for excess content (e.g., 'NO_AVAILABLE_SLOT')")
    correlation_id: UUID | None = Field(default=None, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Event envelope integration for batch coordination events
class BatchCoordinationEventData(BaseModel):
    """Union type for all batch coordination event data types."""

    batch_essays_registered: BatchEssaysRegistered | None = None
    batch_essays_ready: BatchEssaysReady | None = None
    batch_readiness_timeout: BatchReadinessTimeout | None = None
    excess_content_provisioned: ExcessContentProvisionedV1 | None = None
