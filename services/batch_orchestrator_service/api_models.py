"""API request models for Batch Orchestrator Service."""

from __future__ import annotations

from common_core.domain_enums import CourseCode
from pydantic import BaseModel, Field, model_validator


class BatchRegistrationRequestV1(BaseModel):
    """Lean batch registration model - captures only orchestration essentials.

    Educational context (teacher_name, user_id, student data) is deferred to
    Class Management Service and provided later via enhanced BatchEssaysReady events.
    This maintains proper service boundaries and single source of truth principles.
    """

    expected_essay_count: int = Field(
        ...,
        description="Number of essays expected in this batch.",
        gt=0,
    )
    essay_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of unique essay IDs. If not provided, BOS will auto-generate IDs."
        ),
        min_length=1,
    )

    # Orchestration essentials (BOS responsibility)
    course_code: CourseCode = Field(
        ...,
        description="Course code associated with this batch (e.g., SV1, ENG5).",
    )
    essay_instructions: str = Field(
        ...,
        description="Instructions provided for the essay assignment.",
    )
    user_id: str = Field(
        ...,
        description="The ID of the user who owns this batch (from API Gateway JWT).",
    )
    org_id: str | None = Field(
        default=None,
        description="Organization ID for credit attribution, None for individual users (from API Gateway JWT).",
    )
    class_id: str | None = Field(
        default=None,
        description=(
            "Class ID for REGULAR batches requiring student matching, "
            "None for GUEST batches. Provided by API Gateway based on authentication context."
        ),
    )

    # CJ Assessment pipeline parameters
    enable_cj_assessment: bool = Field(
        default=False,
        description="Whether to include CJ assessment in the processing pipeline.",
    )
    cj_default_llm_model: str | None = Field(
        default=None,
        description="Default LLM model for CJ assessment (e.g., 'gpt-4o-mini').",
    )
    cj_default_temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Default temperature for CJ assessment LLM.",
    )

    @model_validator(mode="after")
    def validate_essay_count_consistency(self) -> BatchRegistrationRequestV1:
        """Validate that essay_ids length matches expected_essay_count when provided."""
        if self.essay_ids is not None:
            if len(self.essay_ids) != self.expected_essay_count:
                raise ValueError(
                    f"Length of essay_ids ({len(self.essay_ids)}) must match "
                    f"expected_essay_count ({self.expected_essay_count})",
                )
        return self
