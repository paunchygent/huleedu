"""API models for CJ assessment instruction administration."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssessmentInstructionBase(BaseModel):
    """Shared fields for assessment instruction payloads."""

    model_config = ConfigDict(str_strip_whitespace=True)

    assignment_id: str | None = Field(
        default=None,
        description="Assignment identifier (mutually exclusive with course_id)",
    )
    course_id: str | None = Field(
        default=None,
        description="Course identifier used when assignment_id is not provided",
    )
    instructions_text: str = Field(
        ..., min_length=10, description="Canonical instructions presented to assessors"
    )
    grade_scale: str = Field(..., description="Registered grade scale key")

    @model_validator(mode="after")
    def _xor_scope(self) -> "AssessmentInstructionBase":
        if bool(self.assignment_id) == bool(self.course_id):
            raise ValueError("Provide exactly one of assignment_id or course_id")
        return self


class AssessmentInstructionUpsertRequest(AssessmentInstructionBase):
    """Request payload for creating or updating instructions."""


class AssessmentInstructionResponse(AssessmentInstructionBase):
    """Response model for persisted instructions."""

    id: int
    created_at: datetime


class AssessmentInstructionListResponse(BaseModel):
    """Paginated listing response."""

    items: list[AssessmentInstructionResponse]
    total: int
    page: int = Field(ge=1, description="Current page (1-indexed)")
    page_size: int = Field(ge=1, le=200, description="Number of records per page")
