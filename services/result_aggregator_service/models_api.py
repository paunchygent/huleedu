"""API request and response models."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .enums_api import BatchStatus, ProcessingPhase

if TYPE_CHECKING:
    from .models_db import BatchResult


class EssayResultResponse(BaseModel):
    """Essay result in API response."""

    essay_id: str
    filename: Optional[str] = None

    # Current service results
    spellcheck_status: Optional[str] = None
    spellcheck_correction_count: Optional[int] = None
    spellcheck_corrected_text_storage_id: Optional[str] = None
    spellcheck_error: Optional[str] = None

    cj_assessment_status: Optional[str] = None
    cj_rank: Optional[int] = None
    cj_score: Optional[float] = None
    cj_assessment_error: Optional[str] = None

    # Timestamps
    last_updated: datetime


class BatchStatusResponse(BaseModel):
    """Comprehensive batch status response."""

    batch_id: str
    user_id: str  # Critical for API Gateway security checks
    overall_status: BatchStatus

    # Counts
    essay_count: int
    completed_essay_count: int
    failed_essay_count: int

    # Processing info
    requested_pipeline: Optional[str] = None
    current_phase: Optional[ProcessingPhase] = None

    # Essays with results
    essays: List[EssayResultResponse] = Field(default_factory=list)

    # Metadata
    created_at: datetime
    last_updated: datetime
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None

    @classmethod
    def from_domain(cls, batch_result: "BatchResult") -> "BatchStatusResponse":
        """Convert from domain model."""
        # Map database batch status (lowercase) to API batch status (uppercase)
        status_mapping = {
            "awaiting_content_validation": BatchStatus.REGISTERED,
            "content_ingestion_failed": BatchStatus.FAILED,
            "awaiting_pipeline_configuration": BatchStatus.REGISTERED,
            "ready_for_pipeline_execution": BatchStatus.REGISTERED,
            "processing_pipelines": BatchStatus.PROCESSING,
            "awaiting_student_validation": BatchStatus.PROCESSING,
            "validation_timeout_processed": BatchStatus.PROCESSING,
            "guest_class_ready": BatchStatus.PROCESSING,
            "completed_successfully": BatchStatus.COMPLETED,
            "completed_with_failures": BatchStatus.PARTIALLY_COMPLETED,
            "failed_critically": BatchStatus.FAILED,
            "cancelled": BatchStatus.CANCELLED,
        }

        api_status = status_mapping.get(
            batch_result.overall_status.value,
            BatchStatus.PROCESSING,  # Default fallback
        )

        return cls(
            batch_id=batch_result.batch_id,
            user_id=batch_result.user_id,
            overall_status=api_status,
            essay_count=batch_result.essay_count,
            completed_essay_count=batch_result.completed_essay_count,
            failed_essay_count=batch_result.failed_essay_count,
            requested_pipeline=batch_result.requested_pipeline,
            current_phase=ProcessingPhase.SPELLCHECK,  # Derive from data
            essays=[
                EssayResultResponse(
                    essay_id=essay.essay_id,
                    filename=essay.filename,
                    spellcheck_status=essay.spellcheck_status.value
                    if essay.spellcheck_status
                    else None,
                    spellcheck_correction_count=essay.spellcheck_correction_count,
                    spellcheck_corrected_text_storage_id=essay.spellcheck_corrected_text_storage_id,
                    spellcheck_error=essay.spellcheck_error,
                    cj_assessment_status=essay.cj_assessment_status.value
                    if essay.cj_assessment_status
                    else None,
                    cj_rank=essay.cj_rank,
                    cj_score=essay.cj_score,
                    cj_assessment_error=essay.cj_assessment_error,
                    last_updated=essay.updated_at,
                )
                for essay in batch_result.essays
            ],
            created_at=batch_result.created_at,
            last_updated=batch_result.updated_at,
            processing_started_at=batch_result.processing_started_at,
            processing_completed_at=batch_result.processing_completed_at,
        )


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    details: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None
