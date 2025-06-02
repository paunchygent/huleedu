"""API request models for Batch Orchestrator Service."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BatchRegistrationRequestV1(BaseModel):
    """Request model for batch registration endpoint.

    This model captures all the context needed for batch processing,
    including course information and essay details.
    """

    expected_essay_count: int = Field(
        ..., description="Number of essays expected in this batch.", gt=0
    )
    essay_ids: List[str] = Field(
        ...,
        description="List of unique essay IDs that will be processed in this batch.",
        min_length=1,
    )
    course_code: str = Field(
        ..., description="Course code associated with this batch (e.g., SV1, ENG5)."
    )
    class_designation: str = Field(
        ..., description="Class or group designation (e.g., 'Class 9A', 'Group Blue')."
    )
    essay_instructions: str = Field(
        ..., description="Instructions provided for the essay assignment."
    )
    # CJ Assessment optional parameters (Sub-task 2.1.1)
    enable_cj_assessment: bool = Field(
        default=False, description="Whether to include CJ assessment in the processing pipeline."
    )
    cj_default_llm_model: Optional[str] = Field(
        default=None, description="Default LLM model for CJ assessment (e.g., 'gpt-4o-mini')."
    )
    cj_default_temperature: Optional[float] = Field(
        default=None, ge=0.0, le=2.0, description="Default temperature for CJ assessment LLM."
    )


class BatchStatusResponseV1(BaseModel):
    """Response model for batch status endpoint.

    This model provides comprehensive status information for all pipeline phases.
    """

    batch_id: str = Field(..., description="Unique identifier for the batch.")
    overall_status: str = Field(..., description="Overall batch processing status.")

    # Pipeline phase statuses
    spellcheck_status: str = Field(..., description="Status of spellcheck pipeline phase.")
    cj_assessment_status: str = Field(..., description="Status of CJ assessment pipeline phase.")

    # Timestamps
    created_at: Optional[str] = Field(None, description="Batch creation timestamp.")
    last_updated_at: Optional[str] = Field(None, description="Last status update timestamp.")

    # Processing details
    total_essays: int = Field(..., description="Total number of essays in the batch.")
    pipeline_details: dict = Field(
        default_factory=dict, description="Detailed pipeline state information."
    )
