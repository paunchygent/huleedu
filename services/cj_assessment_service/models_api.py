"""Data models for API interactions and internal data transfer.

This module defines Pydantic models for structuring LLM requests and responses,
as well as for internal data transfer between service layers.

Updated for CJ Assessment Service with string-based essay IDs for ELS integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from common_core import EssayComparisonWinner
from common_core.error_enums import ErrorCode
from common_core.events.cj_assessment_events import LLMConfigOverrides
from common_core.models.error_models import ErrorDetail as CanonicalErrorDetail
from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class CJLLMComparisonMetadata(BaseModel):
    """Typed metadata adapter for CJ → LLM Provider comparison requests.

    This model centralizes the metadata schema that gets serialized into
    `LLMComparisonRequest.metadata` so we can lock the contract with tests.
    The adapter captures the identifiers CJ needs to round-trip callbacks
    and provides extension hooks for future batching metadata.
    """

    model_config = ConfigDict(extra="allow")

    essay_a_id: str = Field(description="Source essay identifier for comparison slot A")
    essay_b_id: str = Field(description="Source essay identifier for comparison slot B")
    bos_batch_id: str | None = Field(
        default=None,
        description="Optional BOS batch identifier (stringified UUID)",
    )
    comparison_iteration: int | None = Field(
        default=None,
        ge=0,
        description="Optional CJ iteration counter when batching comparisons",
    )
    cj_llm_batching_mode: str | None = Field(
        default=None,
        description=(
            "Planned CJ batching mode hint (per_request|provider_serial_bundle|provider_batch_api)"
        ),
    )

    @classmethod
    def from_comparison_task(
        cls,
        task: ComparisonTask,
        *,
        bos_batch_id: str | None = None,
    ) -> "CJLLMComparisonMetadata":
        """Build metadata for a single comparison task."""
        return cls(
            essay_a_id=task.essay_a.id,
            essay_b_id=task.essay_b.id,
            bos_batch_id=bos_batch_id,
        )

    def to_request_metadata(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Serialize metadata for outbound LLM Provider requests."""
        metadata = self.model_dump(exclude_none=True)
        if extra:
            metadata.update(extra)
        return metadata

    def with_additional_context(self, **context: Any) -> "CJLLMComparisonMetadata":
        """Create a copy with additive metadata while preserving typed fields."""
        payload = self.model_dump(exclude_none=False)
        payload.update(context)
        return CJLLMComparisonMetadata(**payload)


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
    anchor_label: str | None = None
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


@dataclass(frozen=True)
class PromptHydrationFailure:
    """Represents a prompt hydration failure with diagnostic information.

    This dataclass encapsulates failure reasons for prompt fetching operations,
    enabling Result-based error discrimination without raising exceptions.
    """

    reason: str  # "empty_content", "content_service_error", "unexpected_error",  # noqa: E501
    # "batch_creation_hydration_failed"
    storage_id: str | None = None


class CJProcessingMetadata(BaseModel):
    """Typed metadata model for CJ batch processing context.

    Enforces schema for known metadata keys while preventing
    unknown keys from being added during batch creation.
    """

    model_config = ConfigDict(extra="forbid")

    student_prompt_storage_id: str | None = None
    student_prompt_text: str | None = None
    judge_rubric_storage_id: str | None = None
    judge_rubric_text: str | None = None


class OriginalCJRequestMetadata(BaseModel):
    """Persisted snapshot of the runner-supplied CJ request payload."""

    model_config = ConfigDict(extra="forbid")

    assignment_id: str | None = None
    language: str
    course_code: str
    student_prompt_text: str | None = None
    student_prompt_storage_id: str | None = None
    judge_rubric_text: str | None = None
    judge_rubric_storage_id: str | None = None
    llm_config_overrides: LLMConfigOverrides | None = None
    batch_config_overrides: dict[str, Any] | None = None
    max_comparisons_override: int | None = Field(None, ge=1)
    user_id: str | None = None
    org_id: str | None = None


class CJEessayMetadata(BaseModel):
    """Base metadata overlay for essays stored inside CJ processing tables."""

    model_config = ConfigDict(extra="forbid")

    is_anchor: bool | None = None
    anchor_grade: str | None = None
    known_grade: str | None = None
    anchor_ref_id: str | None = None
    text_storage_id: str | None = None


class CJAnchorMetadata(CJEessayMetadata):
    """Typed metadata overlay used for anchor essays."""

    is_anchor: bool = True
    anchor_label: str | None = None


class EssayToProcess(BaseModel):
    """Reference to an essay for CJ processing."""

    els_essay_id: str = Field(description="ELS essay identifier")
    text_storage_id: str = Field(description="Content Service storage ID")


class CJAssessmentRequestData(BaseModel):
    """Typed request data for CJ assessment workflow.

    This model replaces the untyped dict[str, Any] used throughout the
    CJ assessment workflow, providing runtime validation and better type safety.
    """

    model_config = ConfigDict(extra="forbid")

    # Required fields (always present)
    bos_batch_id: str = Field(description="BOS batch identifier")
    assignment_id: str | None = Field(None, description="Assignment identifier")
    essays_to_process: list[EssayToProcess] = Field(description="Essays to process in this batch")
    language: str = Field(description="Language code (e.g., 'en', 'sv')")
    course_code: str = Field(description="Course code enum value")

    # Optional prompt context fields
    student_prompt_text: str | None = Field(
        None, description="Hydrated student assignment prompt text"
    )
    student_prompt_storage_id: str | None = Field(
        None, description="Content Service storage ID for student prompt"
    )
    judge_rubric_text: str | None = Field(None, description="Hydrated judge rubric text")
    judge_rubric_storage_id: str | None = Field(
        None, description="Content Service storage ID for judge rubric"
    )

    # Optional configuration overrides
    llm_config_overrides: LLMConfigOverrides | None = Field(
        None, description="LLM parameter overrides for this batch"
    )
    batch_config_overrides: dict[str, Any] | None = Field(
        None, description="Batch processing configuration overrides"
    )
    max_comparisons_override: int | None = Field(
        None, ge=1, description="Runner-specified comparison limit"
    )

    # Optional identity fields (Phase 3: Entitlements)
    user_id: str | None = Field(None, description="User ID for credit attribution")
    org_id: str | None = Field(None, description="Organization ID for credit attribution")
