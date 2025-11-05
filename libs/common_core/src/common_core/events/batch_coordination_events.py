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
from ..metadata_models import EssayProcessingInputRefV1, StorageReferenceMetadata, SystemProcessingMetadata
from ..status_enums import BatchStatus

# Import for structured error handling (forward reference resolution)
if TYPE_CHECKING:
    from ..models.error_models import ErrorDetail


class BatchEssaysRegistered(BaseModel):
    """
    Event to register batch processing expectations with ELS.

    Publisher: Batch Orchestrator Service (BOS)
    Consumer: Essay Lifecycle Service (ELS)
    Topic: batch.essays.registered
    Handler: ELS - DefaultBatchCoordinationHandler.handle_batch_essays_registered()

    Flow:
    1. API Gateway sends BatchRegistrationRequestV1 to BOS (with/without class_id)
    2. BOS creates batch record and generates essay IDs
    3. BOS publishes this event to ELS
    4. ELS creates essay slots and starts tracking content provisioning

    This establishes the count-based coordination contract between BOS and ELS.
    Enhanced to include course context so ELS can create proper BatchEssaysReady events.
    """

    event: str = Field(default="batch.essays.registered", description="Event type identifier")
    entity_id: str = Field(description="Unique batch identifier")
    expected_essay_count: int = Field(description="Number of essays expected in this batch")
    essay_ids: list[str] = Field(description="List of essay IDs that will be processed")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")

    # Course context from BOS lean registration (added for ELS to use in BatchEssaysReady)
    course_code: CourseCode = Field(description="Course code from batch registration")
    student_prompt_ref: StorageReferenceMetadata | None = Field(
        default=None,
        description="Content Service reference for student prompt payloads",
    )
    user_id: str = Field(description="User who owns this batch")
    org_id: str | None = Field(
        default=None,
        description="Organization ID for credit attribution, None for individual users",
    )

    # Class context for GUEST vs REGULAR batch determination
    class_id: str | None = Field(
        default=None,
        description=(
            "Class ID for REGULAR batches requiring student matching, None for GUEST batches"
        ),
    )


# LEGACY EVENT COMPLETELY REPLACED - NO BACKWARDS COMPATIBILITY
# Old BatchEssaysReady with validation_failures anti-pattern has been eliminated
# Replaced with clean BatchEssaysReady following structured error handling principles


class BatchEssaysReady(BaseModel):
    """
    Event indicating batch is ready for Phase 2 pipeline processing.

    Publisher: Essay Lifecycle Service (ELS)
    Consumer: Batch Orchestrator Service (BOS)
    Topic: batch.essays.ready
    Handler: BOS - BatchEssaysReadyHandler.handle_batch_essays_ready()

    IMPORTANT: This event is ONLY published for REGULAR batches after student associations.
    GUEST batches do NOT receive this event - they transition directly from
    BatchContentProvisioningCompletedV1 to READY_FOR_PIPELINE_EXECUTION.

    Flow for REGULAR batches only:
    1. ELS receives StudentAssociationsConfirmedV1 from Class Management
    2. ELS updates essays with student associations
    3. ELS publishes this event with enriched essay data
    4. BOS stores essays and transitions to READY_FOR_PIPELINE_EXECUTION

    ARCHITECTURAL CHANGE: This event has been completely rewritten to eliminate the
    validation_failures anti-pattern. Error handling now uses separate
    BatchValidationErrorsV1 events following HuleEdu structured error handling standards.
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
    student_prompt_ref: StorageReferenceMetadata | None = Field(
        default=None,
        description="Content Service reference for prompt payloads",
    )

    # Educational context from Class Management Service
    class_type: str = Field(description="GUEST or REGULAR - determines processing behavior")

    # CLEAN ARCHITECTURE: Legacy validation_failures and total_files_processed fields REMOVED
    # Errors now handled via separate BatchValidationErrorsV1 events following structured
    # error handling


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
    Event indicating all expected content has been provisioned for a batch.

    Publisher: Essay Lifecycle Service (ELS)
    Consumer: Batch Orchestrator Service (BOS)
    Topic: batch.content.provisioning.completed

    Flow for GUEST batches (class_id = null):
    1. ELS publishes this event when all content is provisioned
    2. BOS receives event and directly transitions batch to READY_FOR_PIPELINE_EXECUTION
    3. No student matching needed, no BatchEssaysReady event needed

    Flow for REGULAR batches (class_id exists):
    1. ELS publishes this event when all content is provisioned
    2. BOS receives event and initiates Phase 1 student matching
    3. Student matching flow completes with StudentAssociationsConfirmedV1
    4. ELS then publishes BatchEssaysReady with student associations
    5. BOS transitions to READY_FOR_PIPELINE_EXECUTION
    """

    event: str = Field(
        default="batch.content.provisioning.completed", description="Event type identifier"
    )
    batch_id: str = Field(description="Batch identifier")
    provisioned_count: int = Field(description="Number of essays successfully provisioned")
    expected_count: int = Field(description="Originally expected essay count")
    course_code: CourseCode = Field(description="Course code for language detection")
    user_id: str = Field(description="User who owns this batch")
    essays_for_processing: list[EssayProcessingInputRefV1] = Field(
        description="All provisioned essays with content references - used by BOS for GUEST batches"
    )
    correlation_id: UUID = Field(default_factory=uuid4, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# NEW CLEAN EVENT MODELS - Modern structured error handling replacement for legacy
# validation_failures pattern


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


class BatchPipelineCompletedV1(BaseModel):
    """
    Event indicating that all requested pipeline phases have completed for a batch.

    Publisher: Batch Orchestrator Service (BOS)
    Consumer: API Gateway, UI Services, Batch Conductor Service (BCS)
    Topic: batch.pipeline.completed

    Published when:
    1. All requested pipeline phases have completed (successfully or with failures)
    2. No more phases remain in the requested_pipelines list
    3. Pipeline execution has reached its terminal state

    This event enables:
    - Multi-pipeline support by clearing active pipeline state
    - UI notifications of pipeline completion
    - BCS to track completed phases for dependency resolution
    - API Gateway to update batch status for clients
    """

    event: str = Field(default="batch.pipeline.completed", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    completed_phases: list[str] = Field(
        description="List of phase names that were completed in this pipeline execution"
    )
    final_status: BatchStatus = Field(
        description=(
            "Final pipeline status. Must be a BatchStatus enum value "
            "(e.g., BatchStatus.COMPLETED_SUCCESSFULLY, BatchStatus.COMPLETED_WITH_FAILURES, "
            "BatchStatus.FAILED_CRITICALLY)"
        )
    )
    processing_duration_seconds: float = Field(
        description="Total duration of pipeline execution in seconds"
    )
    successful_essay_count: int = Field(
        description="Number of essays that completed successfully across all phases"
    )
    failed_essay_count: int = Field(description="Number of essays that failed in any phase")
    correlation_id: UUID = Field(description="Correlation ID from the original pipeline request")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")


class PhaseSkippedV1(BaseModel):
    """
    Event indicating that a phase was skipped during pipeline resolution due to prior completion.

    Publisher: Batch Conductor Service (BCS)
    Consumer: Test harnesses, monitoring services, API Gateway
    Topic: batch.phase.skipped

    Published when:
    1. BCS resolves a pipeline and finds that a phase was already completed
    2. The phase is pruned from the execution list
    3. Results from the previous completion will be reused

    This event enables:
    - Test harnesses to track which phases were pruned
    - Monitoring and observability of pipeline optimization
    - UI to show users which phases were skipped and why
    """

    event: str = Field(default="batch.phase.skipped", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    phase_name: str = Field(description="Name of the phase that was skipped")
    skip_reason: str = Field(
        default="already_completed",
        description="Reason why phase was skipped (e.g., 'already_completed')",
    )
    storage_id: str | None = Field(
        default=None, description="Storage ID from previous completion that will be reused"
    )
    correlation_id: UUID = Field(description="Correlation ID from the pipeline request")
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
    batch_content_provisioning_completed: BatchContentProvisioningCompletedV1 | None = None
    batch_pipeline_completed: BatchPipelineCompletedV1 | None = None  # Multi-pipeline support
    phase_skipped: PhaseSkippedV1 | None = None  # Phase pruning support
