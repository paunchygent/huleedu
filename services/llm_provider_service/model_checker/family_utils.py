"""Centralized model family extraction utilities.

Each provider uses different naming conventions for model IDs. These utilities
extract the "family" portion consistently across the codebase.

Examples:
    OpenAI: gpt-5-mini-2025-08-07 → gpt-5
    Anthropic: claude-haiku-4-5-20251001 → claude-haiku
    Google: gemini-2.5-flash-preview-05-20 → gemini-2.5-flash
    OpenRouter: anthropic/claude-haiku-4-5-20251001 → claude-haiku-openrouter

Architecture:
    - Provider-specific extraction functions encapsulate naming conventions
    - Centralized logic prevents code duplication across 4 checkers
    - Single source of truth for family extraction patterns
    - Easier to test and maintain

Usage:
    from services.llm_provider_service.model_checker.family_utils import (
        extract_openai_family,
        extract_anthropic_family,
    )

    family = extract_openai_family("gpt-5-mini-2025-08-07")  # Returns "gpt-5"
"""

from __future__ import annotations


def extract_openai_family(model_id: str) -> str:
    """Extract model family from OpenAI model_id.

    Handles various OpenAI naming patterns:
    - GPT decimal versions: gpt-4.1-mini-2025-04-14 → gpt-4.1
    - GPT standard: gpt-5-mini-2025-08-07 → gpt-5
    - Other families: dall-e-3 → dall-e, whisper-1 → whisper

    Args:
        model_id: Full model identifier from OpenAI API

    Returns:
        Family identifier (e.g., "gpt-5", "gpt-4.1", "dall-e")

    Examples:
        >>> extract_openai_family("gpt-5-mini-2025-08-07")
        'gpt-5'
        >>> extract_openai_family("gpt-4.1-2025-04-14")
        'gpt-4.1'
        >>> extract_openai_family("dall-e-3")
        'dall-e'
    """
    parts = model_id.split("-")

    # Special case: gpt-4.1 (decimal version)
    if len(parts) >= 2 and parts[0] == "gpt" and "." in parts[1]:
        return f"{parts[0]}-{parts[1]}"  # e.g., "gpt-4.1"

    # Standard GPT case: gpt-5, gpt-4o
    if len(parts) >= 2 and parts[0] == "gpt":
        return f"{parts[0]}-{parts[1]}"  # e.g., "gpt-5", "gpt-4o"

    # Other families (dall-e, whisper, o1, o3, etc.)
    return parts[0] if parts else model_id


def extract_anthropic_family(model_id: str) -> str:
    """Extract model family from Anthropic model_id.

    Handles Anthropic tier-based naming:
    - claude-haiku-4-5-20251001 → claude-haiku
    - claude-sonnet-4-5-20250929 → claude-sonnet

    Args:
        model_id: Full model identifier from Anthropic API

    Returns:
        Family identifier (e.g., "claude-haiku", "claude-sonnet")

    Examples:
        >>> extract_anthropic_family("claude-haiku-4-5-20251001")
        'claude-haiku'
        >>> extract_anthropic_family("claude-sonnet-4-5-20250929")
        'claude-sonnet'
    """
    parts = model_id.split("-")

    # Pattern: claude-{tier}-{version}-{date}
    if len(parts) >= 2 and parts[0] == "claude":
        return f"{parts[0]}-{parts[1]}"  # e.g., "claude-haiku"

    # Fallback
    return parts[0] if parts else model_id


def extract_google_family(model_id: str) -> str:
    """Extract model family from Google model_id.

    Handles Gemini version-tier naming:
    - gemini-2.5-flash-preview-05-20 → gemini-2.5-flash
    - gemini-2.0-pro → gemini-2.0-pro

    Args:
        model_id: Full model identifier from Google API

    Returns:
        Family identifier (e.g., "gemini-2.5-flash")

    Examples:
        >>> extract_google_family("gemini-2.5-flash-preview-05-20")
        'gemini-2.5-flash'
        >>> extract_google_family("gemini-2.0-pro")
        'gemini-2.0-pro'
    """
    parts = model_id.split("-")

    # Pattern: gemini-{version}-{tier}-{variant}
    if len(parts) >= 3 and parts[0] == "gemini":
        return f"{parts[0]}-{parts[1]}-{parts[2]}"  # e.g., "gemini-2.5-flash"

    # Fallback: use full model_id
    return model_id


def extract_openrouter_family(model_id: str) -> str:
    """Extract model family from OpenRouter model_id.

    OpenRouter uses provider-prefixed IDs: {provider}/{model-id}.
    We extract the underlying family and append "-openrouter" suffix.

    Examples:
    - anthropic/claude-haiku-4-5-20251001 → claude-haiku-openrouter
    - openai/gpt-5-mini → gpt-5-openrouter

    Args:
        model_id: Full model identifier from OpenRouter API

    Returns:
        Family identifier with -openrouter suffix

    Examples:
        >>> extract_openrouter_family("anthropic/claude-haiku-4-5-20251001")
        'claude-haiku-openrouter'
        >>> extract_openrouter_family("openai/gpt-5-mini")
        'gpt-5-openrouter'
    """
    if "/" not in model_id:
        return model_id

    provider, base_id = model_id.split("/", 1)

    # Extract family using provider-specific logic
    if provider == "anthropic":
        base_family = extract_anthropic_family(base_id)
        # Only append suffix if we successfully extracted a family
        if base_family and not base_family.endswith("-openrouter"):
            return f"{base_family}-openrouter"

    elif provider == "openai":
        base_family = extract_openai_family(base_id)
        if base_family and not base_family.endswith("-openrouter"):
            return f"{base_family}-openrouter"

    # Fallback: use full model_id
    return model_id
