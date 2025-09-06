"""Pipeline-related event models for credit management and denial notifications."""

from datetime import datetime
from typing import Optional

from pydantic import Field

from common_core.event_enums import ProcessingEvent

from .base_event_models import BaseEventData


class PipelineDeniedV1(BaseEventData):
    """Event published when a pipeline request is denied due to insufficient credits or rate limits.

    This event is published by the Batch Orchestrator Service when credit checking fails
    before pipeline execution. It triggers teacher notifications and API Gateway 402 responses.
    """

    event_name: ProcessingEvent = Field(default=ProcessingEvent.PIPELINE_DENIED)
    batch_id: str = Field(..., description="ID of the batch whose pipeline was denied")
    user_id: str = Field(..., description="User who requested the pipeline")
    org_id: Optional[str] = Field(None, description="Organization ID (if applicable)")
    requested_pipeline: str = Field(..., description="Name of the pipeline that was requested")
    denial_reason: str = Field(
        ..., description="Reason for denial: 'insufficient_credits' or 'rate_limit_exceeded'"
    )
    required_credits: int = Field(..., description="Total credits required for the pipeline")
    available_credits: int = Field(..., description="Credits currently available")
    resource_breakdown: Optional[dict[str, int]] = Field(
        None,
        description="Breakdown of required resources by type (e.g., {'cj_comparison': 45, 'ai_feedback': 10})",
    )
    denied_at: datetime = Field(
        default_factory=datetime.utcnow, description="When the denial occurred"
    )

    class Config:
        # Pydantic v2 configuration
        json_schema_extra = {
            "examples": [
                {
                    "event_name": "pipeline.denied",
                    "entity_id": "batch-123",
                    "entity_type": "batch",
                    "batch_id": "batch-123",
                    "user_id": "teacher-456",
                    "org_id": "school-789",
                    "requested_pipeline": "cj_assessment",
                    "denial_reason": "insufficient_credits",
                    "required_credits": 45,
                    "available_credits": 10,
                    "resource_breakdown": {"cj_comparison": 45},
                    "correlation_id": "req-123",
                },
                {
                    "event_name": "pipeline.denied",
                    "entity_id": "batch-456",
                    "entity_type": "batch",
                    "batch_id": "batch-456",
                    "user_id": "teacher-789",
                    "org_id": None,
                    "requested_pipeline": "full_assessment",
                    "denial_reason": "rate_limit_exceeded",
                    "required_credits": 55,
                    "available_credits": 100,
                    "resource_breakdown": {"cj_comparison": 45, "ai_feedback_generation": 10},
                    "correlation_id": "req-456",
                },
            ]
        }
