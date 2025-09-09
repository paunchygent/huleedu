"""Pipeline validation helper for test assertions."""

from typing import Dict, List, Set

from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("test.validation")


class PipelineValidationHelper:
    """Helper class for validating pipeline execution results."""

    @staticmethod
    def validate_phase_pruning(
        expected_phases: List[str],
        executed_steps: Set[str],
        pruned_phases: List[str],
        reused_storage_ids: Dict[str, str],
    ) -> None:
        """
        Validate that phase pruning worked correctly.

        Args:
            expected_phases: List of phases expected to be pruned
            executed_steps: Set of steps that were actually executed
            pruned_phases: List of phases that were pruned
            reused_storage_ids: Dictionary of reused storage IDs

        Raises:
            AssertionError: If validation fails
        """
        for phase in expected_phases:
            assert phase in pruned_phases, f"Expected {phase} to be pruned"
            assert phase not in executed_steps, f"Phase {phase} should not have been executed"
            if phase in reused_storage_ids:
                logger.info(
                    f"✅ Phase {phase} properly pruned, reused storage ID: {reused_storage_ids[phase]}"
                )
            else:
                logger.warning(f"⚠️ Phase {phase} was pruned but no storage ID was reused")
