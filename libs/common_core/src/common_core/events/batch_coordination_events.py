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
    pass
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..domain_enums import CourseCode
from ..metadata_models import (
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)

# Import for structured error handling (forward reference resolution)
if TYPE_CHECKING:
    from ..models.error_models import ErrorDetail


class BatchEssaysRegistered(BaseModel):
    """
    Event sent by BOS to ELS to register batch processing expectations.

    This establishes the count-based coordination contract between BOS and ELS.
    Enhanced to include course context so ELS can create proper BatchEssaysReady events.
    """

    event: str = Field(default="batch.essays.registered", description="Event type identifier")
    batch_id: str = Field(description="Unique batch identifier")
    expected_essay_count: int = Field(description="Number of essays expected in this batch")
    essay_ids: list[str] = Field(description="List of essay IDs that will be processed")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")

    # Course context from BOS lean registration (added for ELS to use in BatchEssaysReady)
    course_code: CourseCode = Field(description="Course code from batch registration")
    essay_instructions: str = Field(description="Essay instructions from batch registration")
    user_id: str = Field(description="User who owns this batch")


# LEGACY EVENT COMPLETELY REPLACED - NO BACKWARDS COMPATIBILITY
# Old BatchEssaysReady with validation_failures anti-pattern has been eliminated
# Replaced with clean BatchEssaysReady following structured error handling principles


class BatchEssaysReady(BaseModel):
    """
    Clean event for successful batch readiness - follows structured error handling principles.

    ARCHITECTURAL CHANGE: This event has been completely rewritten to eliminate the
    validation_failures anti-pattern. Error handling now uses separate BatchValidationErrorsV1 events
    following HuleEdu structured error handling standards.

    NO BACKWARDS COMPATIBILITY - This is a clean break from the legacy mixed success/error pattern.
    """

    event: str = Field(default="batch.essays.ready", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    ready_essays: list[EssayProcessingInputRefV1] = Field(
        description="List of essays ready for processing with their content references"
    )
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")

    # Enhanced context from Class Management Service (lean registration refactoring)
    course_code: CourseCode = Field(description="Course code from BOS lean registration")
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

    # CLEAN ARCHITECTURE: Legacy validation_failures and total_files_processed fields REMOVED
    # Errors now handled via separate BatchValidationErrorsV1 events following structured error handling


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
    correlation_id: UUID = Field(default_factory=uuid4, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BatchContentProvisioningCompletedV1(BaseModel):
    """
    Event sent by ELS to BOS when all expected content has been provisioned.

    This signals BOS to initiate Phase 1 student matching before batch readiness.
    """

    event: str = Field(
        default="batch.content.provisioning.completed", description="Event type identifier"
    )
    batch_id: str = Field(description="Batch identifier")
    provisioned_count: int = Field(description="Number of essays successfully provisioned")
    expected_count: int = Field(description="Originally expected essay count")
    class_id: str = Field(description="Class ID for student matching")
    course_code: CourseCode = Field(description="Course code for language detection")
    user_id: str = Field(description="User who owns this batch")
    correlation_id: UUID = Field(default_factory=uuid4, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# NEW CLEAN EVENT MODELS - Modern structured error handling replacement for legacy validation_failures pattern


class EssayValidationError(BaseModel):
    """Structured validation error for an essay following HuleEdu error standards."""

    essay_id: str = Field(description="Essay ID that failed validation")
    file_name: str = Field(description="Original file name that failed")
    error_detail: "ErrorDetail" = Field(
        description="Structured error detail using HuleEdu error handling"
    )
    failed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the validation failure occurred",
    )


class BatchErrorSummary(BaseModel):
    """Summary of batch processing errors for observability and metrics."""

    total_errors: int = Field(description="Total number of errors in batch")
    error_categories: dict[str, int] = Field(
        description="Error categories e.g., {'validation': 3, 'extraction': 2}"
    )
    critical_failure: bool = Field(
        default=False, description="True if no essays succeeded in batch (complete failure)"
    )


class BatchValidationErrorsV1(BaseModel):
    """
    Event for batch validation failures - replaces legacy inline error pattern.

    This event follows structured error handling principles with clean separation
    from success events. Replaces the anti-pattern of embedding validation_failures
    in BatchEssaysReady success events.
    """

    event: str = Field(default="batch.validation.errors.v1", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    failed_essays: list[EssayValidationError] = Field(
        description="List of essays that failed validation with structured error details"
    )
    error_summary: BatchErrorSummary = Field(
        description="Summary of errors for observability and metrics"
    )
    correlation_id: UUID = Field(default_factory=uuid4, description="Request correlation ID")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")


# BatchEssaysReadyV2 REMOVED - No need for V2 when following no-backwards-compatibility
# The main BatchEssaysReady event above has been completely rewritten instead


# Event envelope integration for batch coordination events
class BatchCoordinationEventData(BaseModel):
    """Union type for all batch coordination event data types."""

    batch_essays_registered: BatchEssaysRegistered | None = None
    batch_essays_ready: BatchEssaysReady | None = None  # Clean event (legacy anti-pattern removed)
    batch_validation_errors: BatchValidationErrorsV1 | None = None  # New structured error event
    batch_readiness_timeout: BatchReadinessTimeout | None = None
    excess_content_provisioned: ExcessContentProvisionedV1 | None = None
