from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from common_core.domain_enums import CourseCode

"""Inter-service HTTP contract models for batch registration.

This model is shared across services to enforce a single, explicit contract
for batch registration requests. It is intentionally placed in common_core
per Rule 020 to avoid drift and duplicated definitions.
"""


class BatchRegistrationRequestV1(BaseModel):
    """Inter-service contract for batch registration.

    Used by:
    - API Gateway: Enriches with identity and forwards to BOS
    - BOS: Receives and processes registration

    Identity Threading:
    - user_id: Required, from JWT sub claim
    - org_id: Optional, from JWT org claims (org-first attribution)

    Version History:
    - v1: Initial version with org_id support
    """

    expected_essay_count: int = Field(
        ..., description="Number of essays expected in this batch.", gt=0
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
        ..., description="Course code associated with this batch (e.g., SV1, ENG5)."
    )
    essay_instructions: str = Field(
        ..., description="Instructions provided for the essay assignment."
    )
    user_id: str = Field(
        ..., description="The ID of the user who owns this batch (from API Gateway JWT)."
    )
    org_id: str | None = Field(
        default=None,
        description=(
            "Organization ID for credit attribution, None for individual users "
            "(from API Gateway JWT)."
        ),
    )
    class_id: str | None = Field(
        default=None,
        description=(
            "Class ID for REGULAR batches requiring student matching, "
            "None for GUEST batches. Provided by API Gateway."
        ),
    )

    # CJ Assessment pipeline parameters
    enable_cj_assessment: bool = Field(
        default=False,
        description="Whether to include CJ assessment in the processing pipeline.",
    )
    cj_default_llm_model: str | None = Field(
        default=None, description="Default LLM model for CJ assessment (e.g., 'gpt-4o-mini')."
    )
    cj_default_temperature: float | None = Field(
        default=None, ge=0.0, le=2.0, description="Default temperature for CJ assessment LLM."
    )

    @model_validator(mode="after")
    def validate_essay_count_consistency(self) -> BatchRegistrationRequestV1:
        if self.essay_ids is not None and len(self.essay_ids) != self.expected_essay_count:
            raise ValueError(
                "Length of essay_ids ({}) must match expected_essay_count ({})".format(
                    len(self.essay_ids), self.expected_essay_count
                )
            )
        return self
