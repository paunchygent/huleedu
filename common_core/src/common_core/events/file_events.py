"""
File Service event models for HuleEdu microservices.

This module contains events related to file processing and content provisioning
by the File Service. These events are part of the file processing domain,
separate from batch coordination concerns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ..metadata_models import EntityReference, StorageReferenceMetadata, SystemProcessingMetadata


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


class EssayContentProvisionedV1(BaseModel):
    """
    Event sent by File Service when content is successfully processed and stored.

    This event replaces EssayContentReady to decouple File Service from internal
    essay ID management. File Service simply announces that content has been
    provisioned for a batch.
    """

    event: str = Field(default="essay.content.provisioned", description="Event type identifier")
    batch_id: str = Field(description="Batch identifier this content belongs to")
    original_file_name: str = Field(description="Original uploaded file name")
    text_storage_id: str = Field(description="Content Service storage ID for extracted text")
    file_size_bytes: int = Field(description="Size of processed file in bytes")
    content_md5_hash: Optional[str] = Field(default=None, description="MD5 hash of file content")
    correlation_id: Optional[UUID] = Field(default=None, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Event envelope integration for file events
class FileEventData(BaseModel):
    """Union type for all file service event data types."""

    essay_content_ready: Optional[EssayContentReady] = None
    essay_content_provisioned: Optional[EssayContentProvisionedV1] = None
