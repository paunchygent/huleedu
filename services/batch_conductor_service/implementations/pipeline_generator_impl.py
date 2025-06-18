"""Default implementation of PipelineGeneratorProtocol."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import CollectorRegistry

import pathlib
from collections import defaultdict, deque
from typing import Any

import yaml

from services.batch_conductor_service.config import Settings
from services.batch_conductor_service.pipeline_definitions import (
    PipelineConfig,
    PipelineDefinition,
)


class DefaultPipelineGenerator:
    """Generate and validate pipeline definitions from a YAML file.

    The generator loads the configuration once and keeps it cached for the
    service lifetime. Validation is executed during the first load and the
    result cached as well. Subsequent calls hit the in-memory dict only.

    Prometheus counters are exposed for successful and failed configuration
    loads to provide observability on operator errors.
    """

    def __init__(
        self,
        settings: Settings,
        registry: "CollectorRegistry | None" = None,
    ):
        from prometheus_client import Counter, CollectorRegistry  # local import to avoid hard dep if unused

        # Re-use the default registry if none is supplied (e.g. in unit tests)
        self._registry: CollectorRegistry = registry or CollectorRegistry()

        # Metrics
        self._config_load_success: Counter = Counter(
            "bcs_pipeline_config_load_success_total",
            "Total successful pipeline configuration loads",
            registry=self._registry,
        )
        self._config_load_error: Counter = Counter(
            "bcs_pipeline_config_load_error_total",
            "Total failed pipeline configuration loads",
            registry=self._registry,
        )

        self.settings = settings
        self._pipelines: dict[str, PipelineDefinition] = {}
        self._loaded: bool = False

    async def _ensure_loaded(self) -> None:
        """Load and validate the YAML configuration if not yet done."""
        if self._loaded:
            return

        cfg_path = pathlib.Path(self.settings.PIPELINE_CONFIG_PATH)
        try:
            if not cfg_path.exists():
                raise FileNotFoundError(
                    f"Pipeline configuration YAML not found at {cfg_path.resolve()}"
                )

            with cfg_path.open("r", encoding="utf-8") as fp:
                raw_yaml: dict[str, Any] = yaml.safe_load(fp)

            pipeline_config = PipelineConfig(**raw_yaml)

            self._pipelines = pipeline_config.pipelines

            # Run validation (duplicates already handled by model construction)
            self._validate_cycles()

            self._loaded = True
            # Metrics – happy path
            self._config_load_success.inc()
        except Exception:
            # Metrics – error path
            self._config_load_error.inc()
            raise

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    async def get_pipeline_definition(
        self, pipeline_name: str
    ) -> PipelineDefinition | None:
        """Retrieve pipeline definition by name."""
        await self._ensure_loaded()
        return self._pipelines.get(pipeline_name)

    async def list_available_pipelines(self) -> list[str]:
        """Return names of all configured pipelines."""
        await self._ensure_loaded()
        return list(self._pipelines.keys())

    async def validate_pipeline_config(self) -> bool:
        """Validate and reload configuration on-demand.

        Returns
        -------
        bool
            *True* if configuration is valid (no cycles / missing deps).
        """
        # Force reload next call then load to re-validate
        self._loaded = False
        await self._ensure_loaded()
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_cycles(self) -> None:
        """Detect dependency cycles in every pipeline using Kahn's algorithm."""
        for pipeline_name, definition in self._pipelines.items():
            # Build graph structures
            in_degree: dict[str, int] = defaultdict(int)
            adjacency: dict[str, list[str]] = defaultdict(list)

            step_names = {s.name for s in definition.steps}

            for step in definition.steps:
                # Validate undefined deps early
                for dep in step.depends_on:
                    if dep not in step_names:
                        raise ValueError(
                            f"Step '{step.name}' in pipeline '{pipeline_name}' depends on unknown step '{dep}'."
                        )

                    adjacency[dep].append(step.name)
                    in_degree[step.name] += 1
                # Ensure the step is present with 0 in-degree if it has none
                in_degree.setdefault(step.name, 0)

            # Topological sort
            q: deque[str] = deque([n for n, d in in_degree.items() if d == 0])
            visited = 0
            while q:
                node = q.popleft()
                visited += 1
                for neighbor in adjacency.get(node, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        q.append(neighbor)

            if visited != len(in_degree):
                raise ValueError(
                    f"Dependency cycle detected in pipeline '{pipeline_name}'."
                )
        