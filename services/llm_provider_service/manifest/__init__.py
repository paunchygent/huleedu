"""LLM Provider Service model manifest package.

This package provides a modular, maintainable structure for LLM model definitions.

Structure:
- types.py: Core types (ModelConfig, ModelRegistry, ProviderName, etc.)
- openai.py: OpenAI model definitions and validators
- anthropic.py: Anthropic (Claude) model definitions and validators
- google.py: Google (Gemini) model definitions and validators
- openrouter.py: OpenRouter model definitions and validators

Usage:
    from services.llm_provider_service.manifest import get_model_config, ProviderName

    # Get default model for a provider
    config = get_model_config(ProviderName.ANTHROPIC)

    # Get specific model
    config = get_model_config(ProviderName.OPENAI, "gpt-5-mini-2025-08-07")
"""

from __future__ import annotations

from typing import Callable

from services.llm_provider_service.manifest import anthropic, google, openai, openrouter
from services.llm_provider_service.manifest.types import (
    ModelConfig,
    ModelRegistry,
    ProviderName,
    StructuredOutputMethod,
)

# =============================================================================
# Build Global Registry by Aggregating Provider Modules
# =============================================================================

SUPPORTED_MODELS: ModelRegistry = ModelRegistry(
    models={
        ProviderName.ANTHROPIC: anthropic.ANTHROPIC_MODELS,
        ProviderName.OPENAI: openai.OPENAI_MODELS,
        ProviderName.GOOGLE: google.GOOGLE_MODELS,
        ProviderName.OPENROUTER: openrouter.OPENROUTER_MODELS,
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
# Aggregate Per-Model Validators from All Providers
# =============================================================================

MODEL_VALIDATORS: dict[str, Callable[[str], bool]] = {
    **openai.MODEL_VALIDATORS,
    **anthropic.MODEL_VALIDATORS,
    **google.MODEL_VALIDATORS,
    **openrouter.MODEL_VALIDATORS,
}


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
        'claude-haiku-4-5-20251001'
    """
    if provider not in SUPPORTED_MODELS.default_models:
        raise ValueError(f"Unknown provider: {provider}")

    model_id = SUPPORTED_MODELS.default_models[provider]
    if not model_id:
        raise ValueError(f"No default model configured for provider: {provider}")

    return model_id


def validate_model_capability(provider: ProviderName, model_id: str, capability: str) -> bool:
    """Check if a specific model supports a capability.

    This function uses a three-tier validation strategy:
    1. Check per-model validator function if registered
    2. Fall back to model capabilities dict
    3. (Future) Check dynamic overrides if enabled

    Args:
        provider: The LLM provider
        model_id: The model identifier
        capability: Capability to check (e.g., 'tool_use', 'vision', 'function_calling')

    Returns:
        True if capability is supported, False otherwise

    Raises:
        ValueError: If provider or model_id is invalid

    Examples:
        >>> validate_model_capability(
        ...     ProviderName.ANTHROPIC,
        ...     "claude-haiku-4-5-20251001",
        ...     "tool_use"
        ... )
        True

        >>> validate_model_capability(
        ...     ProviderName.OPENAI,
        ...     "gpt-5-mini-2025-08-07",
        ...     "vision"
        ... )
        False
    """
    # Get model config (validates provider and model_id)
    config = get_model_config(provider, model_id)

    # Tier 1: Check per-model validator function if registered
    if model_id in MODEL_VALIDATORS:
        validator = MODEL_VALIDATORS[model_id]
        return validator(capability)

    # Tier 2: Fall back to capabilities dict
    return config.capabilities.get(capability, False)


# =============================================================================
# Public API Exports
# =============================================================================

__all__ = [
    # Types
    "ModelConfig",
    "ModelRegistry",
    "ProviderName",
    "StructuredOutputMethod",
    # Registry
    "SUPPORTED_MODELS",
    "MODEL_VALIDATORS",
    # Helper Functions
    "get_model_config",
    "list_models",
    "get_default_model_id",
    "validate_model_capability",
]
