"""Default implementation of PipelineRulesProtocol."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

from collections import defaultdict, deque

import structlog

from huleedu_service_libs.error_handling.batch_conductor_factories import (
    raise_pipeline_compatibility_failed,
)
from huleedu_service_libs.error_handling.factories import (
    raise_resource_not_found,
)
from services.batch_conductor_service.pipeline_definitions import PipelineDefinition, PipelineStep
from services.batch_conductor_service.protocols import (
    BatchStateRepositoryProtocol,
    PipelineGeneratorProtocol,
    PipelineRulesProtocol,
)

logger = structlog.getLogger(__name__)


class DefaultPipelineRules(PipelineRulesProtocol):
    """Default implementation of pipeline dependency resolution rules with Prometheus metrics."""

    def __init__(
        self,
        pipeline_generator: PipelineGeneratorProtocol,
        batch_state_repository: BatchStateRepositoryProtocol,
        registry: CollectorRegistry | None = None,
    ):
        from prometheus_client import CollectorRegistry, Counter  # local import

        self.pipeline_generator = pipeline_generator
        self.batch_state_repository = batch_state_repository

        self._registry: CollectorRegistry = registry or CollectorRegistry()
        # Metrics
        self._rules_success: Counter = Counter(
            "bcs_pipeline_rules_success_total",
            "Total successful pipeline dependency resolutions",
            registry=self._registry,
        )
        self._rules_error: Counter = Counter(
            "bcs_pipeline_rules_error_total",
            "Total failed pipeline dependency resolutions",
            registry=self._registry,
        )
        self._rules_pruned: Counter = Counter(
            "bcs_pipeline_rules_pruned_total",
            "Pipeline steps pruned due to prior completion",
            registry=self._registry,
        )

        # Track pruned phases from last resolution for event publishing
        self._last_pruned_phases: list[str] = []

    async def resolve_pipeline_dependencies(
        self, requested_pipeline: str, batch_id: str | None = None
    ) -> list[str]:
        """Build an ordered execution list for a requested pipeline step.

        Prometheus counters are recorded for successes, pruned steps, and errors.
        """
        try:
            # Locate pipeline definition containing the requested step
            definition = await self._find_pipeline_containing_step(requested_pipeline)
            if definition is None:
                raise ValueError(f"Unknown pipeline step '{requested_pipeline}'.")

            # Topological sort of the sub-graph rooted at requested_pipeline
            ordered_steps = self._topological_sort(definition, requested_pipeline)

            # Remove already-completed ones (order preserved)
            if batch_id is not None:
                before_len = len(ordered_steps)
                original_steps = ordered_steps.copy()
                ordered_steps = await self.prune_completed_steps(ordered_steps, batch_id)
                pruned = before_len - len(ordered_steps)
                if pruned:
                    self._rules_pruned.inc(pruned)

                # Store pruned phases for the last resolution (for event publishing)
                self._last_pruned_phases = [
                    step for step in original_steps if step not in ordered_steps
                ]
            else:
                self._last_pruned_phases = []

            # Success metric
            self._rules_success.inc()
            return ordered_steps
        except Exception:
            self._rules_error.inc()
            raise

    async def validate_pipeline_prerequisites(self, pipeline_name: str, batch_id: str) -> bool:
        """Check that all *dependencies* of ``pipeline_name`` are complete for the batch."""

        definition = await self._find_pipeline_containing_step(pipeline_name)
        if definition is None:
            raise ValueError(f"Unknown pipeline step '{pipeline_name}'.")

        # Build quick lookup
        step_map: dict[str, PipelineStep] = {s.name: s for s in definition.steps}
        to_check: list[str] = list(step_map[pipeline_name].depends_on)

        while to_check:
            dep = to_check.pop()
            done = await self.batch_state_repository.is_batch_step_complete(batch_id, dep)
            if not done:
                return False
            # Add transitive deps
            to_check.extend(step_map[dep].depends_on)

        return True

    async def prune_completed_steps(self, pipeline_steps: list[str], batch_id: str) -> list[str]:
        """Remove already-completed steps from pipeline execution list."""
        # Use batch state repository to check completion status
        remaining_steps = []
        pruned_steps = []

        logger.info(
            f"Checking phase completions for batch {batch_id}. Pipeline steps to check: {pipeline_steps}"
        )

        for step in pipeline_steps:
            is_complete = await self.batch_state_repository.is_batch_step_complete(batch_id, step)
            if is_complete:
                pruned_steps.append(step)
                logger.info(
                    f"✅ Phase '{step}' is already complete for batch {batch_id} - will be PRUNED",
                    extra={"batch_id": batch_id, "step": step, "pruned": True},
                )
            else:
                remaining_steps.append(step)
                logger.debug(
                    f"⏳ Phase '{step}' is not complete for batch {batch_id} - will be EXECUTED",
                    extra={"batch_id": batch_id, "step": step, "pruned": False},
                )

        if pruned_steps:
            logger.info(
                f"🎯 Phase pruning summary for batch {batch_id}: "
                f"Pruned {len(pruned_steps)} phases: {pruned_steps}, "
                f"Will execute {len(remaining_steps)} phases: {remaining_steps}",
                extra={
                    "batch_id": batch_id,
                    "pruned_phases": pruned_steps,
                    "remaining_phases": remaining_steps,
                    "original_pipeline": pipeline_steps,
                },
            )
        else:
            logger.info(
                f"No phases pruned for batch {batch_id}. All {len(pipeline_steps)} phases will execute: {pipeline_steps}",
                extra={"batch_id": batch_id, "pipeline_steps": pipeline_steps},
            )

        return remaining_steps

    def get_last_pruned_phases(self) -> list[str]:
        """Get the phases that were pruned in the last pipeline resolution."""
        return self._last_pruned_phases.copy()

    async def validate_pipeline_compatibility(
        self, pipeline_name: str, correlation_id: UUID, batch_metadata: dict | None = None
    ) -> None:
        """Validate if pipeline can be executed with given batch metadata.

        Args:
            pipeline_name: Name of the pipeline to validate
            correlation_id: Correlation ID for request tracing
            batch_metadata: Optional batch metadata for compatibility checks

        Raises:
            HuleEduError: If pipeline compatibility validation fails
        """
        try:
            # Check if pipeline definition exists
            definition = await self._find_pipeline_containing_step(pipeline_name)
            if definition is None:
                raise_resource_not_found(
                    service="batch_conductor_service",
                    operation="validate_pipeline_compatibility",
                    resource_type="pipeline",
                    resource_id=pipeline_name,
                    correlation_id=correlation_id,
                )

            # Basic validation - pipeline exists and is well-formed
            # Additional metadata-based validation can be added here as needed
            # Success case: method returns without raising

        except Exception as e:
            # If it's already a HuleEduError, let it propagate
            if hasattr(e, "error_detail"):
                raise

            # Otherwise, wrap in compatibility failure error
            raise_pipeline_compatibility_failed(
                service="batch_conductor_service",
                operation="validate_pipeline_compatibility",
                message=f"Pipeline validation error: {str(e)}",
                correlation_id=correlation_id,
                pipeline_name=pipeline_name,
                batch_metadata=batch_metadata,
                compatibility_issue=str(e),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _find_pipeline_containing_step(self, step_name: str) -> PipelineDefinition | None:
        """Return the PipelineDefinition that contains *step_name*, else None."""
        for pipeline_name in await self.pipeline_generator.list_available_pipelines():
            definition = await self.pipeline_generator.get_pipeline_definition(pipeline_name)
            if definition and any(s.name == step_name for s in definition.steps):
                return definition
        return None

    def _topological_sort(self, definition: PipelineDefinition, root_step: str) -> list[str]:
        """Return ordered list starting with dependencies and ending with *root_step*."""
        # Gather reachable nodes via DFS
        step_map: dict[str, PipelineStep] = {s.name: s for s in definition.steps}
        reachable: set[str] = set()

        def dfs(node: str):
            if node in reachable:
                return
            reachable.add(node)
            for dep in step_map[node].depends_on:
                dfs(dep)

        dfs(root_step)

        # Build adjacency and in-degree for reachable subgraph
        in_degree: dict[str, int] = defaultdict(int)
        adjacency: dict[str, list[str]] = defaultdict(list)

        for name in reachable:
            for dep in step_map[name].depends_on:
                if dep in reachable:
                    adjacency[dep].append(name)
                    in_degree[name] += 1
            in_degree.setdefault(name, 0)

        queue: deque[str] = deque([n for n, d in in_degree.items() if d == 0])
        ordered: list[str] = []
        while queue:
            node = queue.popleft()
            ordered.append(node)
            for neighbor in adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(reachable):
            raise ValueError("Dependency cycle detected during ordering.")

        # Ensure root_step is last
        if ordered[-1] != root_step:
            ordered.remove(root_step)
            ordered.append(root_step)

        return ordered
