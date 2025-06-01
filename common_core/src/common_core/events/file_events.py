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


class EssayContentProvisionedV1(BaseModel):
    """
    Event sent by File Service when content is successfully processed and stored.

    This event decouples File Service from internal
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

    essay_content_provisioned: Optional[EssayContentProvisionedV1] = None
