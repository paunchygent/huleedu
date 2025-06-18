"""
Defines the Pydantic models for parsing pipeline configurations.
"""

from pydantic import BaseModel


class PipelineStep(BaseModel):
    """Defines a single step in a processing pipeline.

    Attributes
    ----------
    name: Unique identifier for the step. This is the value returned to BOS and
        referenced in *depends_on* of other steps.
    service_name: Name of the downstream specialised service that will be
        triggered for this step.
    event_type: Fully-qualified Kafka topic / event type that will be emitted
        to start the step.
    event_data_model: Pydantic model name for the *data* portion of the event
        envelope.
    depends_on: List of step *name*s that must be completed before this step is
        eligible to run.
    """

    name: str
    service_name: str
    event_type: str
    event_data_model: str
    depends_on: list[str] = []


class PipelineDefinition(BaseModel):
    """Defines a complete processing pipeline."""

    description: str
    steps: list[PipelineStep]


class PipelineConfig(BaseModel):
    """The top-level model for the pipeline configuration file."""

    pipelines: dict[str, PipelineDefinition]
