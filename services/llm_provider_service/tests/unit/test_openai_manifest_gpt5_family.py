"""Unit tests for GPT-5 family OpenAI manifest entries."""

from __future__ import annotations

import pytest

from services.llm_provider_service.model_manifest import (
    ProviderName,
    get_model_config,
)


@pytest.mark.parametrize(
    "model_id",
    [
        "gpt-5-2025-08-07",
        "gpt-5-mini-2025-08-07",
        "gpt-5-nano-2025-08-07",
        "gpt-5.1",
    ],
)
def test_gpt5_family_flags_and_capabilities(model_id: str) -> None:
    """All GPT-5 family models share reasoning-only parameter semantics."""
    config = get_model_config(ProviderName.OPENAI, model_id)

    assert config.model_family == "gpt-5"
    assert config.supports_temperature is False
    assert config.supports_top_p is False
    assert config.supports_frequency_penalty is False
    assert config.supports_presence_penalty is False
    assert config.uses_max_completion_tokens is True

    assert config.capabilities.get("function_calling") is True
    assert config.capabilities.get("json_mode") is True
    assert config.capabilities.get("response_format_schema") is True
