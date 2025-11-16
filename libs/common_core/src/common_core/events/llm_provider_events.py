"""Event models for LLM Provider Service."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from common_core.config_enums import LLMProviderType
from common_core.domain_enums import EssayComparisonWinner
from common_core.models.error_models import ErrorDetail


class LLMRequestStartedV1(BaseModel):
    """Event published when LLM request begins."""

    provider: LLMProviderType
    request_type: str  # "comparison", "generation", etc.
    correlation_id: UUID
    user_id: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMRequestCompletedV1(BaseModel):
    """Event published when LLM request completes."""

    provider: LLMProviderType
    request_type: str
    correlation_id: UUID
    success: bool
    response_time_ms: int
    error_message: str | None = None
    token_usage: Dict[str, int] | None = None  # prompt_tokens, completion_tokens
    cost_estimate: float | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMProviderFailureV1(BaseModel):
    """Event published when LLM provider experiences failure."""

    provider: LLMProviderType
    failure_type: str  # "timeout", "rate_limit", "service_unavailable"
    correlation_id: UUID
    error_details: str
    circuit_breaker_opened: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMUsageAnalyticsV1(BaseModel):
    """Periodic analytics event for LLM usage."""

    period_start: datetime
    period_end: datetime
    provider_stats: Dict[str, Dict[str, Any]]  # Stats by provider
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_tokens: Dict[str, int]  # By token type
    total_cost: float
    average_response_time_ms: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMCostAlertV1(BaseModel):
    """Event published when cost threshold is exceeded."""

    alert_type: str  # "daily_limit", "monthly_limit", "rate_spike"
    provider: LLMProviderType | None = None
    current_cost: float
    threshold: float
    period: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMCostTrackingV1(
    BaseModel
):  # TODO: IMPLEMENT IN RESULT AGGREGATOR SERVICE or DEDICATED METRICS/BILLING SERVICE
    """Event for downstream cost aggregation and billing (Result Aggregator Service)."""

    correlation_id: UUID
    provider: LLMProviderType
    model: str
    request_type: str  # "comparison", "generation", etc.

    # Cost breakdown
    cost_estimate_usd: float
    token_usage: Dict[str, int]  # prompt_tokens, completion_tokens, total_tokens

    # Request metadata for cost attribution
    user_id: str | None = None
    organization_id: str | None = None  # For multi-tenant billing
    service_name: str  # Which service made the request (e.g., "cj_assessment_service")

    # Timing for cost analysis
    request_timestamp: datetime
    response_time_ms: int

    metadata: Dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Token usage breakdown for LLM operations."""

    prompt_tokens: int = Field(default=0, ge=0, description="Number of tokens in the prompt")
    completion_tokens: int = Field(
        default=0, ge=0, description="Number of tokens in the completion"
    )
    total_tokens: int = Field(default=0, ge=0, description="Total number of tokens used")


class LLMComparisonResultV1(BaseModel):
    """
    Event payload for LLM comparison results delivered via callback.
    Supports both success and error scenarios.
    """

    # Request identification
    request_id: str = Field(description="Original queue ID from LLM Provider Service")
    correlation_id: UUID = Field(description="Correlation ID for distributed tracing")

    # === SUCCESS FIELDS (mutually exclusive with error field) ===
    winner: Optional[EssayComparisonWinner] = Field(
        None, description="Selected essay: 'essay_a' or 'essay_b'"
    )
    justification: Optional[str] = Field(
        None, max_length=500, description="Justification for the decision"
    )
    confidence: Optional[float] = Field(None, ge=1.0, le=5.0, description="Confidence score (1-5)")

    # === ERROR FIELD (mutually exclusive with success fields) ===
    error_detail: Optional[ErrorDetail] = Field(
        None, description="Structured error information if comparison failed"
    )

    # === COMMON METADATA ===
    provider: LLMProviderType = Field(description="Provider used for comparison")
    model: str = Field(description="Model name/version used")

    # Performance metrics
    response_time_ms: int = Field(ge=0, description="Total processing time in milliseconds")
    token_usage: TokenUsage = Field(default_factory=TokenUsage, description="Token usage breakdown")
    cost_estimate: float = Field(ge=0.0, description="Estimated cost in USD")

    # Timestamps
    requested_at: datetime = Field(description="When request was originally submitted")
    completed_at: datetime = Field(description="When processing completed")

    # Tracing
    trace_id: Optional[str] = Field(None, description="Distributed trace ID")
    request_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Opaque CJ-supplied metadata echoed back in callbacks. "
            "Must always include `essay_a_id`/`essay_b_id` for correlation; "
            "`bos_batch_id`, `prompt_sha256`, and future batching hints are additive."
        ),
    )

    @model_validator(mode="after")
    def validate_exclusive_fields(self) -> "LLMComparisonResultV1":
        """Ensure either success fields or error_detail is set, but not both."""
        has_success_fields = self.winner is not None
        has_error_field = self.error_detail is not None

        if has_success_fields and has_error_field:
            raise ValueError("Cannot have both success fields and error_detail")

        if not has_success_fields and not has_error_field:
            raise ValueError("Must have either success fields or error_detail")

        # If success, all success fields must be set
        if has_success_fields:
            if self.justification is None or self.confidence is None:
                raise ValueError(
                    "All success fields (winner, justification, confidence) must be set together"
                )

        return self

    @property
    def is_success(self) -> bool:
        """Check if this represents a successful comparison."""
        return self.winner is not None

    @property
    def is_error(self) -> bool:
        """Check if this represents an error result."""
        return self.error_detail is not None
