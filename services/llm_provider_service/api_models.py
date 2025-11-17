"""API request/response models for LLM Provider Service.

This module contains LPS-internal models only.
Shared HTTP contracts are in common_core.api_models.llm_provider
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


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
    dependencies: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Status of service dependencies"
    )


class UsageSummaryResponse(BaseModel):
    """Usage summary response model."""

    period: str = Field(description="Time period for summary")
    total_requests: int = Field(description="Total requests in period")
    successful_requests: int = Field(description="Successful requests")
    failed_requests: int = Field(description="Failed requests")
    total_tokens: dict[str, int] = Field(description="Total tokens by type")
    total_cost: float = Field(description="Total cost in USD")
    provider_breakdown: dict[str, dict[str, Any]] = Field(description="Usage breakdown by provider")


class ModelInfoResponse(BaseModel):
    """Model information for API exposure.

    Subset of ModelConfig fields relevant for external clients.
    Internal manifest fields (parameter compatibility flags, etc.) are excluded.
    """

    model_id: str = Field(description="Provider-specific model identifier")
    provider: str = Field(description="Provider hosting this model")
    display_name: str = Field(description="Human-readable model name")
    model_family: str = Field(description="Model family identifier")
    max_tokens: int = Field(description="Maximum output tokens supported")
    context_window: int = Field(description="Total context window size")
    supports_streaming: bool = Field(description="Supports streaming responses")
    capabilities: dict[str, bool] = Field(description="Model capabilities")
    cost_per_1k_input_tokens: float | None = Field(
        default=None, description="Cost per 1000 input tokens in USD"
    )
    cost_per_1k_output_tokens: float | None = Field(
        default=None, description="Cost per 1000 output tokens in USD"
    )
    is_deprecated: bool = Field(description="Model is deprecated")
    release_date: date | None = Field(default=None, description="Model release date")
    recommended_for: list[str] = Field(description="Use cases this model excels at")


class ModelManifestResponse(BaseModel):
    """Response model for model manifest endpoint.

    Returns all available models grouped by provider.
    """

    providers: dict[str, list[ModelInfoResponse]] = Field(
        description="Models grouped by provider name"
    )
    total_models: int = Field(description="Total number of models across all providers")
