"""Internal Pydantic models for LLM Provider Service."""

from typing import Any, Dict, Optional
from uuid import UUID

from common_core import EssayComparisonWinner, LLMProviderType
from common_core.error_enums import ErrorCode
from pydantic import BaseModel, Field

from services.llm_provider_service.error_types import LLMProviderErrorType


class LLMProviderResponse(BaseModel):
    """Internal model for LLM provider responses."""

    # Core comparison result
    winner: EssayComparisonWinner = Field(description="Selected essay")
    justification: str = Field(description="Justification for the choice")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")

    # Provider metadata
    provider: LLMProviderType = Field(description="Provider that generated the response")
    model: str = Field(description="Model used for generation")

    # Performance metrics
    prompt_tokens: int = Field(ge=0, description="Number of prompt tokens")
    completion_tokens: int = Field(ge=0, description="Number of completion tokens")
    total_tokens: int = Field(ge=0, description="Total tokens used")

    # Additional metadata
    raw_response: Dict[str, Any] = Field(default_factory=dict, description="Raw provider response")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional provider metadata"
    )


class LLMOrchestratorResponse(BaseModel):
    """Internal model for orchestrator responses."""

    # Core result (from provider)
    winner: EssayComparisonWinner = Field(description="Selected essay")
    justification: str = Field(description="Justification for the choice")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")

    # Provider information
    provider: LLMProviderType = Field(description="Actual provider used")
    model: str = Field(description="Actual model used")

    # Performance metrics
    response_time_ms: int = Field(ge=0, description="Total response time in milliseconds")

    # Token usage and cost
    token_usage: Dict[str, int] = Field(
        description="Token usage breakdown",
        default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    )
    cost_estimate: float = Field(ge=0.0, description="Estimated cost in USD")

    # Tracing
    correlation_id: UUID = Field(description="Request correlation ID")
    trace_id: str | None = Field(default=None, description="Distributed trace ID")

    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class LLMProviderError(BaseModel):
    """Model for provider error responses."""

    error_type: ErrorCode | LLMProviderErrorType = Field(description="Type of error")
    message: str = Field(description="Error message")
    provider: LLMProviderType = Field(description="Provider that failed")
    correlation_id: UUID = Field(description="Request correlation ID")
    retry_after: int | None = Field(default=None, description="Seconds to wait before retry")
    is_retryable: bool = Field(default=True, description="Whether error is retryable")


class LLMQueuedResult(BaseModel):
    """Model for queued LLM request result."""

    queue_id: UUID = Field(description="Unique queue identifier")
    correlation_id: UUID = Field(description="Request correlation ID")
    provider: LLMProviderType = Field(description="Requested provider")
    status: str = Field(default="queued", description="Request status")
    estimated_wait_minutes: int | None = Field(default=None, description="Estimated wait time")
    priority: int = Field(description="Request priority")
    queued_at: str = Field(description="ISO timestamp when queued")


class BatchComparisonItem(BaseModel):
    """Container for batch comparison processing input."""

    provider: LLMProviderType = Field(description="Provider requested for each comparison")
    user_prompt: str = Field(description="Fully rendered comparison prompt")
    prompt_blocks: list[dict[str, Any]] | None = Field(
        default=None,
        description="Structured prompt blocks (preferred for caching-capable providers)",
    )
    correlation_id: UUID = Field(description="Per-comparison correlation identifier")
    overrides: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional override kwargs forwarded to process_comparison",
    )
