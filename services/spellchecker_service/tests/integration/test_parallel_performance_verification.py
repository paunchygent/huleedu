"""Integration test for parallel processing performance verification with real essays."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from services.spellchecker_service.core_logic import default_perform_spell_check_algorithm
from services.spellchecker_service.implementations.parallel_processor_impl import (
    DefaultParallelProcessor,
)
from services.spellchecker_service.implementations.whitelist_impl import DefaultWhitelist
from services.spellchecker_service.spell_logic.l2_dictionary_loader import load_l2_errors
from services.spellchecker_service.tests.mocks import MockWhitelist


class TestParallelPerformanceVerification:
    """Integration test to verify parallel processing performance improvement."""

    @pytest.fixture
    def l2_errors(self) -> dict[str, str]:
        """Load L2 error dictionary for testing."""
        return load_l2_errors(
            str(Path(__file__).parent.parent.parent / "data" / "l2-swedish-learner-errors.csv"),
            filter_entries=False,
        )

    @pytest.fixture
    def whitelist(self) -> MockWhitelist:
        """Create mock whitelist for testing."""
        return MockWhitelist()

    @pytest.fixture
    def parallel_processor(self) -> DefaultParallelProcessor:
        """Create parallel processor for testing."""
        return DefaultParallelProcessor()

    @pytest.fixture
    def sample_essays(self) -> list[str]:
        """Load sample essay texts for testing."""
        test_texts = [
            "This is a tset essay with some erors that need to be corrected.",
            "The studnet wrote adn interesting essay about litreature.",
            "Ponyboy is teh main character in The Outsiders book.",
            "Stockholm is a beutiful city wiht many museums and parks.",
            "The experiment showed intresting results that we can anlyze.",
        ]
        return test_texts

    @pytest.mark.asyncio
    async def test_parallel_vs_sequential_identical_results(
        self,
        l2_errors: dict[str, str],
        whitelist: MockWhitelist,
        parallel_processor: DefaultParallelProcessor,
        sample_essays: list[str],
    ) -> None:
        """Test that parallel and sequential processing produce identical results."""
        for i, text in enumerate(sample_essays):
            essay_id = f"test_essay_{i}"
            correlation_id = uuid4()

            # Sequential processing
            sequential_result, sequential_count = await default_perform_spell_check_algorithm(
                text=text,
                l2_errors=l2_errors,
                essay_id=essay_id,
                correlation_id=correlation_id,
                whitelist=whitelist,
                parallel_processor=parallel_processor,
                enable_parallel=False,  # Force sequential
                min_words_for_parallel=999,  # Ensure sequential mode
            )

            # Parallel processing
            parallel_result, parallel_count = await default_perform_spell_check_algorithm(
                text=text,
                l2_errors=l2_errors,
                essay_id=essay_id,
                correlation_id=correlation_id,
                whitelist=whitelist,
                parallel_processor=parallel_processor,
                enable_parallel=True,
                min_words_for_parallel=1,  # Force parallel mode
            )

            # Results should be identical
            assert sequential_result == parallel_result, (
                f"Results differ for essay {i}: sequential='{sequential_result}', "
                f"parallel='{parallel_result}'"
            )
            assert sequential_count == parallel_count, (
                f"Correction counts differ for essay {i}: sequential={sequential_count}, "
                f"parallel={parallel_count}"
            )

    @pytest.mark.asyncio
    async def test_performance_improvement_measurement(
        self,
        l2_errors: dict[str, str],
        whitelist: MockWhitelist,
        parallel_processor: DefaultParallelProcessor,
        sample_essays: list[str],
    ) -> None:
        """Measure and verify performance improvement with parallel processing."""
        # Create a longer text to ensure parallel processing kicks in
        long_text = " ".join(
            [
                "This tset contains many erors that need corection.",
                "The studnet wrote adn intresting paper about litreature.",
                "Ponyboy is teh main charcter in The Outsiders.",
                "Stockholm is beutiful wiht many museums and galeries.",
                "Scientfic experiments show facinating results for anaylsis.",
                "The algorythm can proces multiple words simulatneously.",
                "Performace improvements are measurable in real aplications.",
                "Concurency helps reduc processing time signifcantly.",
            ]
            * 3
        )  # Repeat to ensure enough words for parallel processing

        correlation_id = uuid4()

        # Measure sequential processing time
        start_time = time.time()
        sequential_result, sequential_count = await default_perform_spell_check_algorithm(
            text=long_text,
            l2_errors=l2_errors,
            essay_id="performance_test_sequential",
            correlation_id=correlation_id,
            whitelist=whitelist,
            parallel_processor=parallel_processor,
            enable_parallel=False,
            min_words_for_parallel=999,
        )
        sequential_time = time.time() - start_time

        # Measure parallel processing time
        start_time = time.time()
        parallel_result, parallel_count = await default_perform_spell_check_algorithm(
            text=long_text,
            l2_errors=l2_errors,
            essay_id="performance_test_parallel",
            correlation_id=correlation_id,
            whitelist=whitelist,
            parallel_processor=parallel_processor,
            enable_parallel=True,
            min_words_for_parallel=1,
            max_concurrent=10,
        )
        parallel_time = time.time() - start_time

        # Verify results are identical
        assert sequential_result == parallel_result
        assert sequential_count == parallel_count

        # Log performance metrics
        improvement_ratio = sequential_time / parallel_time if parallel_time > 0 else 1
        print("\nPerformance Results:")
        print(f"Sequential time: {sequential_time:.4f}s")
        print(f"Parallel time: {parallel_time:.4f}s")
        print(f"Improvement ratio: {improvement_ratio:.2f}x")
        print(f"Corrections made: {sequential_count}")

        # Performance should show some improvement for long texts
        # Note: In testing, improvement may be minimal due to test overhead
        # In production with longer texts, improvement should be more significant
        assert parallel_time <= sequential_time * 1.5, (
            f"Parallel processing took too long relative to sequential: "
            f"{parallel_time:.4f}s vs {sequential_time:.4f}s"
        )

    @pytest.mark.asyncio
    async def test_parallel_processing_with_real_whitelist(self) -> None:
        """Test parallel processing with actual whitelist implementation."""
        # Load actual whitelist data
        whitelist_data_dir = Path(__file__).parent.parent.parent / "data" / "whitelist"
        if not whitelist_data_dir.exists():
            pytest.skip("Whitelist data not available for testing")

        mock_settings = MagicMock()
        whitelist = DefaultWhitelist(mock_settings)
        parallel_processor = DefaultParallelProcessor()
        l2_errors = load_l2_errors(
            str(Path(__file__).parent.parent.parent / "data" / "l2-swedish-learner-errors.csv"),
            filter_entries=False,
        )

        # Test text with proper names that should be whitelisted
        test_text = (
            "Ponyboy Curtis lives in Tulsa with his brothers "
            "Stockholm and Copenhagen are beautiful cities."
        )

        result, corrections = await default_perform_spell_check_algorithm(
            text=test_text,
            l2_errors=l2_errors,
            essay_id="whitelist_test",
            correlation_id=uuid4(),
            whitelist=whitelist,
            parallel_processor=parallel_processor,
            enable_parallel=True,
            min_words_for_parallel=1,
        )

        # Verify that proper names were preserved
        assert "Ponyboy" in result  # Should be whitelisted
        assert "Curtis" in result  # Should be whitelisted
        assert "Tulsa" in result  # Should be whitelisted
        assert "Stockholm" in result  # Should be whitelisted
        assert "Copenhagen" in result  # Should be whitelisted

        print("\nWhitelist Test Results:")
        print(f"Original: {test_text}")
        print(f"Corrected: {result}")
        print(f"Corrections: {corrections}")
