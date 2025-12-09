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

    Full implementation will aggregate data from RAS and CMS services.
    """

    batches: list[TeacherBatchItemV1] = Field(default_factory=list)
    total_count: int = 0
