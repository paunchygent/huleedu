"""Database enums for the Batch Orchestrator Service.

This module defines enums used in database models for the Batch Orchestrator Service.
These enums represent the specific database states needed for BOS operations.

NOTE: BatchStatus is now imported from common_core as it's part of inter-service contracts.
Only service-specific internal enums should be defined here.
"""

from __future__ import annotations

import enum

# BatchStatusEnum REMOVED - use common_core.enums.BatchStatus instead
# This eliminates duplication and ensures contract consistency


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
