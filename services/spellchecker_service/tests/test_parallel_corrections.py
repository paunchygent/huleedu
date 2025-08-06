"""Tests for parallel processing integration with the spell check algorithm."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from services.spellchecker_service.core_logic import default_perform_spell_check_algorithm
from services.spellchecker_service.implementations.parallel_processor_impl import (
    DefaultParallelProcessor,
)


class TestParallelCorrections:
    """Test suite for parallel word correction functionality with algorithm integration."""

    @pytest.mark.asyncio
    async def test_parallel_correct_words_error_handling(self) -> None:
        """Test error handling in parallel corrections."""
        # Create mock spell checker that raises exception
        mock_checker = MagicMock()
        mock_checker.correction.side_effect = Exception("Test error")

        spell_checker_cache = {
            "en_d1": mock_checker,
            "en_d2": mock_checker,
        }

        words_to_correct = [(0, "test")]

        processor = DefaultParallelProcessor()
        processor.max_concurrent = 1
        processor.timeout_seconds = 5.0

        results = await processor.process_corrections_parallel(
            words_to_correct=words_to_correct,
            spell_checker_cache=spell_checker_cache,
            correlation_id=uuid4(),
            essay_id="test_essay",
        )

        # Should return None for failed corrections
        assert results[0][0] is None
        assert results[0][1] >= 0  # Time should still be recorded

    @pytest.mark.asyncio
    async def test_algorithm_parallel_vs_sequential(self) -> None:
        """Test that parallel and sequential modes produce identical results."""
        text = "Teh quck brown fox jumps ovr teh lazy dog"
        l2_errors: dict[str, str] = {}  # No L2 errors for this test

        # Mock whitelist
        mock_whitelist = MagicMock()
        mock_whitelist.is_whitelisted.return_value = False

        with patch("services.spellchecker_service.core_logic._spellchecker_cache", {}):
            # Initialize spell checker cache
            from spellchecker import SpellChecker

            from services.spellchecker_service.core_logic import _spellchecker_cache
            from services.spellchecker_service.implementations.parallel_processor_impl import (
                DefaultParallelProcessor,
            )

            _spellchecker_cache["en_d1"] = SpellChecker(language="en", distance=1)
            _spellchecker_cache["en_d2"] = SpellChecker(language="en", distance=2)

            # Create parallel processor
            parallel_processor = DefaultParallelProcessor()

            # Test with parallel processing enabled
            corrected_parallel, count_parallel = await default_perform_spell_check_algorithm(
                text=text,
                l2_errors=l2_errors,
                essay_id="test_parallel",
                language="en",
                correlation_id=uuid4(),
                whitelist=mock_whitelist,
                parallel_processor=parallel_processor,
                enable_parallel=True,
                max_concurrent=5,
                batch_size=100,
                parallel_timeout=5.0,
                min_words_for_parallel=1,  # Force parallel even for small text
            )

            # Test with parallel processing disabled
            corrected_sequential, count_sequential = await default_perform_spell_check_algorithm(
                text=text,
                l2_errors=l2_errors,
                essay_id="test_sequential",
                language="en",
                correlation_id=uuid4(),
                whitelist=mock_whitelist,
                parallel_processor=parallel_processor,
                enable_parallel=False,
                max_concurrent=5,
                batch_size=100,
                parallel_timeout=5.0,
                min_words_for_parallel=1,
            )

            # Results should be identical
            assert corrected_parallel == corrected_sequential
            assert count_parallel == count_sequential

    @pytest.mark.asyncio
    async def test_algorithm_batch_processing(self) -> None:
        """Test that batch processing works correctly for large word lists."""
        # Create a text with many misspelled words
        words = ["teh"] * 150  # 150 misspelled words
        text = " ".join(words)
        l2_errors: dict[str, str] = {}

        mock_whitelist = MagicMock()
        mock_whitelist.is_whitelisted.return_value = False

        with patch("services.spellchecker_service.core_logic._spellchecker_cache", {}):
            from spellchecker import SpellChecker

            from services.spellchecker_service.core_logic import _spellchecker_cache
            from services.spellchecker_service.implementations.parallel_processor_impl import (
                DefaultParallelProcessor,
            )

            _spellchecker_cache["en_d1"] = SpellChecker(language="en", distance=1)
            _spellchecker_cache["en_d2"] = SpellChecker(language="en", distance=2)

            # Create parallel processor
            parallel_processor = DefaultParallelProcessor()

            corrected_text, correction_count = await default_perform_spell_check_algorithm(
                text=text,
                l2_errors=l2_errors,
                essay_id="test_batch",
                language="en",
                correlation_id=uuid4(),
                whitelist=mock_whitelist,
                parallel_processor=parallel_processor,
                enable_parallel=True,
                max_concurrent=10,
                batch_size=50,  # Process in batches of 50
                parallel_timeout=5.0,
                min_words_for_parallel=1,
            )

            # Should correct all instances
            assert correction_count == 150
            assert "the" in corrected_text  # "teh" should be corrected to "the"
            assert corrected_text.count("the") == 150

    @pytest.mark.asyncio
    async def test_algorithm_min_words_threshold(self) -> None:
        """Test that min_words_for_parallel threshold works correctly."""
        text = "Teh fox"  # Only 2 words, below typical threshold
        l2_errors: dict[str, str] = {}

        mock_whitelist = MagicMock()
        mock_whitelist.is_whitelisted.return_value = False

        with patch("services.spellchecker_service.core_logic._spellchecker_cache", {}):
            from spellchecker import SpellChecker

            from services.spellchecker_service.core_logic import _spellchecker_cache
            from services.spellchecker_service.implementations.parallel_processor_impl import (
                DefaultParallelProcessor,
            )

            _spellchecker_cache["en_d1"] = SpellChecker(language="en", distance=1)
            _spellchecker_cache["en_d2"] = SpellChecker(language="en", distance=2)

            # Create parallel processor
            parallel_processor = DefaultParallelProcessor()

            # Test with high threshold (should use sequential)
            corrected_text, _ = await default_perform_spell_check_algorithm(
                text=text,
                l2_errors=l2_errors,
                essay_id="test_threshold",
                language="en",
                correlation_id=uuid4(),
                whitelist=mock_whitelist,
                parallel_processor=parallel_processor,
                enable_parallel=True,
                min_words_for_parallel=10,  # High threshold, should use sequential
            )

            # Should still correct the text
            assert "The" in corrected_text or "the" in corrected_text

    @pytest.mark.asyncio
    async def test_algorithm_whitelist_integration(self) -> None:
        """Test that whitelist properly excludes words from parallel processing."""
        text = "Teh Microsoft Excel documment"
        l2_errors: dict[str, str] = {}

        # Mock whitelist that whitelists "Microsoft" and "Excel"
        mock_whitelist = MagicMock()
        mock_whitelist.is_whitelisted.side_effect = lambda w: w in ["Microsoft", "Excel"]

        with patch("services.spellchecker_service.core_logic._spellchecker_cache", {}):
            from spellchecker import SpellChecker

            from services.spellchecker_service.core_logic import _spellchecker_cache
            from services.spellchecker_service.implementations.parallel_processor_impl import (
                DefaultParallelProcessor,
            )

            _spellchecker_cache["en_d1"] = SpellChecker(language="en", distance=1)
            _spellchecker_cache["en_d2"] = SpellChecker(language="en", distance=2)

            # Create parallel processor
            parallel_processor = DefaultParallelProcessor()

            corrected_text, correction_count = await default_perform_spell_check_algorithm(
                text=text,
                l2_errors=l2_errors,
                essay_id="test_whitelist",
                language="en",
                correlation_id=uuid4(),
                whitelist=mock_whitelist,
                parallel_processor=parallel_processor,
                enable_parallel=True,
                min_words_for_parallel=1,
            )

            # Should preserve whitelisted words
            assert "Microsoft" in corrected_text
            assert "Excel" in corrected_text
            # Should correct non-whitelisted words
            assert "Teh" not in corrected_text  # Should be corrected
            assert "documment" not in corrected_text  # Should be corrected
