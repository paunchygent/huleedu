"""common_core.pipeline_models – Fine-grained batch pipeline state machine"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PhaseName(str, Enum):
    """
    Enum defining all valid pipeline phase names for type-safe orchestration.

    This enum is used as keys in the phase_initiators_map, within ProcessingPipelineState,
    and for validating requested_pipelines values, eliminating magic strings and
    providing compile-time safety.
    """

    SPELLCHECK = "spellcheck"
    AI_FEEDBACK = "ai_feedback"
    CJ_ASSESSMENT = "cj_assessment"
    NLP = "nlp"


class PipelineExecutionStatus(str, Enum):
    REQUESTED_BY_USER = "requested_by_user"
    PENDING_DEPENDENCIES = "pending_dependencies"
    DISPATCH_INITIATED = "dispatch_initiated"
    IN_PROGRESS = "in_progress"
    COMPLETED_SUCCESSFULLY = "completed_successfully"
    COMPLETED_WITH_PARTIAL_SUCCESS = "completed_with_partial_success"
    FAILED = "failed"
    SKIPPED_DUE_TO_DEPENDENCY_FAILURE = "skipped_due_to_dependency_failure"
    SKIPPED_BY_USER_CONFIG = "skipped_by_user_config"
    CANCELLED = "cancelled"


class EssayProcessingCounts(BaseModel):
    total: int = 0
    pending_dispatch_or_processing: int = 0
    successful: int = 0
    failed: int = 0


class PipelineStateDetail(BaseModel):
    status: PipelineExecutionStatus = PipelineExecutionStatus.REQUESTED_BY_USER
    essay_counts: EssayProcessingCounts = Field(default_factory=EssayProcessingCounts)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_info: Optional[Dict[str, Any]] = None
    progress_percentage: Optional[float] = None


class ProcessingPipelineState(BaseModel):
    """Whole-batch perspective of every requested pipeline."""

    batch_id: str
    requested_pipelines: List[str]
    spellcheck: Optional[PipelineStateDetail] = Field(default_factory=PipelineStateDetail)
    nlp_metrics: Optional[PipelineStateDetail] = Field(default_factory=PipelineStateDetail)
    ai_feedback: Optional[PipelineStateDetail] = Field(default_factory=PipelineStateDetail)
    ai_editor_revision: Optional[PipelineStateDetail] = Field(default_factory=PipelineStateDetail)
    grammar_check: Optional[PipelineStateDetail] = Field(default_factory=PipelineStateDetail)
    cj_assessment: Optional[PipelineStateDetail] = Field(default_factory=PipelineStateDetail)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_pipeline(self, name: str) -> Optional[PipelineStateDetail]:
        pipeline_name_attr = name.lower().replace("-", "_")
        return getattr(self, pipeline_name_attr, None)
