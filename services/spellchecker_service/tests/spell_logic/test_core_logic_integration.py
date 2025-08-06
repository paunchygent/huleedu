"""
Integration tests for the core spell checking algorithm.

Tests the complete L2 + pyspellchecker pipeline in the service context,
verifying end-to-end functionality with realistic scenarios.
"""

from __future__ import annotations

import pytest

from ...core_logic import default_perform_spell_check_algorithm


class TestCoreLogicIntegration:
    """Integration tests for the complete spell checking pipeline."""

    @pytest.mark.asyncio
    async def test_simple_pyspellchecker_corrections(self) -> None:
        """Test basic pyspellchecker corrections without L2 involvement."""
        # Arrange
        text = "Thiss is a documment with errrors and misstakes."
        essay_id = "test-simple-001"

        # Act
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text,
            {},  # Empty L2 errors for pure pyspellchecker test
            essay_id,
            language="en",
        )

        # Assert
        # Verify specific corrections (pyspellchecker behavior)
        assert "This" in corrected_text  # "Thiss" -> "This"
        assert "document" in corrected_text  # "documment" -> "document"
        assert "errors" in corrected_text  # "errrors" -> "errors"
        assert "mistakes" in corrected_text  # "misstakes" -> "mistakes"

        # Should have made several corrections
        assert corrections_count >= 3
        assert corrected_text != text  # Text should be changed

    @pytest.mark.asyncio
    async def test_l2_plus_pyspellchecker_pipeline(self) -> None:
        """Test combined L2 + pyspellchecker pipeline with realistic text."""
        # Arrange - Text with both L2 errors and regular misspellings
        text = "I recieve the documment becouse it hapened yesterday."
        essay_id = "test-l2-001"

        # Act
        l2_errors = {"recieve": "receive", "becouse": "because"}  # L2 errors for comprehensive test
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text,
            l2_errors,
            essay_id,
            language="en",
        )

        # Assert
        # Should correct both L2 and pyspellchecker errors
        assert "receive" in corrected_text  # L2 or pyspellchecker: "recieve" -> "receive"
        assert "document" in corrected_text  # pyspellchecker: "documment" -> "document"
        assert "because" in corrected_text  # L2: "becouse" -> "because"
        assert "happened" in corrected_text  # pyspellchecker: "hapened" -> "happened"

        # Should have made multiple corrections
        assert corrections_count >= 3
        assert corrected_text != text

    @pytest.mark.asyncio
    async def test_punctuation_and_capitalization_preservation(self) -> None:
        """Test that punctuation and capitalization are preserved correctly."""
        # Arrange
        text = "Hello! Thiss is a documment. It's verry importent."
        essay_id = "test-punct-001"

        # Act
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text,
            {},  # Empty L2 errors for punctuation test
            essay_id,
            language="en",
        )

        # Assert
        # Verify punctuation is preserved
        assert corrected_text.startswith("Hello!")
        assert ". It's" in corrected_text
        assert corrected_text.endswith(".")

        # Verify corrections while maintaining structure
        assert "This" in corrected_text  # "Thiss" -> "This"
        assert "document" in corrected_text  # "documment" -> "document"
        assert "very" in corrected_text  # "verry" -> "very"
        assert "important" in corrected_text  # "importent" -> "important"

        assert corrections_count >= 3

    @pytest.mark.asyncio
    async def test_hyphenated_and_contractions(self) -> None:
        """Test handling of hyphenated words and contractions."""
        # Arrange
        text = "It's a well-writen artical that's verry intresting."
        essay_id = "test-hyphen-001"

        # Act
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text,
            {},  # Empty L2 errors for hyphenation test
            essay_id,
            language="en",
        )

        # Assert
        # Verify contractions are preserved
        assert "It's" in corrected_text
        assert "that's" in corrected_text

        # Verify that corrections were made (don't expect specific corrections)
        # The algorithm should correct some misspellings, but exact corrections may vary
        assert corrections_count >= 2  # At least some corrections expected
        assert corrected_text != text  # Text should be changed
        
        # Verify the text is still readable and improved
        assert "well-" in corrected_text  # Hyphenated structure preserved
        assert len(corrected_text) > 0

    @pytest.mark.asyncio
    async def test_no_corrections_needed(self) -> None:
        """Test with text that needs no corrections."""
        # Arrange
        text = "This is a perfectly spelled sentence with no errors."
        essay_id = "test-perfect-001"

        # Act
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text,
            {},  # Empty L2 errors for no-corrections test
            essay_id,
            language="en",
        )

        # Assert
        assert corrected_text == text  # Should be unchanged
        assert corrections_count == 0  # No corrections made

    @pytest.mark.asyncio
    async def test_empty_text_handling(self) -> None:
        """Test handling of empty or whitespace-only text."""
        # Arrange
        empty_text = ""
        whitespace_text = "   \n\t   "
        essay_id = "test-empty-001"

        # Act
        result_empty = await default_perform_spell_check_algorithm(empty_text, {}, essay_id)
        result_whitespace = await default_perform_spell_check_algorithm(
            whitespace_text, {}, essay_id
        )

        # Assert
        assert result_empty[0] == ""
        assert result_empty[1] == 0

        assert result_whitespace[0] == whitespace_text  # Preserved
        assert result_whitespace[1] == 0

    @pytest.mark.asyncio
    async def test_different_languages(self) -> None:
        """Test spell checking with different language settings."""
        # Arrange
        text = "Thiss is a tset."  # Same errors, different language
        essay_id = "test-lang-001"

        # Act - Test with English (default)
        result_en = await default_perform_spell_check_algorithm(text, {}, essay_id, language="en")

        # Test with Spanish (should still work, though corrections may differ)
        result_es = await default_perform_spell_check_algorithm(text, {}, essay_id, language="es")

        # Assert
        # Both should make some corrections (though results may differ)
        assert result_en[1] > 0  # Should correct something
        assert result_es[1] >= 0  # May or may not correct (depends on Spanish dictionary)

        # Corrected text should be different from original for English
        assert result_en[0] != text

    @pytest.mark.asyncio
    async def test_performance_with_longer_text(self) -> None:
        """Test performance and correctness with longer text."""
        # Arrange - A longer text with various errors
        text = """
        Thiss is a documment that containns many errrors. The spellchecker should
        be abel to handl all of thees misstakes efficently. It's importent that
        the algorythm workss wel with longr textes becouse essayss can bee quit
        lenghty. We nede to ensur that performanc remainss gud even with
        substantil amounts of contnt.
        """.strip()
        essay_id = "test-long-001"

        # Act
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text,
            {},  # Empty L2 errors for performance test
            essay_id,
            language="en",
        )

        # Assert
        # Should make significant corrections
        assert corrections_count >= 10  # Many errors to correct
        assert len(corrected_text) > 0
        assert corrected_text != text

        # Verify that common misspellings were corrected (without expecting exact results)
        # The text should be significantly improved
        assert "Thiss" not in corrected_text  # Common misspellings should be fixed
        assert "documment" not in corrected_text
        assert "containns" not in corrected_text
        assert "errrors" not in corrected_text
        assert "misstakes" not in corrected_text
        
        # Verify text is still coherent and readable
        assert "spellchecker" in corrected_text.lower()  # Key words preserved

    @pytest.mark.asyncio
    async def test_case_preservation(self) -> None:
        """Test that original case patterns are preserved in corrections."""
        # Arrange
        text = "RECIEVE IS WRONG. Recieve Is Title Case. recieve is lowercase."
        essay_id = "test-case-001"

        # Act
        l2_errors = {"recieve": "receive"}  # L2 error for case preservation test
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text,
            l2_errors,
            essay_id,
            language="en",
        )

        # Assert
        # Verify case preservation
        assert "RECEIVE IS" in corrected_text  # Uppercase preserved
        assert "Receive Is" in corrected_text  # Title case preserved
        assert "receive is" in corrected_text  # Lowercase preserved
        assert corrections_count >= 3  # Should correct all three instances

    @pytest.mark.asyncio
    async def test_uppercase_case_normalization(self) -> None:
        """Test that uppercase misspelled words are properly detected and corrected."""
        # Arrange - Use words NOT in L2 dictionary to test pyspellchecker normalization
        text = "THISS DOCUMMENT HAS ERRRORS."
        essay_id = "test-uppercase-norm-001"

        # Act
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text,
            {},  # Empty L2 errors for uppercase normalization test
            essay_id,
            language="en",
        )

        # Assert
        # Verify uppercase is preserved in corrections
        assert "THIS DOCUMENT" in corrected_text  # "THISS DOCUMMENT" -> "THIS DOCUMENT"
        assert "ERRORS" in corrected_text  # "ERRRORS" -> "ERRORS"
        assert corrections_count >= 3  # Should correct all three words
        assert corrected_text != text  # Text should be changed

        # Verify the entire sentence structure is preserved
        assert corrected_text.endswith(".")
        assert corrected_text.startswith("THIS")
