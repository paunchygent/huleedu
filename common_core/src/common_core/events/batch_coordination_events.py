"""
Batch coordination event models for HuleEdu microservices.

These events enable count-based aggregation pattern for batch readiness coordination:
- BOS registers batch expectations with ELS
- File Service reports individual essay readiness to ELS
- ELS aggregates and reports batch readiness back to BOS
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..metadata_models import EntityReference, StorageReferenceMetadata, SystemProcessingMetadata


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


class EssayContentReady(BaseModel):
    """
    Event sent by File Service to ELS when individual essay content is ready.

    This triggers ELS to track readiness and potentially emit BatchEssaysReady.
    """

    event: str = Field(default="essay.content.ready", description="Event type identifier")
    essay_id: str = Field(description="Essay identifier")
    batch_id: str = Field(description="Batch this essay belongs to")
    content_storage_reference: StorageReferenceMetadata = Field(
        description="Reference to stored content"
    )
    entity: EntityReference = Field(description="Essay entity reference")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")
    student_name: Optional[str] = Field(
        default=None, description="Parsed student name, if available (stubbed for skeleton)"
    )
    student_email: Optional[str] = Field(
        default=None, description="Parsed student email, if available (stubbed for skeleton)"
    )


class BatchEssaysReady(BaseModel):
    """
    Event sent by ELS to BOS when all essays in a batch are ready for processing.

    This triggers BOS to begin pipeline orchestration for the complete batch.
    """

    event: str = Field(default="batch.essays.ready", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    ready_essay_ids: list[str] = Field(description="List of essay IDs ready for processing")
    total_count: int = Field(description="Total number of essays in the batch")
    batch_entity: EntityReference = Field(description="Batch entity reference")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")


class BatchReadinessTimeout(BaseModel):
    """
    Event sent by ELS to BOS when batch readiness times out.

    Allows BOS to handle partial batches or retry logic.
    """

    event: str = Field(default="batch.readiness.timeout", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier")
    ready_essay_ids: list[str] = Field(description="Essays that are ready")
    missing_essay_ids: list[str] = Field(description="Essays still pending")
    expected_count: int = Field(description="Originally expected essay count")
    actual_count: int = Field(description="Actual ready essay count")
    timeout_duration_seconds: int = Field(description="How long ELS waited")
    metadata: SystemProcessingMetadata = Field(description="Processing metadata")


# Event envelope integration for the new events
class BatchCoordinationEventData(BaseModel):
    """Union type for all batch coordination event data types."""

    batch_essays_registered: Optional[BatchEssaysRegistered] = None
    essay_content_ready: Optional[EssayContentReady] = None
    batch_essays_ready: Optional[BatchEssaysReady] = None
    batch_readiness_timeout: Optional[BatchReadinessTimeout] = None
