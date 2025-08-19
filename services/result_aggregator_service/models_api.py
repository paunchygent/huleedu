"""API request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from services.result_aggregator_service.enums_api import BatchStatus, ProcessingPhase

if TYPE_CHECKING:
    from services.result_aggregator_service.models_db import BatchResult


class EssayResultResponse(BaseModel):
    """Essay result in API response."""

    essay_id: str
    filename: Optional[str] = None
    file_upload_id: Optional[str] = None  # Added for complete traceability

    # Current service results
    spellcheck_status: Optional[str] = None
    spellcheck_correction_count: Optional[int] = None
    spellcheck_corrected_text_storage_id: Optional[str] = None
    spellcheck_error_detail: Optional[Dict[str, Any]] = None

    cj_assessment_status: Optional[str] = None
    cj_rank: Optional[int] = None
    cj_score: Optional[float] = None
    cj_assessment_error_detail: Optional[Dict[str, Any]] = None

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
        # Map database batch status to client-facing API status
        status_mapping = {
            "awaiting_content_validation": BatchStatus.PENDING_CONTENT,
            "content_ingestion_failed": BatchStatus.FAILED,
            "awaiting_pipeline_configuration": BatchStatus.PENDING_CONTENT,
            "ready_for_pipeline_execution": BatchStatus.READY,
            "processing_pipelines": BatchStatus.PROCESSING,
            "awaiting_student_validation": BatchStatus.PROCESSING,
            "validation_timeout_processed": BatchStatus.PROCESSING,
            "guest_class_ready": BatchStatus.PROCESSING,
            "completed_successfully": BatchStatus.COMPLETED_SUCCESSFULLY,
            "completed_with_failures": BatchStatus.COMPLETED_WITH_FAILURES,
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
                    file_upload_id=essay.file_upload_id,  # Include for traceability
                    spellcheck_status=essay.spellcheck_status.value
                    if essay.spellcheck_status
                    else None,
                    spellcheck_correction_count=essay.spellcheck_correction_count,
                    spellcheck_corrected_text_storage_id=essay.spellcheck_corrected_text_storage_id,
                    spellcheck_error_detail=essay.spellcheck_error_detail,
                    cj_assessment_status=essay.cj_assessment_status.value
                    if essay.cj_assessment_status
                    else None,
                    cj_rank=essay.cj_rank,
                    cj_score=essay.cj_score,
                    cj_assessment_error_detail=essay.cj_assessment_error_detail,
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
    """Standard error response with structured error details."""

    error_code: str
    message: str
    correlation_id: str = Field(default_factory=lambda: str(uuid4()))
    service: str
    operation: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = Field(default_factory=dict)
