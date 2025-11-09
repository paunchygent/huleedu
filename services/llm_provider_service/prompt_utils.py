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
    essay_a: str,
    essay_b: str,
) -> str:
    """Return the exact prompt string sent to concrete LLM providers.

    Providers share the same placeholder replacement logic, but a subset appends
    an explicit JSON instruction to encourage structured responses. Centralizing
    the formatter keeps queue-processor fallbacks consistent with provider
    implementations.
    """

    formatted = user_prompt.replace("{essay_a}", essay_a).replace("{essay_b}", essay_b)
    if "{essay_a}" not in user_prompt and "{essay_b}" not in user_prompt:
        formatted = f"{user_prompt}\n\nEssay A:\n{essay_a}\n\nEssay B:\n{essay_b}"

    if provider in _JSON_INSTRUCTION_PROVIDERS:
        formatted += "\n\nPlease respond with a valid JSON object."

    return formatted


def compute_prompt_sha256(
    *,
    provider: LLMProviderType,
    user_prompt: str,
    essay_a: str,
    essay_b: str,
) -> str:
    """Hash the fully formatted prompt for deterministic tracking."""

    full_prompt = format_comparison_prompt(
        provider=provider,
        user_prompt=user_prompt,
        essay_a=essay_a,
        essay_b=essay_b,
    )
    return sha256(full_prompt.encode("utf-8")).hexdigest()
