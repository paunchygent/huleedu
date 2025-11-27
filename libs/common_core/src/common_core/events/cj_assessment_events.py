"""CJ Assessment service event models.

This module defines event contracts for communication between services
regarding Comparative Judgment (CJ) assessment processing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..domain_enums import CourseCode
from ..event_enums import ProcessingEvent
from ..metadata_models import (
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from .base_event_models import BaseEventData, ProcessingUpdate

__all__ = [
    "AssessmentResultV1",
    "CJAssessmentCompletedV1",
    "CJAssessmentFailedV1",
    "ELS_CJAssessmentRequestV1",
    "EssayResultV1",
    "GradeProjectionSummary",
    "LLMConfigOverrides",
]


class GradeProjectionSummary(BaseModel):
    """Grade projection results - always included in CJ assessment results.

    Provides predicted grades based on CJ rankings with statistical confidence scores.
    Grade projections are only calculated when anchor essays are available for calibration.
    """

    projections_available: bool = Field(
        default=False,
        description="True when anchor essays are available and grades can be projected",
    )
    primary_grades: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of essay_id to predicted grade (e.g., 'A', 'B', 'C')",
    )
    confidence_labels: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of essay_id to confidence label ('HIGH', 'MID', 'LOW')",
    )
    confidence_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of essay_id to confidence score (0.0-1.0)",
    )

    # New fields for enriched statistical data
    grade_probabilities: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description=(
            "Per-essay probability distribution over grades "
            "(e.g. {'essay_id': {'A': 0.7, 'B': 0.3}})"
        ),
    )
    calibration_info: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Calibration details including grade centers and boundaries derived from anchors"
        ),
    )
    bt_stats: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Per-essay Bradley-Terry statistics {'essay_id': {'bt_mean': x, 'bt_se': y}}",
    )


class LLMConfigOverrides(BaseModel):
    """LLM configuration overrides for CJ assessment requests.

    Allows dynamic configuration of LLM parameters at request time,
    overriding service defaults for specific assessment batches.
    """

    model_override: str | None = Field(
        default=None,
        description="LLM model to use (e.g., 'gpt-4o-mini')",
    )
    temperature_override: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Temperature for LLM generation",
    )
    max_tokens_override: int | None = Field(
        default=None,
        gt=0,
        description="Maximum tokens for LLM response",
    )
    provider_override: str | None = Field(
        default=None,
        description="LLM provider to use (e.g., 'openai', 'anthropic')",
    )
    system_prompt_override: str | None = Field(
        default=None,
        description="System prompt to force for this batch (caller-supplied instructions).",
    )


class ELS_CJAssessmentRequestV1(BaseEventData):
    """Request event from ELS to CJ Assessment Service to perform CJ on a list of essays."""

    event_name: ProcessingEvent = Field(default=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
    system_metadata: SystemProcessingMetadata  # Populated by ELS
    essays_for_cj: list[EssayProcessingInputRefV1]
    language: str
    course_code: CourseCode
    student_prompt_ref: StorageReferenceMetadata | None = Field(
        default=None,
        description="Content Service reference for the student prompt text",
    )
    llm_config_overrides: LLMConfigOverrides | None = Field(
        default=None,
        description="Optional LLM configuration overrides for this assessment batch",
    )
    assignment_id: str | None = Field(
        default=None,
        max_length=100,
        description="Assignment context for grade projection",
    )

    # Identity fields for credit attribution (Phase 3: Entitlements integration)
    user_id: str = Field(description="User who owns the assessment request")
    org_id: str | None = Field(default=None, description="Organization, if applicable")

    # class_designation: str  # Deferred (YAGNI)


class CJAssessmentCompletedV1(ProcessingUpdate):
    """Result event from CJ Assessment Service to ELS (thin event for state management).

    CRITICAL: This is a thin event following clean architecture principles.
    It contains ONLY state tracking information - NO business data.
    Business data (rankings, scores, grade projections) goes to RAS via AssessmentResultV1.
    """

    event_name: ProcessingEvent = Field(default=ProcessingEvent.CJ_ASSESSMENT_COMPLETED)
    # entity_ref (from BaseEventData) is the BOS Batch ID this result pertains to
    # status (from ProcessingUpdate) indicates outcome (e.g. COMPLETED_SUCCESSFULLY)
    # system_metadata (from ProcessingUpdate) populated by CJ Assessment Service

    cj_assessment_job_id: str  # The internal ID from CJ_BatchUpload, for detailed log/result lookup

    # Clean state tracking field - NO business data
    processing_summary: dict[str, Any] = Field(
        description="Summary of batch processing results for state management",
        default_factory=lambda: {
            "total_essays": 0,
            "successful": 0,
            "failed": 0,
            "successful_essay_ids": [],  # Essay IDs that were successfully assessed
            "failed_essay_ids": [],  # Essay IDs that failed assessment
            "processing_time_seconds": 0.0,
        },
    )


class CJAssessmentFailedV1(ProcessingUpdate):
    """Failure event from CJ Assessment Service to ELS reporting processing failure."""

    event_name: ProcessingEvent = Field(default=ProcessingEvent.CJ_ASSESSMENT_FAILED)
    # entity_ref (from BaseEventData) is the BOS Batch ID
    # status (from ProcessingUpdate) indicates failure
    # system_metadata (from ProcessingUpdate) should contain detailed error_info

    cj_assessment_job_id: str  # Internal CJ Job ID for traceability


# === RICH RESULT EVENT (CJ → RAS) ===


class EssayResultV1(BaseModel):
    """Typed assessment result for individual essay.

    ARCHITECTURAL FOUNDATION: This model establishes the pattern for all assessment
    results across HuleEdu services. Future services (NLP, Spellcheck, AI Feedback)
    will adopt this same structure or extend it, enabling consistent typed models
    throughout the assessment pipeline and Result Aggregator Service.

    This replaces the untyped dict[str, Any] approach with proper validation,
    better IDE support, and schema evolution capabilities.
    """

    essay_id: str = Field(description="Unique identifier for the essay")
    normalized_score: float = Field(
        ge=0.0, le=1.0, description="Normalized score between 0 and 1 for cross-service consistency"
    )
    letter_grade: str = Field(
        pattern=r"^([A-F][+-]?|U)$",
        description="Letter grade (A+, A, A-, B+, B, B-, C+, C, C-, D+, D, D-, F, U)",
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, description="Confidence in the assessment accuracy"
    )
    confidence_label: Literal["HIGH", "MID", "LOW"] = Field(
        description="Human-readable confidence category"
    )
    bt_score: float = Field(description="Bradley-Terry score for comparative ranking")
    rank: int = Field(gt=0, description="Rank position within the assessment batch (1-based)")
    is_anchor: bool = Field(
        default=False, description="Whether this essay serves as an anchor for grade calibration"
    )
    feedback_uri: str | None = Field(
        default=None, description="URI to detailed feedback content (if available and >50KB)"
    )
    metrics_uri: str | None = Field(
        default=None, description="URI to detailed assessment metrics (if available and >50KB)"
    )
    display_name: str | None = Field(
        default=None,
        description=(
            "Human-readable display name for UI purposes (e.g., 'ANCHOR GRADE A' for anchors)"
        ),
    )


class AssessmentResultV1(BaseEventData):
    """Rich assessment result event sent directly to Result Aggregator Service.

    This event contains the full business data from CJ Assessment, including
    scores, grades, and rankings. Published alongside the thin CJAssessmentCompletedV1
    event that goes to ELS for state tracking.
    """

    event_name: ProcessingEvent = Field(default=ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED)

    # Batch identification
    batch_id: str = Field(description="BOS batch ID")
    cj_assessment_job_id: str = Field(description="Internal CJ batch ID")

    # Assignment context (optional for backwards compatibility)
    assignment_id: str | None = Field(
        default=None,
        max_length=100,
        description="Assignment identifier for this assessment batch, if available",
    )

    # Assessment method tracking
    assessment_method: str = Field(description="Method used: cj_assessment, nlp_random_forest, etc")
    model_used: str = Field(description="Specific model: claude-3-opus, gpt-4, etc")
    model_provider: str = Field(description="Provider: anthropic, openai, internal")
    model_version: str | None = Field(default=None, description="Model version if applicable")

    # Essay results (excludes anchor essays) - NOW TYPED!
    essay_results: list[EssayResultV1] = Field(
        description="List of student essay assessment results using typed validation",
        # Replaced dict[str, Any] with EssayResultV1 for:
        # - Proper type safety and IDE support
        # - Runtime validation of all fields
        # - Clear schema documentation
        # - Consistent structure across assessment services
        # - Foundation for future service migrations
    )

    # Assessment metadata
    assessment_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional assessment context",
        # Contains:
        # - anchor_essays_used: int
        # - calibration_method: str (anchor, default)
        # - comparison_count: int
        # - processing_duration_seconds: float
        # - llm_temperature: float
        # - assignment_id: str | None  (legacy location; prefer top-level field)
    )

    # Timestamp
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
