"""OpenAI model definitions and validators.

This module contains all OpenAI model configurations with parameter compatibility flags.

Model Families:
- GPT-5: Does NOT support temperature, top_p, frequency_penalty, presence_penalty
- GPT-4.1: Full parameter support, 1M context window
- GPT-4o: Full parameter support, multimodal/vision capabilities
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
# GPT-5 Family - NO SAMPLING PARAMETER SUPPORT
# =============================================================================

OPENAI_MODELS = [
    ModelConfig(
        model_id="gpt-5-2025-08-07",
        provider=ProviderName.OPENAI,
        display_name="GPT-5",
        model_family="gpt-5",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        # GPT-5 does NOT support sampling parameters
        supports_temperature=False,
        supports_top_p=False,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
        uses_max_completion_tokens=True,
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
        "strong reasoning and analysis capabilities. "
        "Does NOT support temperature/top_p/frequency_penalty/presence_penalty parameters.",
    ),
    ModelConfig(
        model_id="gpt-5-mini-2025-08-07",
        provider=ProviderName.OPENAI,
        display_name="GPT-5 Mini",
        model_family="gpt-5",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        # GPT-5 does NOT support sampling parameters
        supports_temperature=False,
        supports_top_p=False,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
        uses_max_completion_tokens=True,
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
        "272K context window. "
        "Does NOT support temperature/top_p/frequency_penalty/presence_penalty parameters.",
    ),
    ModelConfig(
        model_id="gpt-5-nano-2025-08-07",
        provider=ProviderName.OPENAI,
        display_name="GPT-5 Nano",
        model_family="gpt-5",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        # GPT-5 does NOT support sampling parameters
        supports_temperature=False,
        supports_top_p=False,
        supports_frequency_penalty=False,
        supports_presence_penalty=False,
        uses_max_completion_tokens=True,
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
        "cost-sensitive workloads. 272K context window. "
        "Does NOT support temperature/top_p/frequency_penalty/presence_penalty parameters.",
    ),
    # =============================================================================
    # GPT-4.1 Family - FULL PARAMETER SUPPORT
    # =============================================================================
    ModelConfig(
        model_id="gpt-4.1-2025-04-14",  # FIXED: Added missing model_id
        provider=ProviderName.OPENAI,
        display_name="GPT-4.1",
        model_family="gpt-4.1",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        # GPT-4.1 supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
        notes="GPT-4.1 with 1M context window. 26% less expensive than GPT-4o for median queries.",
    ),
    ModelConfig(
        model_id="gpt-4.1-mini-2025-04-14",
        provider=ProviderName.OPENAI,
        display_name="GPT-4.1 Mini",
        model_family="gpt-4.1",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        # GPT-4.1 supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
        model_family="gpt-4.1",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        # GPT-4.1 supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
    # =============================================================================
    # GPT-4o Family - FULL PARAMETER SUPPORT + VISION
    # =============================================================================
    ModelConfig(
        model_id="gpt-4o-2024-11-20",
        provider=ProviderName.OPENAI,
        display_name="GPT-4o",
        model_family="gpt-4o",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        # GPT-4o supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
        model_family="gpt-4o",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_SCHEMA,
        # GPT-4o supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
# Per-Model Validators
# =============================================================================


def validate_model_capability__gpt_5_2025_08_07(capability: str) -> bool:
    """Validator for GPT-5 flagship model."""
    return capability in ["function_calling", "json_mode", "response_format_schema"]


def validate_model_capability__gpt_5_mini_2025_08_07(capability: str) -> bool:
    """Validator for GPT-5 Mini model."""
    return capability in ["function_calling", "json_mode", "response_format_schema"]


def validate_model_capability__gpt_5_nano_2025_08_07(capability: str) -> bool:
    """Validator for GPT-5 Nano model."""
    return capability in ["function_calling", "json_mode", "response_format_schema"]


def validate_model_capability__gpt_4_1_2025_04_14(capability: str) -> bool:
    """Validator for GPT-4.1 flagship model."""
    return capability in ["function_calling", "json_mode", "response_format_schema"]


def validate_model_capability__gpt_4_1_mini_2025_04_14(capability: str) -> bool:
    """Validator for GPT-4.1 Mini model."""
    return capability in ["function_calling", "json_mode", "response_format_schema"]


def validate_model_capability__gpt_4_1_nano_2025_04_14(capability: str) -> bool:
    """Validator for GPT-4.1 Nano model."""
    return capability in ["function_calling", "json_mode", "response_format_schema"]


def validate_model_capability__gpt_4o_2024_11_20(capability: str) -> bool:
    """Validator for GPT-4o multimodal model."""
    return capability in [
        "function_calling",
        "json_mode",
        "response_format_schema",
        "vision",
    ]


def validate_model_capability__gpt_4o_mini_2024_07_18(capability: str) -> bool:
    """Validator for GPT-4o Mini multimodal model."""
    return capability in [
        "function_calling",
        "json_mode",
        "response_format_schema",
        "vision",
    ]


# Validator registry mapping model_id to validator function
MODEL_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "gpt-5-2025-08-07": validate_model_capability__gpt_5_2025_08_07,
    "gpt-5-mini-2025-08-07": validate_model_capability__gpt_5_mini_2025_08_07,
    "gpt-5-nano-2025-08-07": validate_model_capability__gpt_5_nano_2025_08_07,
    "gpt-4.1-2025-04-14": validate_model_capability__gpt_4_1_2025_04_14,
    "gpt-4.1-mini-2025-04-14": validate_model_capability__gpt_4_1_mini_2025_04_14,
    "gpt-4.1-nano-2025-04-14": validate_model_capability__gpt_4_1_nano_2025_04_14,
    "gpt-4o-2024-11-20": validate_model_capability__gpt_4o_2024_11_20,
    "gpt-4o-mini-2024-07-18": validate_model_capability__gpt_4o_mini_2024_07_18,
}
