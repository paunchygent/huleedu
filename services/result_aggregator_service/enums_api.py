"""API-specific enums for Result Aggregator Service."""

from __future__ import annotations

# Import shared enums from common_core instead of duplicating them
from common_core.pipeline_models import PhaseName as ProcessingPhase
from common_core.status_enums import BatchClientStatus as BatchStatus  # Use client-facing enum for API responses
from common_core.status_enums import BatchStatus as InternalBatchStatus  # Keep internal status for DB mapping

# Re-export for backward compatibility
__all__ = ["BatchStatus", "ProcessingPhase", "InternalBatchStatus"]