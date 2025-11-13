"""Shared helpers for formatting LLM comparison prompts and hashes."""

from __future__ import annotations

from hashlib import sha256

from common_core import LLMProviderType

_JSON_INSTRUCTION_PROVIDERS: tuple[LLMProviderType, ...] = (
    LLMProviderType.OPENAI,
    LLMProviderType.OPENROUTER,
)


def format_comparison_prompt(
    *,
    provider: LLMProviderType,
    user_prompt: str,
) -> str:
    """Return the exact prompt string sent to concrete LLM providers.

    Essays are now embedded directly in user_prompt. This function only adds
    provider-specific formatting (e.g., JSON instructions for certain providers).
    """

    formatted = user_prompt

    if provider in _JSON_INSTRUCTION_PROVIDERS:
        formatted += "\n\nPlease respond with a valid JSON object."

    return formatted


def compute_prompt_sha256(
    *,
    provider: LLMProviderType,
    user_prompt: str,
) -> str:
    """Hash the fully formatted prompt for deterministic tracking."""

    full_prompt = format_comparison_prompt(
        provider=provider,
        user_prompt=user_prompt,
    )
    return sha256(full_prompt.encode("utf-8")).hexdigest()
