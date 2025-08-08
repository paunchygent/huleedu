"""
Client command events for HuleEdu platform.

This module defines command events that originate from client-facing services
(like the API Gateway) and are consumed by internal orchestration services.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ClientBatchPipelineRequestV1(BaseModel):
    """
    Command sent from the API Gateway to signal a user's request to run a
    processing pipeline on an existing, fully uploaded batch.

    This event is published to Kafka when a client requests pipeline execution
    via the API Gateway, and consumed by the Batch Orchestrator Service (BOS).
    """

    batch_id: str = Field(
        description="The unique identifier of the target batch.",
        min_length=1,
        max_length=255,
    )
    requested_pipeline: str = Field(
        description="""The final pipeline the user wants to run (e.g., 'ai_feedback',
        'cj_assessment').""",
        min_length=1,
        max_length=100,
    )
    client_correlation_id: UUID = Field(
        default_factory=uuid4,
        description="Client-provided correlation ID for request tracking.",
    )
    user_id: str = Field(
        description="The ID of the authenticated user who owns this batch.",
        min_length=1,
        max_length=255,
    )
    is_retry: bool = Field(
        default=False,
        description="Flag indicating this is a user-initiated retry request.",
    )
    retry_reason: str | None = Field(
        default=None,
        description="Optional user-provided reason for the retry.",
        max_length=500,
    )
    assignment_id: str | None = Field(
        default=None,
        max_length=100,
        description="Predefined assignment identifier for context-aware assessment",
    )

    model_config = {
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "json_schema_extra": {
            "examples": [
                {
                    "batch_id": "batch_12345",
                    "requested_pipeline": "ai_feedback",
                    "client_correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                    "user_id": "user_789",
                    "is_retry": False,
                    "retry_reason": None,
                },
                {
                    "batch_id": "batch_67890",
                    "requested_pipeline": "spellcheck",
                    "client_correlation_id": None,
                    "user_id": "user_456",
                    "is_retry": True,
                    "retry_reason": "Spellcheck failed due to network error, retrying",
                },
            ],
        },
    }
