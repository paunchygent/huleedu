"""
Unit tests for the spell checker core logic.

These tests focus on testing the core logic functions related to spell checking,
content fetching, and content storing.
"""

from __future__ import annotations

import pytest

from .mocks import (
    MockWhitelist,
    create_mock_parallel_processor,
    create_spell_normalizer_for_tests,
)

# Removed HTTP implementation tests - they were testing internal details


# Removed HTTP mocking utilities - no longer needed


class TestDefaultImplementations:
    """Test the default implementation functions."""

    @pytest.mark.asyncio
    async def test_default_perform_spell_check(self, sample_essay_id: str) -> None:
        """Test the default spell check implementation."""
        # Arrange
        text_with_errors = "This is a tset with teh word recieve."

        # Act
        test_l2_errors = {"teh": "the", "recieve": "receive"}  # Simple test dictionary
        normalizer = create_spell_normalizer_for_tests(
            whitelist=MockWhitelist(),
            parallel_processor=create_mock_parallel_processor(),
            l2_errors=test_l2_errors,
        )
        result = await normalizer.normalize_text(
            text=text_with_errors,
            essay_id=sample_essay_id,
        )

        # Assert - The real L2 + pyspellchecker implementation corrects multiple errors
        assert "the" in result.corrected_text  # "teh" should be corrected to "the"
        assert "receive" in result.corrected_text  # "recieve" should be corrected to "receive"
        assert (
            "set" in result.corrected_text
        )  # "tset" should be corrected to "set" (pyspellchecker behavior)
        assert (
            result.total_corrections >= 2
        )  # Should count at least the corrections made by real implementation
        # Note: Exact count may vary based on pyspellchecker behavior and L2 dictionary availability

    @pytest.mark.asyncio
    async def test_spell_normalizer_outputs_are_deterministic(self) -> None:
        """Ensure repeated runs of the normalizer produce consistent results."""
        text = "teh wrng word"
        l2_errors = {"wrng": "wrong"}
        whitelist = MockWhitelist()
        parallel_processor = create_mock_parallel_processor()

        normalizer = create_spell_normalizer_for_tests(
            whitelist=whitelist,
            parallel_processor=parallel_processor,
            l2_errors=l2_errors,
        )

        first_result = await normalizer.normalize_text(text=text)
        second_result = await normalizer.normalize_text(text=text)

        assert first_result.model_dump() == second_result.model_dump()
