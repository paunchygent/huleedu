"""Internal Pydantic models for LLM Provider Service."""

from typing import Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field

from common_core import LLMProviderType
from common_core.error_enums import ErrorCode
from services.llm_provider_service.error_types import LLMProviderErrorType


class LLMProviderResponse(BaseModel):
    """Internal model for LLM provider responses."""

    # Core comparison result
    choice: str = Field(description="Selected essay (A or B)")
    reasoning: str = Field(description="Reasoning for the choice")
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


class LLMOrchestratorResponse(BaseModel):
    """Internal model for orchestrator responses."""

    # Core result (from provider)
    choice: str = Field(description="Selected essay (A or B)")
    reasoning: str = Field(description="Reasoning for the choice")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")

    # Provider information
    provider: LLMProviderType = Field(description="Actual provider used")
    model: str = Field(description="Actual model used")

    # Performance metrics
    response_time_ms: int = Field(ge=0, description="Total response time in milliseconds")
    cached: bool = Field(default=False, description="Whether response was from cache")

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
    error_message: str = Field(description="Error message")
    provider: LLMProviderType = Field(description="Provider that failed")
    correlation_id: UUID = Field(description="Request correlation ID")
    retry_after: int | None = Field(default=None, description="Seconds to wait before retry")
    is_retryable: bool = Field(default=True, description="Whether error is retryable")
