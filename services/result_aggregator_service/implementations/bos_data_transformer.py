"""
Data transformer for BOS ProcessingPipelineState to RAS BatchResult format.

This module contains the transformation logic moved from API Gateway's
acl_transformers.py to implement proper service boundaries. The Result
Aggregator Service now handles its own data consistency internally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus
from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.models_db import BatchResult

logger = create_service_logger("result_aggregator.bos_data_transformer")


class BOSDataTransformer:
    """Transforms BOS ProcessingPipelineState to RAS BatchResult format."""

    def transform_bos_to_batch_result(self, bos_data: Dict[str, Any], user_id: str) -> BatchResult:
        """
        Transform BOS ProcessingPipelineState to RAS BatchResult.

        Implements the data transformation that was previously handled in
        API Gateway's ACL transformers. This ensures the Result Aggregator
        Service maintains consistent data formats internally.

        Args:
            bos_data: ProcessingPipelineState response from Batch Orchestrator
            user_id: User ID for the batch (for validation)

        Returns:
            BatchResult: Transformed data in RAS format

        Raises:
            ValueError: If bos_data lacks required transformation fields
            KeyError: If essential pipeline state fields are missing
        """
        try:
            # Extract and validate pipeline states
            pipeline_states_with_names = self._extract_pipeline_states(bos_data)
            if not pipeline_states_with_names:
                raise ValueError("No valid pipeline states found in BOS data")

            # Extract just the state data for status derivation
            pipeline_states = [state for _, state in pipeline_states_with_names]

            # Derive aggregated status
            overall_status = self._derive_batch_status_from_pipelines(pipeline_states)

            # Calculate essay counts from primary pipeline
            primary_pipeline = pipeline_states[0]
            essay_counts = primary_pipeline.get("essay_counts", {})

            # Transform to BatchResult format
            batch_result = BatchResult(
                batch_id=bos_data["batch_id"],
                user_id=user_id,
                overall_status=overall_status,
                essay_count=essay_counts.get("total", 0),
                completed_essay_count=self._sum_successful_essays(pipeline_states),
                failed_essay_count=self._sum_failed_essays(pipeline_states),
                requested_pipeline=",".join(bos_data.get("requested_pipelines", [])),
                processing_started_at=self._get_earliest_start_time(pipeline_states),
                processing_completed_at=self._get_latest_completion_time(pipeline_states),
                batch_metadata={
                    "source": "bos_fallback",
                    "transformed_at": datetime.utcnow().isoformat(),
                    "current_phase": self._derive_current_phase(pipeline_states_with_names),
                },
            )

            logger.info(
                "Successfully transformed BOS data to BatchResult",
                batch_id=bos_data["batch_id"],
                overall_status=overall_status,
                essay_count=essay_counts.get("total", 0),
            )

            return batch_result

        except (KeyError, TypeError) as e:
            logger.error(
                "BOS data transformation failed",
                batch_id=bos_data.get("batch_id", "unknown"),
                error=str(e),
                exc_info=True,
            )
            raise ValueError(f"Invalid BOS data structure: {e}") from e

    def _extract_pipeline_states(
        self, bos_data: Dict[str, Any]
    ) -> List[tuple[str, Dict[str, Any]]]:
        """Extract valid pipeline states from BOS data with their names."""
        # Use PhaseName enum values for type safety
        pipeline_names = [
            PhaseName.SPELLCHECK.value,
            PhaseName.NLP.value,
            PhaseName.AI_FEEDBACK.value,
            PhaseName.CJ_ASSESSMENT.value,
        ]
        return [
            (name, bos_data[name])
            for name in pipeline_names
            if name in bos_data and bos_data[name] is not None
        ]

    def _derive_batch_status_from_pipelines(
        self, pipeline_states: List[Dict[str, Any]]
    ) -> BatchStatus:
        """
        Derive BatchStatus from pipeline execution states.

        Maps ProcessingPipelineState status values to BatchStatus enum.
        """
        # Use enum string values for comparison with BOS data
        in_progress_statuses = {
            "DISPATCH_INITIATED",
            "IN_PROGRESS",
            "PENDING_DEPENDENCIES",
        }
        completed_statuses = {
            "COMPLETED_SUCCESSFULLY",
            "COMPLETED_WITH_PARTIAL_SUCCESS",
        }
        failed_statuses = {
            "FAILED",
            "CANCELLED",
        }

        statuses = [state.get("status") for state in pipeline_states]

        # Priority-based status derivation - failed status takes precedence
        if any(status in failed_statuses for status in statuses):
            return BatchStatus.COMPLETED_WITH_FAILURES
        elif any(status in in_progress_statuses for status in statuses):
            return BatchStatus.PROCESSING_PIPELINES
        elif all(status in completed_statuses for status in statuses):
            return BatchStatus.COMPLETED_SUCCESSFULLY
        else:
            return BatchStatus.PROCESSING_PIPELINES  # Safe default

    def _derive_current_phase(
        self, pipeline_states_with_names: List[tuple[str, Dict[str, Any]]]
    ) -> Optional[str]:
        """
        Determine current processing phase from pipeline states.

        Args:
            pipeline_states_with_names: List of (pipeline_name, state_dict) tuples

        Returns:
            Current phase name or None if not processing
        """
        # Map pipeline names to display names
        phase_name_mapping = {
            PhaseName.SPELLCHECK.value: PhaseName.SPELLCHECK.value.upper(),
            PhaseName.NLP.value: "NLP",
            PhaseName.AI_FEEDBACK.value: PhaseName.AI_FEEDBACK.value.upper(),
            PhaseName.CJ_ASSESSMENT.value: PhaseName.CJ_ASSESSMENT.value.upper(),
        }

        # Use enum string values for status comparison with BOS data
        active_statuses = {
            "DISPATCH_INITIATED",
            "IN_PROGRESS",
        }

        # Find first active pipeline by checking states in order
        for pipeline_name, state in pipeline_states_with_names:
            if state.get("status") in active_statuses:
                return phase_name_mapping.get(pipeline_name)

        return None

    def _sum_successful_essays(self, pipeline_states: List[Dict[str, Any]]) -> int:
        """Sum successful essays across all pipelines."""
        return sum(state.get("essay_counts", {}).get("successful", 0) for state in pipeline_states)

    def _sum_failed_essays(self, pipeline_states: List[Dict[str, Any]]) -> int:
        """Sum failed essays across all pipelines."""
        return sum(state.get("essay_counts", {}).get("failed", 0) for state in pipeline_states)

    def _get_earliest_start_time(self, pipeline_states: List[Dict[str, Any]]) -> Optional[datetime]:
        """Extract earliest start time across pipelines."""
        start_times: List[datetime] = []
        for state in pipeline_states:
            start_time = state.get("started_at")
            if start_time is not None:
                parsed_time = self._parse_datetime(start_time)
                if parsed_time:
                    start_times.append(parsed_time)
        return min(start_times) if start_times else None

    def _get_latest_completion_time(
        self, pipeline_states: List[Dict[str, Any]]
    ) -> Optional[datetime]:
        """Extract latest completion time across pipelines."""
        completion_times: List[datetime] = []
        for state in pipeline_states:
            completion_time = state.get("completed_at")
            if completion_time is not None:
                parsed_time = self._parse_datetime(completion_time)
                if parsed_time:
                    completion_times.append(parsed_time)
        return max(completion_times) if completion_times else None

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                # Try ISO format first
                if value.endswith("Z"):
                    value = value[:-1] + "+00:00"
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Failed to parse datetime: {value}")
                return None
        return None
