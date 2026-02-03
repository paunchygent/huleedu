"""API models for CJ anchor summary endpoints (admin surfaces).

Used by ENG5 runner preflight to verify that required anchors already exist in CJ.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AnchorSummaryItem(BaseModel):
    """Single anchor reference record."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: int = Field(..., description="Anchor reference primary key")
    assignment_id: str | None = Field(default=None, description="Assignment identifier")
    anchor_label: str = Field(..., min_length=1, description="Anchor label/identifier")
    grade: str = Field(..., min_length=1, description="Known grade for this anchor")
    grade_scale: str = Field(..., min_length=1, description="Grade scale key")
    text_storage_id: str = Field(..., min_length=1, description="Content Service storage id")
    created_at: datetime = Field(..., description="Insertion timestamp")


class AnchorSummaryResponse(BaseModel):
    """Anchor summary for a specific assignment, scoped to the instruction grade_scale."""

    assignment_id: str = Field(..., min_length=1, description="Assignment identifier")
    grade_scale: str = Field(..., min_length=1, description="Instruction-owned grade scale")
    anchor_count: int = Field(ge=0, description="Number of anchors in the instruction grade scale")
    anchors: list[AnchorSummaryItem] = Field(default_factory=list)
    anchor_count_total: int = Field(
        ge=0,
        description="Total anchors for this assignment across all grade_scales",
    )
    anchor_count_by_scale: dict[str, int] = Field(
        default_factory=dict,
        description="Anchor counts per grade_scale for this assignment",
    )
