"""Data models for API interactions and internal data transfer.

This module defines Pydantic models for structuring LLM requests and responses,
as well as for internal data transfer between service layers.

Updated for CJ Assessment Service with string-based essay IDs for ELS integration.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from common_core import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from common_core.models.error_models import ErrorDetail as CanonicalErrorDetail
from pydantic import BaseModel, Field, field_validator


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
    error_detail: ErrorDetail | None = None
    raw_llm_response_content: str | None = None


class ErrorDetail(BaseModel):
    """Detailed error information for API responses.

    This model provides structured error information including error codes,
    correlation IDs, and additional context for effective debugging and monitoring.
    """

    error_code: ErrorCode
    message: str
    correlation_id: UUID
    timestamp: datetime
    service: str = "cj_assessment_service"
    details: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """API error response wrapper.

    This model wraps ErrorDetail with an HTTP status code for consistent
    error response format across all API endpoints.
    """

    error: CanonicalErrorDetail
    status_code: int


class FailedComparisonEntry(BaseModel):
    """Represents a failed comparison in the retry pool."""

    essay_a_id: str
    essay_b_id: str
    comparison_task: ComparisonTask
    failure_reason: str
    failed_at: datetime
    retry_count: int = 0
    original_batch_id: str
    correlation_id: UUID


class FailedComparisonPoolStatistics(BaseModel):
    """Statistics for the failed comparison pool."""

    total_failed: int = 0
    retry_attempts: int = 0
    last_retry_batch: str | None = None
    successful_retries: int = 0
    permanently_failed: int = 0


class FailedComparisonPool(BaseModel):
    """Complete failed comparison pool structure."""

    failed_comparison_pool: list[FailedComparisonEntry] = Field(default_factory=list)
    pool_statistics: FailedComparisonPoolStatistics = Field(
        default_factory=FailedComparisonPoolStatistics
    )


class RegisterAnchorRequest(BaseModel):
    """Request payload for registering anchor essays."""

    assignment_id: str
    grade: str
    essay_text: str

    @field_validator("assignment_id", "grade")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value cannot be empty")
        return value

    @field_validator("essay_text")
    @classmethod
    def validate_essay_length(cls, value: str) -> str:
        if len(value) < 100:
            raise ValueError("Essay text too short (min 100 chars)")
        return value
