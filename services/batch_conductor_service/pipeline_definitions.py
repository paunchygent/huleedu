"""
Defines the Pydantic models for parsing pipeline configurations.
"""

from pydantic import BaseModel


class PipelineStep(BaseModel):
    """Defines a single step in a processing pipeline."""

    service_name: str
    event_type: str
    # The model for the 'data' field of the event envelope
    event_data_model: str


class PipelineDefinition(BaseModel):
    """Defines a complete processing pipeline."""

    description: str
    steps: list[PipelineStep]


class PipelineConfig(BaseModel):
    """The top-level model for the pipeline configuration file."""

    pipelines: dict[str, PipelineDefinition]
