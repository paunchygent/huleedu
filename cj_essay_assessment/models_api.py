"""Data models for API interactions and internal data transfer.

This module defines Pydantic models for structuring LLM requests and responses,
as well as for internal data transfer between service layers.
"""

from typing import Literal

from pydantic import BaseModel, Field


class EssayForComparison(BaseModel):
    """Represents an essay prepared for comparison."""

    id: int
    original_filename: str
    text_content: str
    current_bt_score: float | None = None


class LLMAssessmentResponseSchema(BaseModel):
    """Schema for structured LLM responses to essay comparisons."""

    winner: Literal["Essay A", "Essay B", "Error"]
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
    raw_llm_response_content: str | None = None
    error_message: str | None = None
    from_cache: bool = False
    prompt_hash: str | None = None
