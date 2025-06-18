"""Default implementation of PipelineRulesProtocol."""

from __future__ import annotations

from services.batch_conductor_service.protocols import (
    BatchStateRepositoryProtocol,
    PipelineGeneratorProtocol,
    PipelineRulesProtocol,
)


class DefaultPipelineRules(PipelineRulesProtocol):
    """Default implementation of pipeline dependency resolution rules."""

    def __init__(
        self,
        pipeline_generator: PipelineGeneratorProtocol,
        batch_state_repository: BatchStateRepositoryProtocol,
    ):
        self.pipeline_generator = pipeline_generator
        self.batch_state_repository = batch_state_repository

    async def resolve_pipeline_dependencies(
        self, requested_pipeline: str, batch_id: str | None = None
    ) -> list[str]:
        """Resolve pipeline dependencies into an ordered execution sequence."""
        # Basic stub implementation - return single pipeline for now
        # TODO: Implement actual dependency resolution in Phase 2B Checkpoint 2
        return [requested_pipeline]

    async def validate_pipeline_prerequisites(self, pipeline_name: str, batch_id: str) -> bool:
        """Validate that a pipeline's prerequisites are met for the given batch."""
        # Basic stub implementation - always return True for now
        # TODO: Implement actual prerequisite validation using batch_state_repository in Phase 2B
        return True

    async def prune_completed_steps(self, pipeline_steps: list[str], batch_id: str) -> list[str]:
        """Remove already-completed steps from pipeline execution list."""
        # Use batch state repository to check completion status
        remaining_steps = []
        for step in pipeline_steps:
            is_complete = await self.batch_state_repository.is_batch_step_complete(batch_id, step)
            if not is_complete:
                remaining_steps.append(step)

        return remaining_steps
