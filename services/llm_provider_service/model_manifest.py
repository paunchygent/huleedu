"""Centralized model manifest for LLM Provider Service.

This module provides a single source of truth for all supported LLM models
across providers. It defines model capabilities, API requirements, and
compatibility metadata.

BACKWARD COMPATIBILITY LAYER:
This module now re-exports from the modularized manifest package for
maintainability. The public API remains unchanged.

Architecture:
- ModelConfig: Pydantic model for individual model configurations
- ModelRegistry: Collection of all supported models by provider
- Helper functions for querying and validating models

Modular Structure (NEW):
- manifest/types.py: Core types
- manifest/openai.py: OpenAI model definitions
- manifest/anthropic.py: Anthropic (Claude) model definitions
- manifest/google.py: Google (Gemini) model definitions
- manifest/openrouter.py: OpenRouter model definitions
- manifest/__init__.py: Aggregator and helper functions

Usage:
    from services.llm_provider_service.model_manifest import get_model_config, ProviderName

    # Get default model for a provider
    config = get_model_config(ProviderName.ANTHROPIC)

    # Get specific model
    config = get_model_config(ProviderName.ANTHROPIC, "claude-haiku-4-5-20251001")
"""

from __future__ import annotations

# Re-export all public types and functions from manifest package
from services.llm_provider_service.manifest import (
    MODEL_VALIDATORS,
    SUPPORTED_MODELS,
    ModelConfig,
    ModelRegistry,
    ProviderName,
    StructuredOutputMethod,
    get_default_model_id,
    get_model_config,
    list_models,
    validate_model_capability,
)

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
