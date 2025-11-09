"""
Centralized model manifest for LLM Provider Service.

This module provides a single source of truth for all supported LLM models
across providers. It defines model capabilities, API requirements, and
compatibility metadata.

Architecture:
- ModelConfig: Pydantic model for individual model configurations
- ModelRegistry: Collection of all supported models by provider
- Helper functions for querying and validating models

Usage:
    from services.llm_provider_service.model_manifest import get_model_config, ProviderName

    # Get default model for a provider
    config = get_model_config(ProviderName.ANTHROPIC)

    # Get specific model
    config = get_model_config(ProviderName.ANTHROPIC, "claude-3-5-haiku-20241022")
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


# =============================================================================
# Anthropic Models (Primary Focus)
# =============================================================================

ANTHROPIC_MODELS = [
    ModelConfig(
        model_id="claude-haiku-4-5-20251001",
        provider=ProviderName.ANTHROPIC,
        display_name="Claude Haiku 4.5",
        api_version="2023-06-01",
        structured_output_method=StructuredOutputMethod.TOOL_USE,
        capabilities={
            "tool_use": True,
            "vision": True,
            "function_calling": True,
            "json_mode": True,
            "extended_thinking": True,
        },
        max_tokens=64_000,  # 64K max output
        context_window=200_000,  # 200K context
        supports_streaming=True,
        release_date=date(2025, 10, 1),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.001,  # $1 per million
        cost_per_1k_output_tokens=0.005,  # $5 per million
        recommended_for=[
            "comparison",
            "analysis",
            "structured_output",
            "cost_sensitive_workloads",
            "high_volume",
        ],
        notes="Fastest model with near-frontier intelligence. 64K max output, "
        "vision support, and extended thinking. Ideal for cost-effective "
        "high-volume essay comparisons.",
    ),
    ModelConfig(
        model_id="claude-sonnet-4-5-20250929",
        provider=ProviderName.ANTHROPIC,
        display_name="Claude Sonnet 4.5",
        api_version="2023-06-01",
        structured_output_method=StructuredOutputMethod.TOOL_USE,
        capabilities={
            "tool_use": True,
            "vision": True,
            "function_calling": True,
            "json_mode": True,
            "extended_thinking": True,
        },
        max_tokens=64_000,  # 64K max output
        context_window=200_000,  # 200K context (1M beta available)
        supports_streaming=True,
        release_date=date(2025, 9, 29),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.003,  # $3 per million
        cost_per_1k_output_tokens=0.015,  # $15 per million
        recommended_for=[
            "complex_analysis",
            "high_quality_comparison",
            "reasoning",
            "complex_agents",
            "coding",
        ],
        notes="Smartest model for complex agents and coding. 64K max output, "
        "vision support, extended thinking. Use when quality and advanced "
        "reasoning matter more than cost.",
    ),
]

# =============================================================================
# OpenAI Models
# =============================================================================

OPENAI_MODELS = [
    ModelConfig(
        model_id="gpt-5-2025-08-07",
        provider=ProviderName.OPENAI,
        display_name="GPT-5",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
        },
        max_tokens=16384,
        context_window=272_000,  # 272K context window
        supports_streaming=True,
        release_date=date(2025, 8, 7),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00125,  # $1.25 per million
        cost_per_1k_output_tokens=0.01000,  # $10.00 per million
        recommended_for=["complex_analysis", "reasoning", "general_purpose"],
        notes="Latest GPT-5 flagship model. 272K context window, "
        "strong reasoning and analysis capabilities.",
    ),
    ModelConfig(
        model_id="gpt-5-mini-2025-08-07",
        provider=ProviderName.OPENAI,
        display_name="GPT-5 Mini",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
        },
        max_tokens=16384,
        context_window=272_000,  # 272K context window
        supports_streaming=True,
        release_date=date(2025, 8, 7),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00025,  # $0.25 per million
        cost_per_1k_output_tokens=0.00200,  # $2.00 per million
        recommended_for=["comparison", "general_purpose", "cost_effective"],
        notes="Cost-effective GPT-5 model. Best balance of performance and price. "
        "272K context window.",
    ),
    ModelConfig(
        model_id="gpt-5-nano-2025-08-07",
        provider=ProviderName.OPENAI,
        display_name="GPT-5 Nano",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
        },
        max_tokens=16384,
        context_window=272_000,  # 272K context window
        supports_streaming=True,
        release_date=date(2025, 8, 7),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00005,  # $0.05 per million
        cost_per_1k_output_tokens=0.00040,  # $0.40 per million
        recommended_for=["high_volume", "cost_sensitive_workloads", "simple_tasks"],
        notes="Smallest, cheapest GPT-5 model. Ideal for high-volume, "
        "cost-sensitive workloads. 272K context window.",
    ),
    ModelConfig(
        model_id="gpt-5-pro-2025-10-06",
        provider=ProviderName.OPENAI,
        display_name="GPT-5 Pro",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
        },
        max_tokens=16384,
        context_window=272_000,  # 272K context window
        supports_streaming=True,
        release_date=date(2025, 10, 6),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.01500,  # $15.00 per million
        cost_per_1k_output_tokens=0.12000,  # $120.00 per million
        recommended_for=["complex_reasoning", "expert_analysis", "premium_quality"],
        notes="Premium flagship GPT-5 model. Highest quality and reasoning. "
        "Use when quality matters more than cost.",
    ),
    ModelConfig(
        model_id="gpt-4.1-2025-04-14",
        provider=ProviderName.OPENAI,
        display_name="GPT-4.1",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
        },
        max_tokens=16384,
        context_window=1_047_576,  # ~1M context window
        supports_streaming=True,
        release_date=date(2025, 4, 14),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00200,  # $2.00 per million
        cost_per_1k_output_tokens=0.00800,  # $8.00 per million
        recommended_for=["long_context", "analysis", "general_purpose"],
        notes="GPT-4.1 with 1M context window. 26% less expensive than GPT-4o "
        "for median queries.",
    ),
    ModelConfig(
        model_id="gpt-4.1-mini-2025-04-14",
        provider=ProviderName.OPENAI,
        display_name="GPT-4.1 Mini",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
        },
        max_tokens=16384,
        context_window=1_047_576,  # ~1M context window
        supports_streaming=True,
        release_date=date(2025, 4, 14),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00040,  # $0.40 per million
        cost_per_1k_output_tokens=0.00160,  # $1.60 per million
        recommended_for=["long_context", "cost_effective", "general_purpose"],
        notes="Cost-effective GPT-4.1 with 1M context window. Good balance "
        "of performance and price.",
    ),
    ModelConfig(
        model_id="gpt-4.1-nano-2025-04-14",
        provider=ProviderName.OPENAI,
        display_name="GPT-4.1 Nano",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
        },
        max_tokens=16384,
        context_window=1_047_576,  # ~1M context window
        supports_streaming=True,
        release_date=date(2025, 4, 14),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00010,  # $0.10 per million
        cost_per_1k_output_tokens=0.00040,  # $0.40 per million
        recommended_for=["long_context", "high_volume", "cost_sensitive_workloads"],
        notes="Cheapest GPT-4.1 model with 1M context window. Ideal for "
        "cost-sensitive long-context workloads.",
    ),
    ModelConfig(
        model_id="gpt-4o-2024-11-20",
        provider=ProviderName.OPENAI,
        display_name="GPT-4o",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
            "vision": True,
        },
        max_tokens=16384,
        context_window=128_000,
        supports_streaming=True,
        release_date=date(2024, 11, 20),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00250,  # $2.50 per million
        cost_per_1k_output_tokens=0.01000,  # $10.00 per million
        recommended_for=["multimodal", "vision", "analysis"],
        notes="Latest GPT-4o multimodal model. Supports vision and image understanding.",
    ),
    ModelConfig(
        model_id="gpt-4o-mini-2024-07-18",
        provider=ProviderName.OPENAI,
        display_name="GPT-4o Mini",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "response_format_schema": True,
            "vision": True,
        },
        max_tokens=16384,
        context_window=128_000,
        supports_streaming=True,
        release_date=date(2024, 7, 18),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00015,  # $0.15 per million
        cost_per_1k_output_tokens=0.00060,  # $0.60 per million
        recommended_for=["multimodal", "vision", "cost_effective"],
        notes="Cost-effective GPT-4o model with vision support. Over 60% cheaper "
        "than GPT-3.5 Turbo.",
    ),
]

# =============================================================================
# Google Models
# =============================================================================

GOOGLE_MODELS = [
    ModelConfig(
        model_id="gemini-2.5-flash-preview-05-20",
        provider=ProviderName.GOOGLE,
        display_name="Gemini 2.5 Flash (Preview)",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_MIME_TYPE,
        capabilities={
            "function_calling": True,
            "json_mode": True,
            "multimodal": True,
        },
        max_tokens=8192,
        context_window=1_048_576,  # 1M context window
        supports_streaming=True,
        release_date=date(2024, 5, 20),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.00000,  # Preview pricing - verify
        cost_per_1k_output_tokens=0.00000,  # Preview pricing - verify
        recommended_for=["long_context", "multimodal"],
        notes="Preview model with very large context window. "
        "Pricing subject to change after preview period.",
    ),
]

# =============================================================================
# OpenRouter Models
# =============================================================================

OPENROUTER_MODELS = [
    ModelConfig(
        model_id="anthropic/claude-haiku-4-5-20251001",
        provider=ProviderName.OPENROUTER,
        display_name="Claude Haiku 4.5 (via OpenRouter)",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_OBJECT,
        capabilities={
            "tool_use": False,  # OpenRouter may not support all features
            "json_mode": True,
        },
        max_tokens=64_000,
        context_window=200_000,
        supports_streaming=True,
        release_date=date(2025, 10, 1),
        is_deprecated=False,
        cost_per_1k_input_tokens=0.001,  # OpenRouter pricing may differ
        cost_per_1k_output_tokens=0.005,  # OpenRouter pricing may differ
        recommended_for=["fallback", "redundancy"],
        notes="Access to Anthropic models via OpenRouter. Conditional feature support "
        "based on model capabilities.",
    ),
]

# =============================================================================
# Registry Construction
# =============================================================================

SUPPORTED_MODELS: ModelRegistry = ModelRegistry(
    models={
        ProviderName.ANTHROPIC: ANTHROPIC_MODELS,
        ProviderName.OPENAI: OPENAI_MODELS,
        ProviderName.GOOGLE: GOOGLE_MODELS,
        ProviderName.OPENROUTER: OPENROUTER_MODELS,
        ProviderName.MOCK: [],  # Mock provider has no real models
    },
    default_models={
        ProviderName.ANTHROPIC: "claude-haiku-4-5-20251001",
        ProviderName.OPENAI: "gpt-5-mini-2025-08-07",
        ProviderName.GOOGLE: "gemini-2.5-flash-preview-05-20",
        ProviderName.OPENROUTER: "anthropic/claude-haiku-4-5-20251001",
        ProviderName.MOCK: "",  # Mock has no default
    },
)


# =============================================================================
# Helper Functions
# =============================================================================


def get_model_config(provider: ProviderName, model_id: str | None = None) -> ModelConfig:
    """Retrieve model configuration by provider and optional model ID.

    Args:
        provider: The LLM provider
        model_id: Specific model ID. If None, returns provider's default model.

    Returns:
        ModelConfig for the requested model

    Raises:
        ValueError: If provider is unknown or model_id is not found

    Examples:
        >>> # Get default Anthropic model
        >>> config = get_model_config(ProviderName.ANTHROPIC)
        >>> config.model_id
        'claude-haiku-4-5-20251001'

        >>> # Get specific model
        >>> config = get_model_config(ProviderName.ANTHROPIC, "claude-sonnet-4-5-20250929")
        >>> config.display_name
        'Claude Sonnet 4.5'
    """
    if provider not in SUPPORTED_MODELS.models:
        raise ValueError(
            f"Unknown provider: {provider}. Supported: {list(SUPPORTED_MODELS.models.keys())}"
        )

    # Get default model if none specified
    if model_id is None:
        model_id = SUPPORTED_MODELS.default_models.get(provider)
        if not model_id:
            raise ValueError(f"No default model configured for provider: {provider}")

    # Find requested model
    provider_models = SUPPORTED_MODELS.models[provider]
    for model in provider_models:
        if model.model_id == model_id:
            return model

    # Model not found - provide helpful error
    available_ids = [m.model_id for m in provider_models]
    raise ValueError(
        f"Model '{model_id}' not found for provider '{provider}'. Available models: {available_ids}"
    )


def list_models(provider: ProviderName | None = None) -> list[ModelConfig]:
    """List all models, optionally filtered by provider.

    Args:
        provider: If specified, only return models for this provider.
                 If None, return all models across all providers.

    Returns:
        List of ModelConfig objects

    Examples:
        >>> # List all Anthropic models
        >>> models = list_models(ProviderName.ANTHROPIC)
        >>> len(models)
        2

        >>> # List all models
        >>> all_models = list_models()
        >>> len(all_models) >= 4
        True
    """
    if provider is None:
        # Return all models from all providers
        all_models: list[ModelConfig] = []
        for provider_models in SUPPORTED_MODELS.models.values():
            all_models.extend(provider_models)
        return all_models

    return SUPPORTED_MODELS.models.get(provider, [])


def get_default_model_id(provider: ProviderName) -> str:
    """Get the default model ID for a provider.

    Args:
        provider: The LLM provider

    Returns:
        Default model_id string

    Raises:
        ValueError: If provider is unknown or has no default

    Examples:
        >>> get_default_model_id(ProviderName.ANTHROPIC)
        'claude-3-5-haiku-20241022'
    """
    if provider not in SUPPORTED_MODELS.default_models:
        raise ValueError(f"Unknown provider: {provider}")

    model_id = SUPPORTED_MODELS.default_models[provider]
    if not model_id:
        raise ValueError(f"No default model configured for provider: {provider}")

    return model_id


def validate_model_capability(provider: ProviderName, model_id: str, capability: str) -> bool:
    """Check if a specific model supports a capability.

    Args:
        provider: The LLM provider
        model_id: The model identifier
        capability: Capability to check (e.g., 'tool_use', 'vision')

    Returns:
        True if capability is supported, False otherwise

    Raises:
        ValueError: If provider or model_id is invalid

    Examples:
        >>> validate_model_capability(
        ...     ProviderName.ANTHROPIC,
        ...     "claude-3-5-haiku-20241022",
        ...     "tool_use"
        ... )
        True
    """
    config = get_model_config(provider, model_id)
    return config.capabilities.get(capability, False)
