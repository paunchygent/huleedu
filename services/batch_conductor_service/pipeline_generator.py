"""
Loads and provides access to pipeline definitions from a configuration file.
"""

from pathlib import Path

import yaml

from services.batch_conductor_service.pipeline_definitions import (
    PipelineConfig,
    PipelineDefinition,
)


class PipelineGenerator:
    """Loads pipeline definitions from a YAML file and provides them on demand."""

    def __init__(self, config_path: Path):
        with open(config_path) as f:
            raw_config = yaml.safe_load(f)
        self._config = PipelineConfig(**raw_config)

    def get_pipeline(self, name: str) -> PipelineDefinition | None:
        """Retrieves a pipeline definition by its name."""
        return self._config.pipelines.get(name)
