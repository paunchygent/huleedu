"""Database enums for the Batch Orchestrator Service.

This module defines enums used in database models for the Batch Orchestrator Service.
These enums represent the specific database states needed for BOS operations.
"""

from __future__ import annotations

import enum


class BatchStatusEnum(str, enum.Enum):
    """Enum representing the possible states of a batch in BOS database."""

    # Initial states
    AWAITING_CONTENT_VALIDATION = "awaiting_content_validation"
    AWAITING_PIPELINE_CONFIGURATION = "awaiting_pipeline_configuration"
    READY_FOR_PIPELINE_EXECUTION = "ready_for_pipeline_execution"

    # Processing states
    PROCESSING_PIPELINES = "processing_pipelines"

    # Terminal states
    COMPLETED_SUCCESSFULLY = "completed_successfully"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED_CRITICALLY = "failed_critically"
    CANCELLED = "cancelled"
    CONTENT_INGESTION_FAILED = "content_ingestion_failed"

    def __str__(self) -> str:
        return self.value


class PhaseStatusEnum(str, enum.Enum):
    """Enum representing the possible states of a pipeline phase."""

    PENDING = "pending"
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return self.value


class PipelinePhaseEnum(str, enum.Enum):
    """Enum representing the different pipeline phases that can be executed.

    Only includes phases that have actual service implementations or are clearly planned.
    """

    SPELLCHECK = "spellcheck"
    NLP = "nlp"
    AI_FEEDBACK = "ai_feedback"
    CJ_ASSESSMENT = "cj_assessment"

    def __str__(self) -> str:
        return self.value
