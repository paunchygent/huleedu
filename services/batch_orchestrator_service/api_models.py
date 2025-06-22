"""API request models for Batch Orchestrator Service."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class BatchRegistrationRequestV1(BaseModel):
    """Request model for batch registration endpoint.

    This model captures all the context needed for batch processing,
    including course information and essay details.
    """

    expected_essay_count: int = Field(
        ..., description="Number of essays expected in this batch.", gt=0,
    )
    essay_ids: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of unique essay IDs. If not provided, BOS will auto-generate IDs."
        ),
        min_length=1,
    )
    course_code: str = Field(
        ..., description="Course code associated with this batch (e.g., SV1, ENG5).",
    )
    class_designation: str = Field(
        ..., description="Class or group designation (e.g., 'Class 9A', 'Group Blue').",
    )
    teacher_name: str = Field(..., description="Name of the teacher or instructor for this batch.")
    essay_instructions: str = Field(
        ..., description="Instructions provided for the essay assignment.",
    )
    # CJ Assessment optional parameters (Sub-task 2.1.1)
    enable_cj_assessment: bool = Field(
        default=False, description="Whether to include CJ assessment in the processing pipeline.",
    )
    cj_default_llm_model: str | None = Field(
        default=None, description="Default LLM model for CJ assessment (e.g., 'gpt-4o-mini').",
    )
    cj_default_temperature: float | None = Field(
        default=None, ge=0.0, le=2.0, description="Default temperature for CJ assessment LLM.",
    )
    user_id: str | None = Field(
        default=None, description="The ID of the user who owns this batch.",
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
