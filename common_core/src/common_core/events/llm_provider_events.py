"""Event models for LLM Provider Service."""

from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field

from common_core.config_enums import LLMProviderType


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
