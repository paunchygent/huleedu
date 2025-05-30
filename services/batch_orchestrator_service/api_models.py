"""API request models for Batch Orchestrator Service."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class BatchRegistrationRequestV1(BaseModel):
    """Request model for batch registration endpoint.

    This model captures all the context needed for batch processing,
    including course information and essay details.
    """

    expected_essay_count: int = Field(
        ...,
        description="Number of essays expected in this batch.",
        gt=0
    )
    essay_ids: List[str] = Field(
        ...,
        description="List of unique essay IDs that will be processed in this batch.",
        min_length=1
    )
    course_code: str = Field(
        ...,
        description="Course code associated with this batch (e.g., SV1, ENG5)."
    )
    class_designation: str = Field(
        ...,
        description="Class or group designation (e.g., 'Class 9A', 'Group Blue')."
    )
    essay_instructions: str = Field(
        ...,
        description="Instructions provided for the essay assignment."
    )
