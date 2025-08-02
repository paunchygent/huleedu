"""
Essay Lifecycle Service event models for HuleEdu microservices.

This module contains events related to essay slot assignment and lifecycle
management by the Essay Lifecycle Service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from common_core.event_enums import ProcessingEvent
from common_core.events.base_event_models import BaseEventData
from common_core.metadata_models import EssayProcessingInputRefV1


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


class BatchStudentMatchingRequestedV1(BaseEventData):
    """
    Batch-level request for Phase 1 student matching.

    Publisher: Essay Lifecycle Service (ELS)
    Consumer: NLP Service
    Topic: batch.student.matching.requested
    Handler: NLP - BatchStudentMatchingHandler.handle_batch_student_matching()

    Flow (REGULAR batches only):
    1. ELS receives BatchServiceStudentMatchingInitiateCommandDataV1 from BOS
    2. ELS updates batch state to awaiting_student_associations
    3. ELS publishes this event to NLP Service
    4. NLP processes all essays in parallel for student name extraction
    5. NLP publishes BatchAuthorMatchesSuggestedV1 to Class Management

    Note: This is a Phase 1 event - occurs BEFORE batch readiness for REGULAR batches only.
    """

    event_name: ProcessingEvent = ProcessingEvent.BATCH_STUDENT_MATCHING_REQUESTED
    batch_id: str = Field(description="Batch identifier")
    essays_to_process: list[EssayProcessingInputRefV1] = Field(
        description="All essays in batch requiring student matching"
    )
    class_id: str = Field(description="Class ID for roster lookup")
