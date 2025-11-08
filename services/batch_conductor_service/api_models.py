"""
API models for Batch Conductor Service.

Defines request and response models for internal HTTP communication
between the Batch Orchestrator Service (BOS) and Batch Conductor Service (BCS).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from common_core.pipeline_models import PhaseName


class BCSPipelineDefinitionRequestV1(BaseModel):
    """
    Request model for pipeline definition endpoint.

    Used by BOS to request pipeline dependency resolution from BCS.
    """

    batch_id: str = Field(
        description="The unique identifier of the target batch.", min_length=1, max_length=255
    )
    requested_pipeline: PhaseName = Field(
        description=(
            "The final pipeline the user wants to run "
            "(e.g., PhaseName.AI_FEEDBACK, PhaseName.CJ_ASSESSMENT)."
        ),
    )
    correlation_id: str = Field(
        description="The correlation ID from the original pipeline request for event tracking",
        min_length=1,
        max_length=100,
    )
    batch_metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional metadata (prompt attachment, assignment context, etc.) "
            "for validation"
        ),
    )

    model_config = {
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "json_schema_extra": {
            "examples": [
                {
                    "batch_id": "batch_12345",
                    "requested_pipeline": "ai_feedback",
                    "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "batch_metadata": {"prompt_attached": True, "prompt_source": "cms"},
                },
                {
                    "batch_id": "batch_67890",
                    "requested_pipeline": "cj_assessment",
                    "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
                    "batch_metadata": {"prompt_attached": False, "prompt_source": "none"},
                },
            ]
        },
    }


class BCSPipelineDefinitionResponseV1(BaseModel):
    """
    Response model for pipeline definition endpoint.

    Returns the resolved pipeline with all necessary dependencies in execution order.
    """

    batch_id: str = Field(description="The unique identifier of the target batch.")
    final_pipeline: list[str] = Field(
        description="Ordered list of pipeline phases to execute, including dependencies."
    )
    analysis_summary: str | None = Field(
        default=None,
        description="Optional summary of the analysis performed to generate the pipeline.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "batch_id": "batch_12345",
                    "final_pipeline": ["spellcheck", "ai_feedback"],
                    "analysis_summary": "Added spellcheck dependency for ai_feedback pipeline",
                },
                {
                    "batch_id": "batch_67890",
                    "final_pipeline": ["spellcheck", "cj_assessment"],
                    "analysis_summary": "Added spellcheck dependency for cj_assessment pipeline",
                },
            ]
        }
    }
