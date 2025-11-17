"""Batch configuration management for CJ Assessment Service.

This module handles batch processing configuration parameters and overrides.
"""

from __future__ import annotations

from typing import Any

from common_core.config_enums import LLMBatchingMode
from pydantic import BaseModel, Field

from services.cj_assessment_service.config import Settings


class BatchConfigOverrides(BaseModel):
    """Configuration overrides for batch processing parameters."""

    batch_size: int | None = Field(None, ge=10, le=200, description="Batch size override")
    max_concurrent_batches: int | None = Field(
        None, ge=1, le=5, description="Maximum concurrent batches"
    )
    partial_completion_threshold: float | None = Field(
        None, ge=0.5, le=1.0, description="Partial completion threshold"
    )
    llm_batching_mode_override: LLMBatchingMode | None = Field(
        default=None,
        description="Override for CJ→LPS batching strategy on a per-batch basis",
    )


def get_effective_batch_size(
    settings: Settings, config_overrides: BatchConfigOverrides | None
) -> int:
    """Get effective batch size from settings and overrides.

    Args:
        settings: Application settings
        config_overrides: Optional batch configuration overrides

    Returns:
        Effective batch size to use
    """
    if config_overrides and config_overrides.batch_size is not None:
        return config_overrides.batch_size

    # Use settings default or fallback
    return getattr(settings, "DEFAULT_BATCH_SIZE", 50)


def get_effective_threshold(
    config_overrides: BatchConfigOverrides | None, batch_state: Any
) -> float:
    """Get effective completion threshold from settings and overrides.

    Args:
        config_overrides: Optional batch configuration overrides
        batch_state: Current batch state with threshold configuration

    Returns:
        Effective completion threshold to use
    """
    if config_overrides and config_overrides.partial_completion_threshold is not None:
        return config_overrides.partial_completion_threshold

    # Use batch state threshold or default
    if hasattr(batch_state, "completion_threshold_pct"):
        return float(batch_state.completion_threshold_pct / 100.0)

    return 0.95  # Default 95% threshold
