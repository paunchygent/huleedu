"""Tests for model family extraction utilities.

These tests verify that family extraction logic correctly handles various
naming patterns from different LLM providers. Each provider has unique
conventions for model identifiers, and family extraction must handle:

- Standard naming patterns
- Special cases (decimal versions, prefixes, etc.)
- Edge cases (short names, unusual formats)
- Provider-specific conventions

Test Coverage:
- OpenAI family extraction (GPT variants, non-GPT models)
- Anthropic family extraction (Claude tier-based naming)
- Google family extraction (Gemini version-tier naming)
- OpenRouter family extraction (provider-prefixed IDs)
"""

from __future__ import annotations

import pytest

from services.llm_provider_service.model_checker.family_utils import (
    extract_anthropic_family,
    extract_google_family,
    extract_openai_family,
    extract_openrouter_family,
)


class TestOpenAIFamilyExtraction:
    """Tests for OpenAI model family extraction logic."""

    @pytest.mark.parametrize(
        "model_id, expected_family",
        [
            # GPT-5 family (standard naming)
            ("gpt-5-2025-08-07", "gpt-5"),
            ("gpt-5-mini-2025-08-07", "gpt-5"),
            ("gpt-5-nano-2025-08-07", "gpt-5"),
            # GPT-4.1 family (decimal version)
            ("gpt-4.1-2025-04-14", "gpt-4.1"),
            ("gpt-4.1-mini-2025-04-14", "gpt-4.1"),
            ("gpt-4.1-nano-2025-04-14", "gpt-4.1"),
            # GPT-4o family (variant suffix)
            ("gpt-4o-2024-11-20", "gpt-4o"),
            ("gpt-4o-mini-2024-07-18", "gpt-4o"),
            # Non-GPT models
            ("dall-e-3", "dall-e"),
            ("dall-e-2", "dall-e"),
            ("whisper-1", "whisper"),
            # Reasoning models
            ("o1-mini", "o1"),
            ("o1-preview", "o1"),
            ("o3-mini-2025-01-31", "o3"),
            # Sora models
            ("sora-1", "sora"),
            ("sora-2", "sora"),
            # Edge cases
            ("gpt", "gpt"),  # Single part
            ("", ""),  # Empty string
        ],
    )
    def test_extract_openai_family_patterns(
        self, model_id: str, expected_family: str
    ) -> None:
        """OpenAI family extraction handles various naming patterns correctly.

        Tests verify that the extraction logic correctly handles:
        - Standard GPT models with version numbers
        - Decimal versions (e.g., gpt-4.1)
        - Variant suffixes (e.g., mini, nano, turbo)
        - Non-GPT families (DALL-E, Whisper, O-series, Sora)
        - Edge cases (empty strings, single-part names)

        Args:
            model_id: Model identifier from OpenAI API
            expected_family: Expected family identifier
        """
        family = extract_openai_family(model_id)
        assert family == expected_family, (
            f"Expected family '{expected_family}' for model '{model_id}', "
            f"got '{family}'"
        )

    def test_extract_openai_family_preserves_decimal_versions(self) -> None:
        """Decimal version numbers are preserved in family names.

        GPT-4.1 models must extract as 'gpt-4.1' not 'gpt-4' to distinguish
        from the GPT-4 family. This ensures proper family-based filtering.
        """
        model_id = "gpt-4.1-mini-2025-04-14"
        family = extract_openai_family(model_id)
        assert family == "gpt-4.1"
        assert "." in family, "Decimal version should be preserved"

    def test_extract_openai_family_handles_variants(self) -> None:
        """Variant suffixes (mini, nano) are stripped to extract family.

        All variants within a family (e.g., gpt-5, gpt-5-mini, gpt-5-nano)
        should extract to the same family identifier for proper grouping.
        """
        variants = [
            "gpt-5-2025-08-07",
            "gpt-5-mini-2025-08-07",
            "gpt-5-nano-2025-08-07",
            "gpt-5-turbo-2025-08-07",
        ]
        families = [extract_openai_family(v) for v in variants]
        assert all(f == "gpt-5" for f in families), (
            "All variants should extract to same family"
        )

    def test_extract_openai_family_non_gpt_models(self) -> None:
        """Non-GPT models extract base family correctly.

        Models like DALL-E, Whisper, and O-series use simpler naming
        and should extract just the base name as the family.
        """
        assert extract_openai_family("dall-e-3") == "dall-e"
        assert extract_openai_family("whisper-1") == "whisper"
        assert extract_openai_family("o1-mini") == "o1"
        assert extract_openai_family("o3-mini-2025-01-31") == "o3"


class TestAnthropicFamilyExtraction:
    """Tests for Anthropic model family extraction logic."""

    @pytest.mark.parametrize(
        "model_id, expected_family",
        [
            # Current generation (Claude 4.x)
            ("claude-haiku-4-5-20251001", "claude-haiku"),
            ("claude-sonnet-4-5-20250929", "claude-sonnet"),
            ("claude-opus-4-20250514", "claude-opus"),
            # Legacy generation (Claude 3.x)
            ("claude-3-haiku-20240307", "claude-3"),
            ("claude-3-sonnet-20240229", "claude-3"),
            ("claude-3-opus-20240229", "claude-3"),
            # Edge cases
            ("claude", "claude"),  # Single part
            ("", ""),  # Empty string
        ],
    )
    def test_extract_anthropic_family_patterns(
        self, model_id: str, expected_family: str
    ) -> None:
        """Anthropic family extraction handles tier-based naming correctly.

        Anthropic uses a consistent pattern: claude-{tier}-{version}-{date}
        The family is extracted as 'claude-{tier}' for current generation,
        or 'claude-{version}' for legacy models (e.g., claude-3).

        Args:
            model_id: Model identifier from Anthropic API
            expected_family: Expected family identifier
        """
        family = extract_anthropic_family(model_id)
        assert family == expected_family, (
            f"Expected family '{expected_family}' for model '{model_id}', "
            f"got '{family}'"
        )

    def test_extract_anthropic_family_tier_grouping(self) -> None:
        """Models with same tier but different versions group together.

        All haiku variants (regardless of version number) should extract
        to the 'claude-haiku' family for proper tracking.
        """
        haiku_models = [
            "claude-haiku-4-5-20251001",
            "claude-haiku-3-5-20240307",
            "claude-haiku-5-0-20260101",  # Hypothetical future version
        ]
        families = [extract_anthropic_family(m) for m in haiku_models]
        assert all(f == "claude-haiku" for f in families), (
            "All haiku variants should extract to same family"
        )

    def test_extract_anthropic_family_distinguishes_tiers(self) -> None:
        """Different tiers extract to different families.

        Haiku, Sonnet, and Opus are distinct families even if they share
        the same version number.
        """
        tier_models = [
            ("claude-haiku-4-5-20251001", "claude-haiku"),
            ("claude-sonnet-4-5-20250929", "claude-sonnet"),
            ("claude-opus-4-5-20250514", "claude-opus"),
        ]
        for model_id, expected_family in tier_models:
            family = extract_anthropic_family(model_id)
            assert family == expected_family


class TestGoogleFamilyExtraction:
    """Tests for Google model family extraction logic."""

    @pytest.mark.parametrize(
        "model_id, expected_family",
        [
            # Gemini 2.5 family
            ("gemini-2.5-flash-preview-05-20", "gemini-2.5-flash"),
            ("gemini-2.5-flash-001", "gemini-2.5-flash"),
            ("gemini-2.5-pro-preview", "gemini-2.5-pro"),
            # Gemini 2.0 family
            ("gemini-2.0-flash", "gemini-2.0-flash"),
            ("gemini-2.0-pro", "gemini-2.0-pro"),
            # Gemini 1.5 family (legacy)
            ("gemini-1.5-flash", "gemini-1.5-flash"),
            ("gemini-1.5-pro", "gemini-1.5-pro"),
            # Edge cases
            ("gemini-flash", "gemini-flash"),  # Only 2 parts
            ("gemini", "gemini"),  # Single part
            ("", ""),  # Empty string
        ],
    )
    def test_extract_google_family_patterns(
        self, model_id: str, expected_family: str
    ) -> None:
        """Google family extraction handles version-tier naming correctly.

        Google uses pattern: gemini-{version}-{tier}-{variant?}
        The family is extracted as 'gemini-{version}-{tier}'.

        Args:
            model_id: Model identifier from Google API
            expected_family: Expected family identifier
        """
        family = extract_google_family(model_id)
        assert family == expected_family, (
            f"Expected family '{expected_family}' for model '{model_id}', "
            f"got '{family}'"
        )

    def test_extract_google_family_version_tier_grouping(self) -> None:
        """Models with same version and tier group together.

        All gemini-2.5-flash variants (with different suffixes) should
        extract to the same family.
        """
        flash_models = [
            "gemini-2.5-flash-preview-05-20",
            "gemini-2.5-flash-001",
            "gemini-2.5-flash-002",
        ]
        families = [extract_google_family(m) for m in flash_models]
        assert all(f == "gemini-2.5-flash" for f in families), (
            "All flash variants should extract to same family"
        )

    def test_extract_google_family_distinguishes_versions_and_tiers(self) -> None:
        """Different versions or tiers extract to different families.

        2.5-flash vs 2.0-flash are different families, as are
        2.5-flash vs 2.5-pro.
        """
        distinct_models = [
            ("gemini-2.5-flash-preview-05-20", "gemini-2.5-flash"),
            ("gemini-2.0-flash", "gemini-2.0-flash"),
            ("gemini-2.5-pro-preview", "gemini-2.5-pro"),
        ]
        families = [extract_google_family(m) for m, _ in distinct_models]
        assert len(set(families)) == 3, "All models should be in different families"


class TestOpenRouterFamilyExtraction:
    """Tests for OpenRouter model family extraction logic."""

    @pytest.mark.parametrize(
        "model_id, expected_family",
        [
            # Anthropic models via OpenRouter
            (
                "anthropic/claude-haiku-4-5-20251001",
                "claude-haiku-openrouter",
            ),
            (
                "anthropic/claude-sonnet-4-5-20250929",
                "claude-sonnet-openrouter",
            ),
            # OpenAI models via OpenRouter
            ("openai/gpt-5-mini", "gpt-5-openrouter"),
            ("openai/gpt-4o-2024-11-20", "gpt-4o-openrouter"),
            ("openai/gpt-4.1-mini-2025-04-14", "gpt-4.1-openrouter"),
            # Non-prefixed models (fallback)
            ("some-model", "some-model"),
            ("", ""),
        ],
    )
    def test_extract_openrouter_family_patterns(
        self, model_id: str, expected_family: str
    ) -> None:
        """OpenRouter family extraction handles provider-prefixed IDs correctly.

        OpenRouter uses {provider}/{model-id} format. Family extraction:
        1. Splits on '/' to get provider and base model ID
        2. Uses provider-specific extraction for base ID
        3. Appends '-openrouter' suffix to distinguish from direct API access

        Args:
            model_id: Model identifier from OpenRouter API
            expected_family: Expected family identifier
        """
        family = extract_openrouter_family(model_id)
        assert family == expected_family, (
            f"Expected family '{expected_family}' for model '{model_id}', "
            f"got '{family}'"
        )

    def test_extract_openrouter_family_appends_suffix(self) -> None:
        """OpenRouter families include '-openrouter' suffix.

        This distinguishes OpenRouter-accessed models from direct API access,
        allowing separate tracking of the same underlying model families.
        """
        model_id = "anthropic/claude-haiku-4-5-20251001"
        family = extract_openrouter_family(model_id)
        assert family.endswith("-openrouter"), (
            "OpenRouter families should have -openrouter suffix"
        )

    def test_extract_openrouter_family_uses_provider_specific_logic(self) -> None:
        """Base model family extraction uses provider-specific rules.

        For anthropic/claude-haiku-X, extract 'claude-haiku' from base,
        then append '-openrouter'. For openai/gpt-5-X, extract 'gpt-5'
        from base, then append '-openrouter'.
        """
        # Anthropic model should use anthropic extraction logic
        anthropic_model = "anthropic/claude-haiku-4-5-20251001"
        anthropic_family = extract_openrouter_family(anthropic_model)
        assert anthropic_family == "claude-haiku-openrouter"

        # OpenAI model should use openai extraction logic
        openai_model = "openai/gpt-5-mini-2025-08-07"
        openai_family = extract_openrouter_family(openai_model)
        assert openai_family == "gpt-5-openrouter"

    def test_extract_openrouter_family_handles_non_prefixed_models(self) -> None:
        """Non-prefixed model IDs are returned as-is (fallback behavior).

        If OpenRouter adds models without provider prefix, extraction
        should handle gracefully by returning the full model ID.
        """
        model_id = "some-custom-model"
        family = extract_openrouter_family(model_id)
        assert family == model_id, "Non-prefixed models should return as-is"


class TestFamilyExtractionEdgeCases:
    """Tests for edge cases and boundary conditions across all extractors."""

    def test_empty_string_handling(self) -> None:
        """Empty strings are handled gracefully across all extractors."""
        assert extract_openai_family("") == ""
        assert extract_anthropic_family("") == ""
        assert extract_google_family("") == ""
        assert extract_openrouter_family("") == ""

    def test_single_word_model_ids(self) -> None:
        """Single-word model IDs extract as themselves (fallback behavior)."""
        assert extract_openai_family("gpt") == "gpt"
        assert extract_anthropic_family("claude") == "claude"
        assert extract_google_family("gemini") == "gemini"

    def test_extraction_is_deterministic(self) -> None:
        """Family extraction produces consistent results for same input.

        Multiple calls with identical input must return identical output
        to ensure reliable family-based filtering.
        """
        model_id = "gpt-5-mini-2025-08-07"
        results = [extract_openai_family(model_id) for _ in range(5)]
        assert len(set(results)) == 1, "Extraction should be deterministic"
        assert results[0] == "gpt-5"

    def test_extraction_handles_unusual_separators(self) -> None:
        """Extraction handles model IDs with unusual separator patterns.

        Some providers might use inconsistent separator patterns.
        Extraction should handle gracefully.
        """
        # Multiple consecutive dashes
        assert extract_openai_family("gpt--5--mini") == "gpt-"

        # Trailing dashes (edge case)
        assert extract_openai_family("gpt-5-") == "gpt-5"
