"""API-specific enums for Result Aggregator Service."""
from __future__ import annotations

from enum import Enum


class BatchStatus(str, Enum):
    """Batch status for API responses."""

    REGISTERED = "REGISTERED"
    PROCESSING = "PROCESSING"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingPhase(str, Enum):
    """Processing phases for API responses."""

    SPELLCHECK = "SPELLCHECK"
    CJ_ASSESSMENT = "CJ_ASSESSMENT"
    NLP_ANALYSIS = "NLP_ANALYSIS"
    AI_FEEDBACK = "AI_FEEDBACK"
