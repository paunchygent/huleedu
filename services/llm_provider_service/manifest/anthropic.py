"""Anthropic (Claude) model definitions and validators.

This module contains all Anthropic Claude model configurations.

All Claude models support standard sampling parameters (temperature, top_p, etc.).
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
# Claude 4.5 Models - FULL PARAMETER SUPPORT
# =============================================================================

ANTHROPIC_MODELS = [
    ModelConfig(
        model_id="claude-haiku-4-5-20251001",
        provider=ProviderName.ANTHROPIC,
        display_name="Claude Haiku 4.5",
        api_version="2023-06-01",
        structured_output_method=StructuredOutputMethod.TOOL_USE,
        # Claude supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
        # Claude supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
# Per-Model Validators
# =============================================================================


def validate_model_capability__claude_haiku_4_5_20251001(capability: str) -> bool:
    """Validator for Claude Haiku 4.5."""
    return capability in [
        "tool_use",
        "vision",
        "function_calling",
        "json_mode",
        "extended_thinking",
    ]


def validate_model_capability__claude_sonnet_4_5_20250929(capability: str) -> bool:
    """Validator for Claude Sonnet 4.5."""
    return capability in [
        "tool_use",
        "vision",
        "function_calling",
        "json_mode",
        "extended_thinking",
    ]


# Validator registry mapping model_id to validator function
MODEL_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "claude-haiku-4-5-20251001": validate_model_capability__claude_haiku_4_5_20251001,
    "claude-sonnet-4-5-20250929": validate_model_capability__claude_sonnet_4_5_20250929,
}
