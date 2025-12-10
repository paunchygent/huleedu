"""Internal Pydantic models for LLM Provider Service."""

from datetime import datetime, timezone
from enum import StrEnum
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


class BatchJobStatus(StrEnum):
    """Lifecycle status for provider batch jobs."""

    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchJobItemStatus(StrEnum):
    """Outcome status for individual batch job items."""

    SUCCESS = "success"
    FAILED = "failed"


class BatchJobItem(BaseModel):
    """Link a queued request to a provider-native batch job item."""

    queue_id: UUID = Field(description="Queue identifier for the originating request")
    provider: LLMProviderType = Field(description="Provider responsible for this item")
    model: str = Field(description="Model identifier used for this item")
    custom_id: str = Field(
        description=(
            "Provider-facing custom identifier used to correlate job results back to queue items"
        )
    )
    user_prompt: str = Field(description="Rendered comparison prompt for this item")
    prompt_blocks: list[dict[str, Any]] | None = Field(
        default=None,
        description="Structured prompt blocks used when constructing provider payloads",
    )
    correlation_id: UUID = Field(
        description="Correlation identifier propagated from the original comparison request"
    )
    overrides: Dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved override kwargs (model, temperature, tokens, etc.)",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Caller-supplied metadata to preserve through provider batch APIs",
    )


class BatchJobResult(BaseModel):
    """Per-item outcome for a provider batch job."""

    queue_id: UUID = Field(description="Queue identifier for the originating request")
    provider: LLMProviderType = Field(description="Provider that executed the item")
    model: str = Field(description="Model used for the item")
    status: BatchJobItemStatus = Field(description="Item-level outcome status")
    response: Optional["LLMOrchestratorResponse"] = Field(
        default=None,
        description="Normalized LLM response when the item succeeds",
    )
    error_code: Optional[ErrorCode] = Field(
        default=None,
        description="Optional error code when the item fails",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Human-readable error message when the item fails",
    )
    raw_error: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider- or implementation-specific error payload for diagnostics",
    )


class BatchJobRef(BaseModel):
    """Handle for tracking provider batch job lifecycle."""

    job_id: UUID = Field(description="Internal identifier for the batch job")
    provider: LLMProviderType = Field(description="Provider responsible for the job")
    model: str = Field(description="Model used for the job")
    status: BatchJobStatus = Field(description="Current lifecycle status for the job")
    provider_job_id: Optional[str] = Field(
        default=None,
        description="Identifier returned by the provider for this job, if applicable",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the job was created",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the job reached a terminal state",
    )
