"""API request and response models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence
from uuid import uuid4

from common_core.pipeline_models import PhaseName

# Use common_core enums directly (no re-exports)
from common_core.status_enums import BatchClientStatus, BatchStatus, ProcessingStage
from pydantic import BaseModel, Field

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
    assignment_id: Optional[str] = None
    overall_status: BatchClientStatus

    # Counts
    essay_count: int
    completed_essay_count: int
    failed_essay_count: int

    # Processing info
    requested_pipeline: Optional[str] = None
    current_phase: Optional[PhaseName] = None

    # Essays with results
    essays: List[EssayResultResponse] = Field(default_factory=list)

    # Metadata
    created_at: datetime
    last_updated: datetime
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    student_prompt_ref: Optional[Dict[str, Any]] = None

    @staticmethod
    def _is_processing_stage_incomplete(value: ProcessingStage | None) -> bool:
        """Return True if a phase is not yet terminal (or missing)."""
        return value is None or value not in ProcessingStage.terminal()

    @classmethod
    def _derive_current_phase_from_essays(cls, essays: Sequence[Any]) -> PhaseName | None:
        """Derive current phase from essay-level processing stages (Phase 4 scope)."""
        if not essays:
            return None

        if any(
            cls._is_processing_stage_incomplete(getattr(essay, "spellcheck_status", None))
            for essay in essays
        ):
            return PhaseName.SPELLCHECK

        if any(
            cls._is_processing_stage_incomplete(getattr(essay, "cj_assessment_status", None))
            for essay in essays
        ):
            return PhaseName.CJ_ASSESSMENT

        return None

    @staticmethod
    def _parse_current_phase_from_metadata(metadata: dict[str, Any]) -> PhaseName | None:
        """Parse a PhaseName from BOS fallback metadata, if present and valid."""
        raw_current_phase = metadata.get("current_phase")
        if not isinstance(raw_current_phase, str):
            return None
        try:
            return PhaseName[raw_current_phase]
        except KeyError:
            return None

    @classmethod
    def _derive_current_phase(
        cls,
        *,
        overall_status: BatchStatus,
        essays: Sequence[Any],
        metadata: dict[str, Any],
    ) -> PhaseName | None:
        """Derive current phase with UX-safe semantics (only while processing pipelines)."""
        if overall_status != BatchStatus.PROCESSING_PIPELINES:
            return None

        essay_phase = cls._derive_current_phase_from_essays(essays)
        if essay_phase is not None or essays:
            return essay_phase

        return cls._parse_current_phase_from_metadata(metadata)

    @classmethod
    def from_domain(cls, batch_result: "BatchResult") -> "BatchStatusResponse":
        """Convert from domain model."""
        # Map database batch status to client-facing API status
        status_mapping = {
            "awaiting_content_validation": BatchClientStatus.PENDING_CONTENT,
            "content_ingestion_failed": BatchClientStatus.FAILED,
            "awaiting_pipeline_configuration": BatchClientStatus.PENDING_CONTENT,
            "ready_for_pipeline_execution": BatchClientStatus.READY,
            "processing_pipelines": BatchClientStatus.PROCESSING,
            "awaiting_student_validation": BatchClientStatus.PROCESSING,
            "validation_timeout_processed": BatchClientStatus.PROCESSING,
            "guest_class_ready": BatchClientStatus.PROCESSING,
            "completed_successfully": BatchClientStatus.COMPLETED_SUCCESSFULLY,
            "completed_with_failures": BatchClientStatus.COMPLETED_WITH_FAILURES,
            "failed_critically": BatchClientStatus.FAILED,
            "cancelled": BatchClientStatus.CANCELLED,
        }

        api_status = status_mapping.get(
            batch_result.overall_status.value,
            BatchClientStatus.PROCESSING,  # Default fallback
        )

        metadata = batch_result.batch_metadata or {}

        return cls(
            batch_id=batch_result.batch_id,
            user_id=batch_result.user_id,
            assignment_id=getattr(batch_result, "assignment_id", None),
            overall_status=api_status,
            essay_count=batch_result.essay_count,
            completed_essay_count=batch_result.completed_essay_count,
            failed_essay_count=batch_result.failed_essay_count,
            requested_pipeline=batch_result.requested_pipeline,
            current_phase=cls._derive_current_phase(
                overall_status=batch_result.overall_status,
                essays=batch_result.essays,
                metadata=metadata,
            ),
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
            student_prompt_ref=metadata.get("student_prompt_ref"),
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
