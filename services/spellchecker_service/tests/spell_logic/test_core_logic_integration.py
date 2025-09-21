"""
Integration tests for the core spell checking algorithm.

Tests the complete L2 + pyspellchecker pipeline in the service context,
verifying end-to-end functionality with realistic scenarios.
"""

from __future__ import annotations

from typing import Any

import pytest
from huleedu_nlp_shared.normalization import SpellNormalizationResult, SpellNormalizer
from huleedu_service_libs.logging_utils import create_service_logger

from ...config import settings
from ...implementations.parallel_processor_impl import DefaultParallelProcessor
from ...tests.mocks import MockWhitelist

_DEFAULT = object()


async def normalize_text(
    *,
    text: str,
    l2_errors: dict[str, str],
    essay_id: str,
    language: str = "en",
    whitelist: object = _DEFAULT,
    **kwargs: Any,
) -> SpellNormalizationResult:
    """Helper to run the shared SpellNormalizer with test-friendly defaults."""

    if whitelist is _DEFAULT:
        whitelist_impl = MockWhitelist()
    else:
        whitelist_impl = whitelist  # type: ignore[assignment]

    normalizer = SpellNormalizer(
        l2_errors=l2_errors,
        whitelist=whitelist_impl,  # type: ignore[arg-type]
        parallel_processor=DefaultParallelProcessor(),
        settings=settings,
        logger_override=create_service_logger("spellchecker_service.tests.core_logic"),
    )

    return await normalizer.normalize_text(
        text=text,
        essay_id=essay_id,
        language=language,
        **kwargs,
    )


class TestCoreLogicIntegration:
    """Integration tests for the complete spell checking pipeline."""

    @pytest.mark.asyncio
    async def test_simple_pyspellchecker_corrections(self) -> None:
        """Test basic pyspellchecker corrections without L2 involvement."""
        # Arrange
        text = "Thiss is a documment with errrors and misstakes."
        essay_id = "test-simple-001"

        # Act
        result = await normalize_text(
            text=text,
            l2_errors={},  # Empty L2 errors for pure pyspellchecker test
            essay_id=essay_id,
            language="en",
        )

        # Assert
        # Verify specific corrections (pyspellchecker behavior)
        assert "This" in result.corrected_text  # "Thiss" -> "This"
        assert "document" in result.corrected_text  # "documment" -> "document"
        assert "errors" in result.corrected_text  # "errrors" -> "errors"
        assert "mistakes" in result.corrected_text  # "misstakes" -> "mistakes"

        # Should have made several corrections
        assert result.total_corrections >= 3
        assert result.corrected_text != text  # Text should be changed

    @pytest.mark.asyncio
    async def test_l2_plus_pyspellchecker_pipeline(self) -> None:
        """Test combined L2 + pyspellchecker pipeline with realistic text."""
        # Arrange - Text with both L2 errors and regular misspellings
        text = "I recieve the documment becouse it hapened yesterday."
        essay_id = "test-l2-001"

        # Act
        l2_errors = {"recieve": "receive", "becouse": "because"}  # L2 errors for comprehensive test
        result = await normalize_text(
            text=text,
            l2_errors=l2_errors,
            essay_id=essay_id,
            language="en",
        )

        # Assert
        # Should correct both L2 and pyspellchecker errors
        assert "receive" in result.corrected_text  # L2 or pyspellchecker: "recieve" -> "receive"
        assert "document" in result.corrected_text  # pyspellchecker: "documment" -> "document"
        assert "because" in result.corrected_text  # L2: "becouse" -> "because"
        assert "happened" in result.corrected_text  # pyspellchecker: "hapened" -> "happened"

        # Should have made multiple corrections
        assert result.total_corrections >= 3
        assert result.corrected_text != text

    @pytest.mark.asyncio
    async def test_punctuation_and_capitalization_preservation(self) -> None:
        """Test that punctuation and capitalization are preserved correctly."""
        # Arrange
        text = "Hello! Thiss is a documment. It's verry importent."
        essay_id = "test-punct-001"

        # Act
        result = await normalize_text(
            text=text,
            l2_errors={},  # Empty L2 errors for punctuation test
            essay_id=essay_id,
            language="en",
        )

        # Assert
        # Verify punctuation is preserved
        assert result.corrected_text.startswith("Hello!")
        assert ". It's" in result.corrected_text
        assert result.corrected_text.endswith(".")

        # Verify corrections while maintaining structure
        assert "This" in result.corrected_text  # "Thiss" -> "This"
        assert "document" in result.corrected_text  # "documment" -> "document"
        assert "very" in result.corrected_text  # "verry" -> "very"
        assert "important" in result.corrected_text  # "importent" -> "important"

        assert result.total_corrections >= 3

    @pytest.mark.asyncio
    async def test_hyphenated_and_contractions(self) -> None:
        """Test handling of hyphenated words and contractions."""
        # Arrange
        text = "It's a well-writen artical that's verry intresting."
        essay_id = "test-hyphen-001"

        # Act
        result = await normalize_text(
            text=text,
            l2_errors={},  # Empty L2 errors for hyphenation test
            essay_id=essay_id,
            language="en",
        )

        # Assert
        # Verify contractions are preserved
        assert "It's" in result.corrected_text
        assert "that's" in result.corrected_text

        # Verify that corrections were made (don't expect specific corrections)
        # The algorithm should correct some misspellings, but exact corrections may vary
        assert result.total_corrections >= 2  # At least some corrections expected
        assert result.corrected_text != text  # Text should be changed

        # Verify the text is still readable and improved
        assert "well-" in result.corrected_text  # Hyphenated structure preserved
        assert len(result.corrected_text) > 0

    @pytest.mark.asyncio
    async def test_no_corrections_needed(self) -> None:
        """Test with text that needs no corrections."""
        # Arrange
        text = "This is a perfectly spelled sentence with no errors."
        essay_id = "test-perfect-001"

        # Act
        result = await normalize_text(
            text=text,
            l2_errors={},  # Empty L2 errors for no-corrections test
            essay_id=essay_id,
            language="en",
        )

        # Assert
        assert result.corrected_text == text  # Should be unchanged
        assert result.total_corrections == 0  # No corrections made

    @pytest.mark.asyncio
    async def test_empty_text_handling(self) -> None:
        """Test handling of empty or whitespace-only text."""
        # Arrange
        empty_text = ""
        whitespace_text = "   \n\t   "
        essay_id = "test-empty-001"

        # Act
        result_empty = await normalize_text(
            text=empty_text,
            l2_errors={},
            essay_id=essay_id,
        )
        result_whitespace = await normalize_text(
            text=whitespace_text,
            l2_errors={},
            essay_id=essay_id,
        )

        # Assert
        assert result_empty.corrected_text == ""
        assert result_empty.total_corrections == 0

        assert result_whitespace.corrected_text == whitespace_text  # Preserved
        assert result_whitespace.total_corrections == 0

    @pytest.mark.asyncio
    async def test_different_languages(self) -> None:
        """Test spell checking with different language settings."""
        # Arrange
        text = "Thiss is a tset."  # Same errors, different language
        essay_id = "test-lang-001"

        # Act - Test with English (default)
        result_en = await normalize_text(
            text=text,
            l2_errors={},
            essay_id=essay_id,
            language="en",
        )

        # Test with Spanish (should still work, though corrections may differ)
        result_es = await normalize_text(
            text=text,
            l2_errors={},
            essay_id=essay_id,
            language="es",
        )

        # Assert
        # Both should make some corrections (though results may differ)
        assert result_en.total_corrections > 0  # Should correct something
        assert (
            result_es.total_corrections >= 0
        )  # May or may not correct (depends on Spanish dictionary)

        # Corrected text should be different from original for English
        assert result_en.corrected_text != text

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
        result = await normalize_text(
            text=text,
            l2_errors={},  # Empty L2 errors for performance test
            essay_id=essay_id,
            language="en",
        )

        # Assert
        # Should make significant corrections
        assert result.total_corrections >= 10  # Many errors to correct
        assert len(result.corrected_text) > 0
        assert result.corrected_text != text

        # Verify that common misspellings were corrected (without expecting exact results)
        # The text should be significantly improved
        assert "Thiss" not in result.corrected_text  # Common misspellings should be fixed
        assert "documment" not in result.corrected_text
        assert "containns" not in result.corrected_text
        assert "errrors" not in result.corrected_text
        assert "misstakes" not in result.corrected_text

        # Verify text is still coherent and readable
        assert "spellchecker" in result.corrected_text.lower()  # Key words preserved

    @pytest.mark.asyncio
    async def test_case_preservation(self) -> None:
        """Test that original case patterns are preserved in corrections."""
        # Arrange
        text = "RECIEVE IS WRONG. Recieve Is Title Case. recieve is lowercase."
        essay_id = "test-case-001"

        # Act
        l2_errors = {"recieve": "receive"}  # L2 error for case preservation test
        result = await normalize_text(
            text=text,
            l2_errors=l2_errors,
            essay_id=essay_id,
            language="en",
        )

        # Assert
        # Verify case preservation
        assert "RECEIVE IS" in result.corrected_text  # Uppercase preserved
        assert "Receive Is" in result.corrected_text  # Title case preserved
        assert "receive is" in result.corrected_text  # Lowercase preserved
        assert result.total_corrections >= 3  # Should correct all three instances

    @pytest.mark.asyncio
    async def test_uppercase_case_normalization(self) -> None:
        """Test that uppercase misspelled words are properly detected and corrected."""
        # Arrange - Use words NOT in L2 dictionary to test pyspellchecker normalization
        text = "THISS DOCUMMENT HAS ERRRORS."
        essay_id = "test-uppercase-norm-001"

        # Act
        result = await normalize_text(
            text=text,
            l2_errors={},  # Empty L2 errors for uppercase normalization test
            essay_id=essay_id,
            language="en",
        )

        # Assert
        # Verify uppercase is preserved in corrections
        assert "THIS DOCUMENT" in result.corrected_text  # "THISS DOCUMMENT" -> "THIS DOCUMENT"
        assert "ERRORS" in result.corrected_text  # "ERRRORS" -> "ERRORS"
        assert result.total_corrections >= 3  # Should correct all three words
        assert result.corrected_text != text  # Text should be changed

        # Verify the entire sentence structure is preserved
        assert result.corrected_text.endswith(".")
        assert result.corrected_text.startswith("THIS")
