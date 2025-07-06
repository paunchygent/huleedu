"""Data models for API interactions and internal data transfer.

This module defines Pydantic models for structuring LLM requests and responses,
as well as for internal data transfer between service layers.

Updated for CJ Assessment Service with string-based essay IDs for ELS integration.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from common_core import EssayComparisonWinner


class EssayForComparison(BaseModel):
    """Represents an essay prepared for comparison.

    Uses string ID to match ELS essay IDs (els_essay_id).
    """

    id: str  # Changed from int to str for ELS integration
    text_content: str
    current_bt_score: float | None = None


class LLMAssessmentResponseSchema(BaseModel):
    """Schema for structured LLM responses to essay comparisons."""

    winner: EssayComparisonWinner
    justification: str
    confidence: float | None = Field(None, ge=1.0, le=5.0)


class ComparisonTask(BaseModel):
    """A task for comparing two essays."""

    essay_a: EssayForComparison
    essay_b: EssayForComparison
    prompt: str


class ComparisonResult(BaseModel):
    """The result of a comparison task."""

    task: ComparisonTask
    llm_assessment: LLMAssessmentResponseSchema | None = None
    error_message: str | None = None
    raw_llm_response_content: str | None = None
