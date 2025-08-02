"""
File Service event models for HuleEdu microservices.

This module contains events related to file processing and content provisioning
by the File Service. These events are part of the file processing domain,
separate from batch coordination concerns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..error_enums import FileValidationErrorCode
from ..models.error_models import ErrorDetail


class EssayContentProvisionedV1(BaseModel):
    """
    Event indicating file content has been extracted and stored.

    Publisher: File Service
    Consumer: Essay Lifecycle Service (ELS)
    Topic: essay.content.provisioned
    Handler: ELS - DefaultBatchCoordinationHandler.handle_essay_content_provisioned()

    Flow (all batches):
    1. Client uploads file via API to File Service
    2. File Service extracts text content and stores in Content Service
    3. File Service publishes this event
    4. ELS assigns content to available essay slot
    5. When all slots filled, ELS publishes BatchContentProvisioningCompletedV1

    This event decouples File Service from internal essay ID management.
    File Service simply announces that content has been provisioned for a batch.
    """

    event: str = Field(default="essay.content.provisioned", description="Event type identifier")
    entity_id: str = Field(description="Batch identifier this content belongs to")
    file_upload_id: str = Field(description="Unique identifier for this file upload")
    original_file_name: str = Field(description="Original uploaded file name")
    raw_file_storage_id: str = Field(
        description="Storage ID of the original, unmodified raw file blob.",
    )
    text_storage_id: str = Field(description="Content Service storage ID for extracted text")
    file_size_bytes: int = Field(description="Size of processed file in bytes")
    content_md5_hash: str | None = Field(default=None, description="MD5 hash of file content")
    correlation_id: UUID = Field(default_factory=uuid4, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EssayValidationFailedV1(BaseModel):
    """
    Event published when file content validation fails.

    Enables ELS to adjust slot expectations and BOS to track
    actual vs expected essay counts for informed pipeline decisions.
    This event is critical for maintaining BOS/ELS coordination when
    validation prevents files from reaching content storage.
    """

    event: str = Field(default="essay.validation.failed", description="Event type identifier")
    entity_id: str = Field(description="Batch identifier this failed validation belongs to")
    file_upload_id: str = Field(description="Unique identifier for this file upload")
    original_file_name: str = Field(description="Name of the file that failed validation")
    raw_file_storage_id: str = Field(
        description="Storage ID of the raw file blob that failed validation.",
    )
    validation_error_code: FileValidationErrorCode = Field(
        description="Specific validation error code from FileValidationErrorCode enum"
    )
    validation_error_detail: ErrorDetail = Field(description="Structured error detail with context")
    file_size_bytes: int = Field(description="Size of the failed file for metrics and analysis")
    correlation_id: UUID = Field(default_factory=uuid4, description="Request correlation ID")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Validation failure timestamp",
    )


# Event envelope integration for file events
class FileEventData(BaseModel):
    """Union type for all file service event data types."""

    essay_content_provisioned: EssayContentProvisionedV1 | None = None
    essay_validation_failed: EssayValidationFailedV1 | None = None
