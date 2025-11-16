"""Fine-grained batch pipeline state machine contracts.

This module hosts typed contracts consumed by the Batch Orchestrator Service
(BOS), Batch Conductor Service (BCS), Result Aggregator Service (RAS), and
WebSocket Service. The models document how orchestration phases progress across
the ``PhaseName`` enum and :class:`PipelineExecutionStatus` state machine. They
complement the diagrams in ``libs/common_core/docs/status-state-machines.md`` and
should be kept in sync whenever orchestration semantics evolve.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PhaseName(str, Enum):
    """All valid pipeline phase names for BOS/BCS orchestration.

    The enum provides type-safe keys for ``phase_initiators_map`` definitions and
    :class:`ProcessingPipelineState` attributes, eliminating magic strings when
    publishing pipeline events or storing requested pipelines in BOS.
    """

    SPELLCHECK = "spellcheck"
    AI_FEEDBACK = "ai_feedback"
    CJ_ASSESSMENT = "cj_assessment"
    NLP = "nlp"
    STUDENT_MATCHING = "student_matching"


class PipelineExecutionStatus(str, Enum):
    """Pipeline phase execution status for BOS/BCS orchestration and WebSocket notifications.

    State Transition Flow:
    1. REQUESTED_BY_USER → Initial state when pipeline requested by client
    2. PENDING_DEPENDENCIES → Waiting for prerequisite phases (e.g., spellcheck before NLP)
    3. DISPATCH_INITIATED → BCS has initiated phase (published initiate command)
    4. IN_PROGRESS → Service is processing essays (reported via phase completion events)
    5. Terminal states:
       - COMPLETED_SUCCESSFULLY → All essays processed successfully
       - COMPLETED_WITH_PARTIAL_SUCCESS → Some essays succeeded, some failed
       - FAILED → All essays failed or critical service error
       - SKIPPED_DUE_TO_DEPENDENCY_FAILURE → Prerequisite phase failed, skip this phase
       - SKIPPED_BY_USER_CONFIG → User chose not to run this phase
       - CANCELLED → User cancelled batch before phase completion

    Terminal States: COMPLETED_*, FAILED, SKIPPED_*, CANCELLED
    Non-Terminal States: REQUESTED_BY_USER, PENDING_DEPENDENCIES, DISPATCH_INITIATED, IN_PROGRESS

    Usage:
    - BOS/BCS: Orchestration state machine tracking
    - WebSocket: Real-time progress notifications to clients
    - Result Aggregator: Determining batch completion status
    """

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
    """Granular essay-level processing counts within a pipeline phase.

    Tracks how many essays in a batch are at each processing stage within
    a specific phase (e.g., spellcheck, NLP). Used for progress tracking
    and determining phase completion criteria.
    """

    total: int = Field(default=0, description="Total number of essays in the batch for this phase")
    pending_dispatch_or_processing: int = Field(
        default=0, description="Essays not yet dispatched or currently being processed"
    )
    successful: int = Field(default=0, description="Essays that completed processing successfully")
    failed: int = Field(
        default=0, description="Essays that failed processing (validation, service errors, etc.)"
    )


class PipelineStateDetail(BaseModel):
    """Detailed state tracking for a single pipeline phase execution.

    Combines phase-level status (e.g., IN_PROGRESS, COMPLETED) with essay-level
    granularity (how many essays succeeded/failed). Updated by BCS as phase
    progresses and used for WebSocket notifications and batch completion logic.
    """

    status: PipelineExecutionStatus = Field(
        default=PipelineExecutionStatus.REQUESTED_BY_USER,
        description=(
            "Current execution status of this pipeline phase. "
            "See PipelineExecutionStatus for state transitions."
        ),
    )
    essay_counts: EssayProcessingCounts = Field(
        default_factory=EssayProcessingCounts,
        description=(
            "Essay-level processing counts within this phase. "
            "Updated as essays complete."
        ),
    )
    started_at: datetime | None = Field(
        default=None,
        description=(
            "Timestamp when phase processing started (DISPATCH_INITIATED → IN_PROGRESS). "
            "UTC timezone."
        ),
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Timestamp when phase reached terminal status. UTC timezone.",
    )
    error_info: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Error details for FAILED status. "
            "Contains error_code, message, service context. "
            "Follows SystemProcessingMetadata.error_info structure."
        ),
    )
    progress_percentage: float | None = Field(
        default=None,
        description=(
            "Optional progress percentage (0.0-100.0) for IN_PROGRESS phases. "
            "Calculated from essay_counts: (successful + failed) / total * 100."
        ),
    )


class ProcessingPipelineState(BaseModel):
    """Batch-level aggregate of all requested pipeline phase states.

    Provides whole-batch perspective tracking granular state for each pipeline
    phase (spellcheck, NLP, CJ assessment, etc.). Persisted in the BOS database
    and updated by BCS as ``ProcessingPipelineStatusUpdatedV1`` events arrive.

    Relationship to :class:`~common_core.status_enums.BatchStatus`:
    - ``BatchStatus``: Coarse batch lifecycle state (ACTIVE, READY_FOR_PIPELINE,
      PROCESSING, COMPLETED)
    - ``ProcessingPipelineState``: Fine-grained phase-by-phase execution tracking

    Storage: BOS database, materialized to WebSocket clients, and queried by the
    Result Aggregator when determining if all requested pipelines reached terminal
    states.
    """

    batch_id: str = Field(description="Batch identifier this pipeline state belongs to")
    requested_pipelines: list[str] = Field(
        description=(
            "User-requested pipeline names (e.g., ['spellcheck', 'nlp', 'cj_assessment']). "
            "Determines which phase fields are populated."
        )
    )
    spellcheck: PipelineStateDetail | None = Field(
        default_factory=PipelineStateDetail,
        description=(
            "Spellcheck phase execution state. "
            "Only populated if 'spellcheck' in requested_pipelines."
        ),
    )
    nlp: PipelineStateDetail | None = Field(
        default_factory=PipelineStateDetail,
        description=(
            "NLP phase execution state. "
            "Only populated if 'nlp' in requested_pipelines."
        ),
    )
    ai_feedback: PipelineStateDetail | None = Field(
        default_factory=PipelineStateDetail,
        description=(
            "AI Feedback phase execution state. "
            "Only populated if 'ai_feedback' in requested_pipelines."
        ),
    )
    cj_assessment: PipelineStateDetail | None = Field(
        default_factory=PipelineStateDetail,
        description=(
            "CJ Assessment phase execution state. "
            "Only populated if 'cj_assessment' in requested_pipelines."
        ),
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description=(
            "Timestamp of most recent pipeline state update. UTC timezone. "
            "Updated on every phase status change."
        ),
    )

    def get_pipeline(self, name: str) -> PipelineStateDetail | None:
        """Return the :class:`PipelineStateDetail` for ``name`` if it exists."""
        pipeline_name_attr = name.lower().replace("-", "_")
        return getattr(self, pipeline_name_attr, None)
