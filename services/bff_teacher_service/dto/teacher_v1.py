"""Teacher BFF v1 DTOs.

Screen-specific Data Transfer Objects for teacher dashboard API responses.
These DTOs are view models for frontend consumption - they aggregate data from
multiple backend services into screen-optimized responses.

DTOs use common_core enums for consistency with backend services.
"""

from __future__ import annotations

from datetime import datetime

from common_core.status_enums import BatchClientStatus
from pydantic import BaseModel, Field


class TeacherBatchItemV1(BaseModel):
    """Single batch item for the teacher dashboard list.

    Aggregates data from:
    - RAS: status, counts, timestamps
    - CMS: class_name
    - Content/RAS: title (from assignment or prompt)
    """

    batch_id: str
    title: str = "Untitled Batch"
    class_name: str | None = None
    status: BatchClientStatus
    total_essays: int = 0
    completed_essays: int = 0
    created_at: datetime


class TeacherDashboardResponseV1(BaseModel):
    """Dashboard view: list of batches for teacher.

    Aggregates data from RAS and CMS services.
    """

    batches: list[TeacherBatchItemV1] = Field(default_factory=list)
    total_count: int = Field(default=0, description="Total batches matching query")
    limit: int = Field(default=20, description="Page size requested")
    offset: int = Field(default=0, description="Number of batches skipped")


# --- Internal response models for backend service deserialization ---


class BatchSummaryV1(BaseModel):
    """RAS batch summary from internal API response.

    Used for deserialization from RAS GET /internal/v1/batches/user/{user_id}.
    Maps to internal status values (not client-facing statuses).
    """

    batch_id: str
    user_id: str
    overall_status: str
    essay_count: int = 0
    completed_essay_count: int = 0
    failed_essay_count: int = 0
    created_at: datetime
    assignment_id: str | None = None


class ClassInfoV1(BaseModel):
    """CMS class info from internal API response.

    Used for deserialization from CMS GET /internal/v1/batches/class-info.
    """

    class_id: str
    class_name: str


class PaginationV1(BaseModel):
    """Pagination metadata from backend responses."""

    limit: int
    offset: int
    total: int
