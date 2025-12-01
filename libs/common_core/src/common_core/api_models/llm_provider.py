"""LLM Provider Service HTTP API contracts.

This module defines the inter-service HTTP contracts for the LLM Provider Service.
These models are used by CJ Assessment Service and other services when calling
the LLM Provider Service via HTTP.

IMPORTANT: For Kafka event contracts, use models from common_core.events.cj_assessment_events.
HTTP contracts use strict typing (e.g., LLMProviderType enum) for API validation,
while event contracts use looser typing (e.g., str) for flexibility and backward compatibility.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ..config_enums import LLMProviderType
from ..domain_enums import EssayComparisonWinner

# ====================================================================
# Configuration Models
# ====================================================================


class LLMConfigOverridesHTTP(BaseModel):
    """LLM configuration overrides for HTTP API requests.

    This model uses strict typing (LLMProviderType enum) for HTTP API validation.
    For Kafka events, use LLMConfigOverrides from cj_assessment_events which uses
    str for provider_override to allow looser coupling between services.
    """

    provider_override: LLMProviderType | None = None
    model_override: str | None = None
    temperature_override: float | None = Field(None, ge=0.0, le=2.0)
    system_prompt_override: str | None = None
    max_tokens_override: int | None = Field(None, gt=0)
    reasoning_effort: str | None = Field(
        default=None,
        pattern=r"^(none|low|medium|high)$",
        description="Optional reasoning effort hint for GPT-5 family models.",
    )
    output_verbosity: str | None = Field(
        default=None,
        pattern=r"^(low|medium|high)$",
        description="Optional output verbosity hint for GPT-5 family models.",
    )


# ====================================================================
# Request Models
# ====================================================================


class LLMComparisonRequest(BaseModel):
    """Request model for LLM essay comparison.

    Preferred path is to send `prompt_blocks` (cache-friendly, ordered with TTL rules)
    while retaining the legacy `user_prompt` string for backward compatibility.
    """

    user_prompt: str = Field(..., description="The complete comparison prompt including essays")
    prompt_blocks: list[dict[str, Any]] | None = Field(
        default=None,
        description=(
            "Optional structured prompt blocks (cache-friendly); user_prompt remains for fallback"
        ),
    )

    # REQUIRED callback topic for async processing
    callback_topic: str = Field(
        ..., description="Kafka topic for result callback (required for all requests)"
    )

    # Optional configuration overrides
    llm_config_overrides: LLMConfigOverridesHTTP | None = None

    # Correlation tracking
    correlation_id: UUID | None = None
    user_id: str | None = None

    # Metadata for extensibility
    metadata: dict[str, Any] = Field(default_factory=dict)


# ====================================================================
# Response Models
# ====================================================================


class LLMComparisonResponse(BaseModel):
    """Response model for LLM essay comparison."""

    # Core result fields (matching CJ Assessment expectations)
    winner: EssayComparisonWinner = Field(description="Selected essay")
    justification: str = Field(description="Justification for the choice")
    confidence: float = Field(description="Confidence score (1-5)")

    # Provider information
    provider: str = Field(description="Actual provider used")
    model: str = Field(description="Actual model used")

    # Performance metrics
    response_time_ms: int = Field(description="Response time in milliseconds")
    token_usage: dict[str, int] | None = Field(description="Token usage stats")
    cost_estimate: float | None = Field(description="Estimated cost in USD")

    # Tracing
    correlation_id: UUID = Field(description="Request correlation ID")
    trace_id: str | None = Field(description="Distributed trace ID")

    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMQueuedResponse(BaseModel):
    """Response model when LLM request is queued for callback delivery."""

    queue_id: UUID = Field(description="Unique queue identifier for tracking")
    status: str = Field(default="queued", description="Request status")
    message: str = Field(
        default="Request queued for processing", description="User-friendly status message"
    )
    estimated_wait_minutes: int | None = Field(
        default=None, description="Estimated wait time in minutes"
    )
