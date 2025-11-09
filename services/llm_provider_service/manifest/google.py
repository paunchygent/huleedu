"""Google (Gemini) model definitions and validators.

This module contains all Google Gemini model configurations.

All Gemini models support standard sampling parameters (temperature, top_p, etc.).
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
# Gemini 2.5 Models - FULL PARAMETER SUPPORT
# =============================================================================

GOOGLE_MODELS = [
    ModelConfig(
        model_id="gemini-2.5-flash-preview-05-20",
        provider=ProviderName.GOOGLE,
        display_name="Gemini 2.5 Flash (Preview)",
        model_family="gemini-2.5-flash",
        api_version="v1",
        structured_output_method=StructuredOutputMethod.JSON_MIME_TYPE,
        # Gemini supports all sampling parameters
        supports_temperature=True,
        supports_top_p=True,
        supports_frequency_penalty=True,
        supports_presence_penalty=True,
        uses_max_completion_tokens=False,
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
# Per-Model Validators
# =============================================================================


def validate_model_capability__gemini_2_5_flash_preview_05_20(capability: str) -> bool:
    """Validator for Gemini 2.5 Flash preview model."""
    return capability in ["function_calling", "json_mode", "multimodal"]


# Validator registry mapping model_id to validator function
MODEL_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "gemini-2.5-flash-preview-05-20": validate_model_capability__gemini_2_5_flash_preview_05_20,
}
