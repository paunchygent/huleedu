"""Core types for LLM Provider Service manifest.

This module defines the foundational types used across the model manifest:
- ModelConfig: Configuration for individual LLM models
- ModelRegistry: Collection of all supported models by provider
- Enums: ProviderName, StructuredOutputMethod

All model definitions in provider-specific modules use these types.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StructuredOutputMethod(str, Enum):
    """Methods for obtaining structured JSON output from LLM providers."""

    TOOL_USE = "tool_use"  # Anthropic tool/function calling
    JSON_SCHEMA = "json_schema"  # OpenAI response_format with schema
    JSON_MIME_TYPE = "json_mime_type"  # Google response_mime_type
    JSON_OBJECT = "json_object"  # OpenRouter json_object format
    NATIVE_JSON = "native_json"  # Native JSON mode (future providers)


class ProviderName(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    OPENROUTER = "openrouter"
    MOCK = "mock"  # Testing only


class ModelConfig(BaseModel):
    """Configuration and metadata for a single LLM model.

    This model is frozen (immutable) to ensure manifest integrity.
    All model updates should create new ModelConfig instances.

    Parameter Compatibility Flags:
    - supports_temperature: Model accepts custom temperature values
    - supports_top_p: Model accepts top_p sampling parameter
    - supports_frequency_penalty: Model accepts frequency_penalty parameter
    - supports_presence_penalty: Model accepts presence_penalty parameter
    - uses_max_completion_tokens: Model uses max_completion_tokens instead of max_tokens

    Note: GPT-5 family and reasoning models (o1, o3) do NOT support sampling parameters.
    """

    model_config = ConfigDict(frozen=True)

    # Identity
    model_id: str = Field(
        ...,
        description="Provider-specific model identifier (e.g., 'claude-3-5-haiku-20241022')",
    )
    provider: ProviderName = Field(..., description="Provider hosting this model")
    display_name: str = Field(
        ..., description="Human-readable model name (e.g., 'Claude 3.5 Haiku')"
    )

    # API Configuration
    api_version: str = Field(
        ..., description="API version string required by provider (e.g., '2023-06-01')"
    )
    structured_output_method: StructuredOutputMethod = Field(
        ..., description="Method used to obtain structured JSON responses"
    )

    # Parameter Compatibility (NEW - for conditional parameter sending)
    supports_temperature: bool = Field(
        default=True,
        description="Model supports custom temperature parameter (GPT-5 family: False)",
    )
    supports_top_p: bool = Field(
        default=True, description="Model supports top_p sampling parameter (GPT-5 family: False)"
    )
    supports_frequency_penalty: bool = Field(
        default=True,
        description="Model supports frequency_penalty parameter (GPT-5 family: False)",
    )
    supports_presence_penalty: bool = Field(
        default=True,
        description="Model supports presence_penalty parameter (GPT-5 family: False)",
    )
    uses_max_completion_tokens: bool = Field(
        default=False,
        description="Model uses max_completion_tokens instead of max_tokens (reasoning models: True)",
    )

    # Capabilities
    capabilities: dict[str, bool] = Field(
        default_factory=dict,
        description="Model capabilities (e.g., {'tool_use': True, 'vision': True})",
    )

    # Performance Characteristics
    max_tokens: int = Field(default=4096, description="Maximum output tokens supported")
    context_window: int = Field(default=200_000, description="Total context window size")
    supports_streaming: bool = Field(default=True, description="Supports streaming responses")

    # Metadata
    release_date: date | None = Field(default=None, description="Model release date")
    is_deprecated: bool = Field(default=False, description="Model is deprecated")
    deprecation_date: date | None = Field(
        default=None, description="Date model will be/was deprecated"
    )

    # Cost Tracking (optional, can be None if unknown)
    cost_per_1k_input_tokens: float | None = Field(
        default=None, description="Cost per 1000 input tokens in USD"
    )
    cost_per_1k_output_tokens: float | None = Field(
        default=None, description="Cost per 1000 output tokens in USD"
    )

    # Quality Metadata
    recommended_for: list[str] = Field(
        default_factory=list,
        description="Use cases this model excels at (e.g., ['comparison', 'analysis'])",
    )
    notes: str = Field(default="", description="Additional notes or warnings")


class ModelRegistry(BaseModel):
    """Registry of all supported models across providers.

    This is the single source of truth for model configurations.
    """

    models: dict[ProviderName, list[ModelConfig]] = Field(
        ..., description="All supported models, organized by provider"
    )
    default_models: dict[ProviderName, str] = Field(
        ..., description="Default model_id for each provider"
    )
