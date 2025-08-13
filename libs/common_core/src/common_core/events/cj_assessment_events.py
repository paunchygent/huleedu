"""CJ Assessment service event models.

This module defines event contracts for communication between services
regarding Comparative Judgment (CJ) assessment processing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..domain_enums import CourseCode
from ..event_enums import ProcessingEvent
from ..metadata_models import EssayProcessingInputRefV1, SystemProcessingMetadata
from .base_event_models import BaseEventData, ProcessingUpdate

__all__ = [
    "CJAssessmentCompletedV1",
    "CJAssessmentFailedV1",
    "ELS_CJAssessmentRequestV1",
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
        description="Per-essay probability distribution over grades (e.g. {'essay_id': {'A': 0.7, 'B': 0.3}})",
    )
    calibration_info: dict[str, Any] = Field(
        default_factory=dict,
        description="Calibration details including grade centers and boundaries derived from anchors",
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


class ELS_CJAssessmentRequestV1(BaseEventData):
    """Request event from ELS to CJ Assessment Service to perform CJ on a list of essays."""

    event_name: ProcessingEvent = Field(default=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
    system_metadata: SystemProcessingMetadata  # Populated by ELS
    essays_for_cj: list[EssayProcessingInputRefV1]
    language: str
    course_code: CourseCode
    essay_instructions: str
    llm_config_overrides: LLMConfigOverrides | None = Field(
        default=None,
        description="Optional LLM configuration overrides for this assessment batch",
    )
    assignment_id: str | None = Field(
        default=None,
        max_length=100,
        description="Assignment context for grade projection",
    )
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
