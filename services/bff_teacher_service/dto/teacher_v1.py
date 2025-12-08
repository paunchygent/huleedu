"""Teacher BFF v1 DTOs.

Screen-specific Data Transfer Objects for teacher dashboard API responses.
These DTOs are view models for frontend consumption - they aggregate data from
multiple backend services into screen-optimized responses.

DTOs use common_core enums for consistency with backend services.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TeacherDashboardResponseV1(BaseModel):
    """Dashboard view: list of batches for teacher.

    Stub implementation for scaffolding phase.
    Full implementation will aggregate data from RAS and CMS services.
    """

    batches: list[dict] = Field(default_factory=list)
    total_count: int = 0
