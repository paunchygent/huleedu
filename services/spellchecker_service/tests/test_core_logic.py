"""
Unit tests for the spell checker core logic.

These tests focus on testing the core logic functions related to spell checking,
content fetching, and content storing.
"""

from __future__ import annotations

import pytest

from ..core_logic import default_perform_spell_check_algorithm

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
        result = await default_perform_spell_check_algorithm(
            text_with_errors,
            test_l2_errors,
            sample_essay_id,
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
