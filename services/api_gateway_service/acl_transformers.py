"""
Anti-Corruption Layer transformers for API Gateway.

Implements Rule 020.3.1 (Explicit Contracts) by transforming internal service
data structures to stable external API contracts.

This module ensures the API Gateway maintains consistent client contracts
regardless of backend service evolution.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from common_core.pipeline_models import PhaseName, PipelineExecutionStatus
from common_core.status_enums import BatchClientStatus
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("api_gateway.acl_transformers")


def transform_bos_state_to_ras_response(bos_data: dict[str, Any], user_id: str) -> dict[str, Any]:
    """
    Transform BOS ProcessingPipelineState to RAS BatchStatusResponse format.

    Implements Anti-Corruption Layer (ACL) pattern ensuring stable client
    contracts regardless of backend service data structure evolution.
    Addresses contract violation at status_routes.py:118.

    Args:
        bos_data: ProcessingPipelineState response from Batch Orchestrator
        user_id: Authenticated user ID from JWT context for security

    Returns:
        dict: BatchStatusResponse-compliant data structure

    Raises:
        ValueError: If bos_data lacks required transformation fields
        KeyError: If essential pipeline state fields are missing

    Note:
        Follows Rule 020.3.1 (Explicit Contracts), Rule 050.3.1 (Type Safety),
        and Rule 082.1.1 (100-char line limit).
    """
    try:
        # Extract and validate pipeline states (Rule 050.1: Explicit over implicit)
        pipeline_states = _extract_pipeline_states(bos_data)
        if not pipeline_states:
            raise ValueError("No valid pipeline states found in BOS data")

        # Derive aggregated status (Rule 050.1: Simple over complex)
        overall_status = _derive_batch_status_from_pipelines(pipeline_states)

        # Calculate essay counts from primary pipeline
        primary_pipeline = pipeline_states[0]
        essay_counts = primary_pipeline.get("essay_counts", {})

        # Transform to compliant schema (Rule 020.3.1: Explicit Contracts)
        return {
            "batch_id": bos_data["batch_id"],
            "user_id": user_id,  # Security injection from JWT
            "overall_status": overall_status,
            "essay_count": essay_counts.get("total", 0),
            "completed_essay_count": _sum_successful_essays(pipeline_states),
            "failed_essay_count": _sum_failed_essays(pipeline_states),
            "requested_pipeline": ",".join(bos_data.get("requested_pipelines", [])),
            "current_phase": _derive_current_phase(pipeline_states),
            "essays": [],  # Cannot populate from BOS - missing individual data
            "created_at": None,  # Not available in ProcessingPipelineState
            "last_updated": bos_data.get("last_updated"),
            "processing_started_at": _get_earliest_start_time(pipeline_states),
            "processing_completed_at": _get_latest_completion_time(pipeline_states),
        }

    except (KeyError, TypeError) as e:
        logger.error(f"BOS data transformation failed: {e}")
        raise ValueError(f"Invalid BOS data structure: {e}") from e


def _extract_pipeline_states(bos_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract valid pipeline states from BOS data (Rule 050.3.1: Type Safety)."""
    # Use PhaseName enum values for type safety (Rule 050.3.1)
    pipeline_names = [
        PhaseName.SPELLCHECK.value,
        "nlp_metrics",  # BOS uses different naming
        PhaseName.AI_FEEDBACK.value,
        PhaseName.CJ_ASSESSMENT.value,
    ]
    return [
        bos_data[name] for name in pipeline_names if name in bos_data and bos_data[name] is not None
    ]


def _derive_batch_status_from_pipelines(pipeline_states: list[dict[str, Any]]) -> str:
    """
    Derive BatchClientStatus from pipeline execution states.

    Maps ProcessingPipelineState status values to BatchClientStatus enum.
    Follows Rule 050.1 (Explicit over implicit).

    Args:
        pipeline_states: List of pipeline state dictionaries

    Returns:
        str: BatchClientStatus enum value
    """
    # Use enum values for type safety (Rule 050.3.1: No magic strings)
    in_progress_statuses = {
        PipelineExecutionStatus.DISPATCH_INITIATED.value,
        PipelineExecutionStatus.IN_PROGRESS.value,
        PipelineExecutionStatus.PENDING_DEPENDENCIES.value,
    }
    completed_statuses = {
        PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value,
        PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS.value,
    }
    failed_statuses = {
        PipelineExecutionStatus.FAILED.value,
        PipelineExecutionStatus.CANCELLED.value,
    }

    statuses = [state.get("status") for state in pipeline_states]

    # Priority-based status derivation (Rule 050.1: Simple over complex)
    if any(status in in_progress_statuses for status in statuses):
        return BatchClientStatus.PROCESSING.value
    elif any(status in failed_statuses for status in statuses):
        return "FAILED"  # Note: BatchClientStatus doesn't have FAILED
    elif all(status in completed_statuses for status in statuses):
        return BatchClientStatus.AVAILABLE.value
    else:
        return BatchClientStatus.PROCESSING.value  # Safe default


def _derive_current_phase(pipeline_states: list[dict[str, Any]]) -> str | None:
    """
    Determine current processing phase from pipeline states.

    Args:
        pipeline_states: List of pipeline state dictionaries

    Returns:
        str | None: Current phase name or None if not processing
    """
    # Map pipeline state to phase name using enums (Rule 050.3.1: No magic strings)
    phase_mapping = {
        0: PhaseName.SPELLCHECK,
        1: "nlp_metrics",  # BOS uses different naming, map to closest enum
        2: PhaseName.AI_FEEDBACK,
        3: PhaseName.CJ_ASSESSMENT,
    }

    # Use enum values for status comparison
    active_statuses = {
        PipelineExecutionStatus.DISPATCH_INITIATED.value,
        PipelineExecutionStatus.IN_PROGRESS.value,
    }

    # Find first active pipeline by checking states in order
    for idx, state in enumerate(pipeline_states):
        if state.get("status") in active_statuses:
            phase = phase_mapping.get(idx)
            if isinstance(phase, PhaseName):
                return phase.value.upper()
            elif isinstance(phase, str):
                return phase.upper()

    return None


def _sum_successful_essays(pipeline_states: list[dict[str, Any]]) -> int:
    """Sum successful essays across all pipelines (Rule 050.3.1: Type Safety)."""
    return sum(state.get("essay_counts", {}).get("successful", 0) for state in pipeline_states)


def _sum_failed_essays(pipeline_states: list[dict[str, Any]]) -> int:
    """Sum failed essays across all pipelines (Rule 050.3.1: Type Safety)."""
    return sum(state.get("essay_counts", {}).get("failed", 0) for state in pipeline_states)


def _get_earliest_start_time(pipeline_states: list[dict[str, Any]]) -> datetime | None:
    """Extract earliest start time across pipelines (Rule 050.3.1: Type Safety)."""
    start_times: list[datetime] = []
    for state in pipeline_states:
        start_time = state.get("started_at")
        if start_time is not None and isinstance(start_time, datetime):
            start_times.append(start_time)
    return min(start_times) if start_times else None


def _get_latest_completion_time(pipeline_states: list[dict[str, Any]]) -> datetime | None:
    """Extract latest completion time across pipelines (Rule 050.3.1)."""
    completion_times: list[datetime] = []
    for state in pipeline_states:
        completion_time = state.get("completed_at")
        if completion_time is not None and isinstance(completion_time, datetime):
            completion_times.append(completion_time)
    return max(completion_times) if completion_times else None
