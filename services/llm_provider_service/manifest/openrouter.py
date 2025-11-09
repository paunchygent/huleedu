"""OpenRouter model definitions and validators.

This module contains OpenRouter-proxied model configurations.

OpenRouter provides access to various models through a unified API.
Parameter support depends on the underlying model.
"""

from __future__ import annotations

from datetime import date
from typing import Callable

from services.llm_provider_service.manifest.types import (
    ModelConfig,
    ProviderName,
    StructuredOutputMethod,
)


# =============================================================================
# OpenRouter Models - PARAMETER SUPPORT VARIES BY UNDERLYING MODEL
# =============================================================================

OPENROUTER_MODELS = [
    ModelConfig(
        model_id="anthropic/claude-haiku-4-5-20251001",
        provider=ProviderName.OPENROUTER,
        display_name="Claude Haiku 4.5 (via OpenRouter)",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_OBJECT,
        # Claude via OpenRouter supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
# Per-Model Validators
# =============================================================================


def validate_model_capability__anthropic_claude_haiku_4_5_20251001(capability: str) -> bool:
    """Validator for Claude Haiku 4.5 via OpenRouter."""
    # OpenRouter may not support all Claude features (e.g., tool_use)
    return capability in ["json_mode"]


# Validator registry mapping model_id to validator function
MODEL_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "anthropic/claude-haiku-4-5-20251001": validate_model_capability__anthropic_claude_haiku_4_5_20251001,
}
