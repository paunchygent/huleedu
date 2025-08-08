"""Assessment result events for Result Aggregator Service (RAS)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from common_core.event_enums import ProcessingEvent
from common_core.events.base import BaseEventData


class AssessmentResultV1(BaseEventData):
    """Rich assessment result event sent directly to Result Aggregator Service."""
    
    event_name: ProcessingEvent = Field(default=ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED)
    
    # Batch identification
    batch_id: str = Field(description="BOS batch ID")
    cj_assessment_job_id: str = Field(description="Internal CJ batch ID")
    
    # Assessment method tracking
    assessment_method: str = Field(description="Method used: cj_assessment, nlp_random_forest, etc")
    model_used: str = Field(description="Specific model: claude-3-opus, gpt-4, etc")
    model_provider: str = Field(description="Provider: anthropic, openai, internal")
    model_version: str | None = Field(default=None, description="Model version if applicable")
    
    # Essay results (excludes anchor essays)
    essay_results: list[dict[str, Any]] = Field(
        description="List of student essay assessment results",
        # Each dict contains:
        # - essay_id: str
        # - normalized_score: float (0.0-1.0)
        # - letter_grade: str (A, B, C, etc)
        # - confidence_score: float (0.0-1.0)
        # - confidence_label: str (HIGH, MID, LOW)
        # - bt_score: float (Bradley-Terry score)
        # - rank: int
        # - is_anchor: bool (always False for student essays)
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
        # - assignment_id: str | None
    )
    
    # Timestamp
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))