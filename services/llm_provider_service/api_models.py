"""API request/response models for LLM Provider Service."""

from typing import Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field

from common_core import LLMProviderType


class LLMConfigOverrides(BaseModel):
    """LLM configuration overrides."""

    provider_override: LLMProviderType | None = None
    model_override: str | None = None
    temperature_override: float | None = Field(None, ge=0.0, le=2.0)
    system_prompt_override: str | None = None
    max_tokens_override: int | None = Field(None, gt=0)


class LLMComparisonRequest(BaseModel):
    """Request model for LLM essay comparison."""

    user_prompt: str = Field(..., description="The comparison prompt")
    essay_a: str = Field(..., description="First essay to compare")
    essay_b: str = Field(..., description="Second essay to compare")

    # Optional configuration overrides
    llm_config_overrides: LLMConfigOverrides | None = None

    # Correlation tracking
    correlation_id: UUID | None = None
    user_id: str | None = None

    # Metadata for extensibility
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMComparisonResponse(BaseModel):
    """Response model for LLM essay comparison."""

    # Core result fields (matching CJ Assessment expectations)
    winner: str = Field(description="Selected essay (Essay A or Essay B)")
    justification: str = Field(description="Justification for the choice")
    confidence: float = Field(description="Confidence score (1-5)")

    # Provider information
    provider: str = Field(description="Actual provider used")
    model: str = Field(description="Actual model used")

    # Performance metrics
    response_time_ms: int = Field(description="Response time in milliseconds")
    cached: bool = Field(default=False, description="Whether response was cached")
    token_usage: Dict[str, int] | None = Field(description="Token usage stats")
    cost_estimate: float | None = Field(description="Estimated cost in USD")

    # Tracing
    correlation_id: UUID = Field(description="Request correlation ID")
    trace_id: str | None = Field(description="Distributed trace ID")

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LLMProviderStatus(BaseModel):
    """Model for LLM provider status."""

    name: str
    enabled: bool
    available: bool
    circuit_breaker_state: str  # "closed", "open", "half_open"
    default_model: str | None = None
    last_success: str | None = None
    last_failure: str | None = None
    failure_count: int = 0
    average_response_time_ms: float | None = None


class LLMProviderListResponse(BaseModel):
    """Response model for listing LLM providers."""

    providers: list[LLMProviderStatus]
    default_provider: str
    selection_strategy: str
    total_requests_today: int = 0
    total_cost_today: float = 0.0


class HealthCheckResponse(BaseModel):
    """Health check response model."""

    status: str = Field(description="Service status")
    service: str = Field(description="Service name")
    version: str = Field(description="Service version")
    dependencies: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Status of service dependencies"
    )


class CacheStatsResponse(BaseModel):
    """Cache statistics response model."""

    total_keys: int = Field(description="Total number of cached keys")
    memory_usage_mb: float = Field(description="Memory usage in MB")
    hit_rate: float = Field(description="Cache hit rate percentage")
    miss_rate: float = Field(description="Cache miss rate percentage")
    evictions: int = Field(description="Number of evictions")
    backend: str = Field(description="Cache backend type")


class UsageSummaryResponse(BaseModel):
    """Usage summary response model."""

    period: str = Field(description="Time period for summary")
    total_requests: int = Field(description="Total requests in period")
    successful_requests: int = Field(description="Successful requests")
    failed_requests: int = Field(description="Failed requests")
    total_tokens: Dict[str, int] = Field(description="Total tokens by type")
    total_cost: float = Field(description="Total cost in USD")
    provider_breakdown: Dict[str, Dict[str, Any]] = Field(description="Usage breakdown by provider")
    cache_hit_rate: float = Field(description="Cache hit rate percentage")
