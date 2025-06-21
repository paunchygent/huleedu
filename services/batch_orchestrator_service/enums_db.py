"""Database enums for the Batch Orchestrator Service.

This module defines enums used in database models for the Batch Orchestrator Service.
These enums represent the specific database states needed for BOS operations.

NOTE: BatchStatus is now imported from common_core as it's part of inter-service contracts.
Only service-specific internal enums should be defined here.
"""

from __future__ import annotations

import enum

# No BatchStatusEnum - use common_core.enums.BatchStatus instead
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


# PipelinePhaseEnum removed - now using PhaseName from common_core.pipeline_models
# This eliminates duplication and ensures contract consistency with dynamic orchestration
