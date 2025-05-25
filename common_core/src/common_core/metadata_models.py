"""common_core.metadata_models – Strongly-typed metadata building blocks"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, Field

from .enums import (  # Assuming enums.py is in the same directory
    ContentType,
    ProcessingStage,
)

__all__ = [
    "EntityReference",
    "SystemProcessingMetadata",
    "BatchProcessingMetadata",
    "AIFeedbackMetadata",
    "StorageReferenceMetadata",
    "TaskProcessingMetadata",
    "UserActivityMetadata",
    "CancellationMetadata",
]


class EntityReference(BaseModel):
    entity_id: str
    entity_type: str
    parent_id: Optional[str] = None
    model_config = {
        "frozen": True,
        "json_schema_extra": {"examples": [{"entity_id": "123", "entity_type": "essay"}]},
    }


class SystemProcessingMetadata(BaseModel):
    entity: EntityReference
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_stage: Optional[ProcessingStage] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    event: Optional[str] = None  # Actual event name string, e.g., from ProcessingEvent enum
    events_trail: List[Dict[str, Any]] = Field(default_factory=list, alias="events")  # Audit trail
    error_info: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"populate_by_name": True}


class BatchProcessingMetadata(BaseModel):
    user_id: Optional[str] = None  # Changed to str for flexibility
    context_source: str = Field(default="web_upload", alias="context")
    file_count: int
    total_essays: Optional[int] = None
    processed_essays: Optional[int] = None
    failed_essays: Optional[int] = None
    failed_upload_count: Optional[int] = None
    failed_processing_count: Optional[int] = None
    teacher_name: Optional[str] = None
    course_code: Optional[str] = None
    essay_instructions: Optional[str] = None
    class_designation: Optional[str] = None
    upload_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = Field(default=None, alias="completed_at")
    is_terminal_state: bool = False
    can_cancel: bool = True
    success_rate: Optional[float] = None
    failure_reasons: Dict[str, Any] = Field(default_factory=dict)
    processing_metrics: Dict[str, Any] = Field(default_factory=dict)
    model_config = {"populate_by_name": True}


class AIFeedbackMetadata(BaseModel):
    teacher_name: Optional[str] = None
    course_code: Optional[str] = None
    essay_instructions: Optional[str] = None
    class_designation: Optional[str] = None
    student_name: Optional[str] = None
    student_email: Optional[EmailStr] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    model_version: Optional[str] = None
    generation_time_seconds: Optional[float] = None
    has_feedback: bool = False
    has_editor_revision: bool = False
    has_metrics: bool = False


class StorageReferenceMetadata(BaseModel):
    references: Dict[ContentType, Dict[str, str]] = Field(default_factory=dict)

    def add_reference(
        self, ctype: ContentType, storage_id: str, path_hint: Optional[str] = None
    ) -> None:
        self.references[ctype] = {"storage_id": storage_id, "path": path_hint or ""}


class TaskProcessingMetadata(BaseModel):
    task_id: UUID = Field(default_factory=uuid4)
    retries: int = 0
    last_retry_at: Optional[datetime] = None


class UserActivityMetadata(BaseModel):
    username: str
    email: Optional[EmailStr] = None
    event_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: Optional[str] = None
    previous_status: Optional[str] = None
    activity_details: Optional[Dict[str, Any]] = None


class CancellationMetadata(BaseModel):
    cancelled_by: Optional[str] = None
    reason: Optional[str] = None
    cancellation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
