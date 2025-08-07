"""Result Aggregator Service event models.

This module defines event contracts for result aggregation and
batch completion notifications.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..event_enums import ProcessingEvent
from ..status_enums import BatchStatus
from .base_event_models import ProcessingUpdate

__all__ = [
    "BatchResultsReadyV1",
    "BatchAssessmentCompletedV1",
    "PhaseResultSummary",
]


class PhaseResultSummary(BaseModel):
    """Summary of results for a processing phase."""

    phase_name: str
    status: str
    completed_count: int
    failed_count: int
    processing_time_seconds: float | None = None


class BatchResultsReadyV1(ProcessingUpdate):
    """Batch processing completed with all results available.

    Published when all processing phases are complete and results are
    ready for teacher review. This is a thin event - detailed results
    can be fetched via the RAS query API.
    """

    event_name: ProcessingEvent = Field(default=ProcessingEvent.BATCH_RESULTS_READY)
    batch_id: str
    user_id: str
    total_essays: int
    completed_essays: int
    phase_results: dict[str, PhaseResultSummary]
    overall_status: BatchStatus
    processing_duration_seconds: float


class BatchAssessmentCompletedV1(ProcessingUpdate):
    """CJ Assessment phase completed for batch.

    Published when the CJ Assessment service completes ranking/scoring
    for a batch of essays. This is a thin event - detailed rankings
    can be fetched via the CJ Assessment or RAS query APIs.
    """

    event_name: ProcessingEvent = Field(default=ProcessingEvent.BATCH_ASSESSMENT_COMPLETED)
    batch_id: str
    user_id: str
    assessment_job_id: str
    rankings_summary: list[dict[str, Any]]  # Thin event, details via API
