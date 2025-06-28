"""Database-specific enums for Result Aggregator Service."""

from common_core.status_enums import BatchStatus, ProcessingStage

# Re-export common_core enums for backwards compatibility
__all__ = ["BatchStatus", "ProcessingStage"]
