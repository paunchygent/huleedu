"""Database enums for the CJ Assessment Service.

This module defines enums used in database models for the CJ Assessment Service.
Adapted from the original prototype to focus on CJ assessment workflow states.
"""

from __future__ import annotations

import enum


class CJBatchStatusEnum(str, enum.Enum):
    """Enum representing the possible states of a CJ Assessment batch."""

    PENDING = "PENDING"
    FETCHING_CONTENT = "FETCHING_CONTENT"
    PERFORMING_COMPARISONS = "PERFORMING_COMPARISONS"
    COMPLETE_STABLE = "COMPLETE_STABLE"
    COMPLETE_MAX_COMPARISONS = "COMPLETE_MAX_COMPARISONS"
    ERROR_PROCESSING = "ERROR_PROCESSING"
    ERROR_ESSAY_PROCESSING = "ERROR_ESSAY_PROCESSING"

    def __str__(self) -> str:
        return self.value
