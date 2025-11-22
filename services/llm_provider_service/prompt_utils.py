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


def render_prompt_blocks(prompt_blocks: list[dict[str, str]]) -> str:
    """Render prompt blocks into a monolithic text string."""

    return "\n\n".join(block.get("content", "") for block in prompt_blocks)


def compute_prompt_sha256(
    *,
    provider: LLMProviderType,
    user_prompt: str,
    prompt_blocks: list[dict[str, str]] | None = None,
) -> str:
    """Hash the fully formatted prompt for deterministic tracking."""

    prompt_text = render_prompt_blocks(prompt_blocks) if prompt_blocks else user_prompt
    full_prompt = format_comparison_prompt(provider=provider, user_prompt=prompt_text)
    return sha256(full_prompt.encode("utf-8")).hexdigest()
