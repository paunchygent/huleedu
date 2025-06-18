"""Default implementation of PipelineGeneratorProtocol."""

from __future__ import annotations

from services.batch_conductor_service.config import Settings
from services.batch_conductor_service.pipeline_definitions import PipelineDefinition


class DefaultPipelineGenerator:
    """Default implementation of pipeline generator using configuration files."""

    def __init__(self, settings: Settings):
        self.settings = settings
        # TODO: Load from actual pipeline config in Phase 2B
        self._pipelines: dict[str, PipelineDefinition] = {}

    async def get_pipeline_definition(self, pipeline_name: str) -> PipelineDefinition | None:
        """Retrieve pipeline definition by name."""
        return self._pipelines.get(pipeline_name)

    async def list_available_pipelines(self) -> list[str]:
        """List all available pipeline names."""
        return list(self._pipelines.keys())

    async def validate_pipeline_config(self) -> bool:
        """Validate the current pipeline configuration."""
        return True  # Basic stub implementation
