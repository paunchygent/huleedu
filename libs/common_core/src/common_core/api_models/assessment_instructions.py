"""API models for CJ assessment instruction administration.

Admin workflow: Centralized assignment configuration (instructions + scale + prompt refs).
User workflow: Ad-hoc batch registration with direct prompt upload (bypasses this).

`student_prompt_storage_id` enables admins to associate prompts with assignment_id
(stored by reference in Content Service, not in CJ database). Phase 4 adds dedicated
prompt upload endpoints; currently admins provide pre-obtained storage_id.
"""

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
    student_prompt_storage_id: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Content Service storage reference for student prompt. Optional. "
            "Enables assignment-scoped prompt management (admin workflow). "
            "User ad-hoc batches provide prompt refs directly, bypassing this."
        ),
    )

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


class StudentPromptUploadRequest(BaseModel):
    """Request payload for uploading student prompt to assignment."""

    model_config = ConfigDict(str_strip_whitespace=True)

    assignment_id: str = Field(min_length=1, description="Assignment identifier")
    prompt_text: str = Field(
        min_length=10, description="Student prompt text to upload to Content Service"
    )


class StudentPromptResponse(BaseModel):
    """Response model for student prompt with full instruction context."""

    assignment_id: str
    student_prompt_storage_id: str
    prompt_text: str
    instructions_text: str
    grade_scale: str
    created_at: datetime


class JudgeRubricUploadRequest(BaseModel):
    """Request payload for uploading judge rubric to assignment."""

    model_config = ConfigDict(str_strip_whitespace=True)

    assignment_id: str = Field(min_length=1, description="Assignment identifier")
    rubric_text: str = Field(
        min_length=10, description="Judge rubric text to upload to Content Service"
    )


class JudgeRubricResponse(BaseModel):
    """Response model for judge rubric with full instruction context."""

    assignment_id: str
    judge_rubric_storage_id: str
    rubric_text: str
    instructions_text: str
    grade_scale: str
    created_at: datetime
