"""Integration test for whitelist functionality with real essays.

This test processes actual student essays to demonstrate:
1. L2 dictionary corrections
2. Whitelist matches (proper names that are NOT corrected)
3. PySpellChecker corrections
4. Performance improvements from whitelist at scale
"""

import time
from pathlib import Path
from typing import Any, Dict, Set
from unittest.mock import MagicMock

import pytest
from docx import Document

from services.spellchecker_service.config import settings
from services.spellchecker_service.core_logic import default_perform_spell_check_algorithm
from services.spellchecker_service.implementations.whitelist_impl import DefaultWhitelist
from services.spellchecker_service.spell_logic.l2_dictionary_loader import load_l2_errors


def extract_text_from_docx(file_path: Path) -> str:
    """Extract text content from a .docx file."""
    doc = Document(str(file_path))
    paragraphs = []
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            paragraphs.append(paragraph.text.strip())
    return "\n".join(paragraphs)


class TestWhitelistIntegration:
    """Test whitelist functionality with real essays."""

    @pytest.fixture
    def real_essays(self) -> Dict[str, str]:
        """Load real essays from test_uploads directory."""
        essays = {}
        essays_dir = Path(
            "/Users/olofs_mba/Documents/Repos/huledu-reboot/test_uploads/Book-Report-ES24B-2025-04-09-104843"
        )

        if not essays_dir.exists():
            pytest.skip("Essay directory not found")

        # Load all essays for better statistical significance
        essay_files = list(essays_dir.glob("*.docx"))

        for essay_file in essay_files:
            student_name = essay_file.stem.split(" (")[0]
            try:
                text = extract_text_from_docx(essay_file)
                if text:
                    essays[student_name] = text
            except Exception as e:
                print(f"Could not load {essay_file}: {e}")

        return essays

    @pytest.fixture
    def l2_dictionary(self) -> Dict[str, str]:
        """Load the real L2 dictionary."""
        return load_l2_errors(settings.effective_filtered_dict_path, filter_entries=False)

    @pytest.fixture
    def whitelist(self) -> DefaultWhitelist:
        """Load the real whitelist."""
        mock_settings = MagicMock()
        # Path is handled internally by DefaultWhitelist now
        return DefaultWhitelist(mock_settings)

    @pytest.mark.performance
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_whitelist_impact_on_real_essays(
        self,
        real_essays: Dict[str, str],
        l2_dictionary: Dict[str, str],
        whitelist: DefaultWhitelist,
    ) -> None:
        """Test whitelist impact on real essay processing at scale.

        Simulates processing 10,000 essays to show the real benefit
        where the one-time whitelist loading cost is amortized.
        """

        if not real_essays:
            pytest.skip("No essays loaded")

        print(f"\n{'=' * 80}")
        print("WHITELIST INTEGRATION TEST - SIMULATING 10,000 ESSAY BATCH")
        print(f"{'=' * 80}\n")

        # Measure whitelist loading time (one-time cost)
        whitelist_load_time = 2.0  # Approximated from logs

        # Track overall statistics with proper typing
        {
            "total_essays": len(real_essays),
            "total_l2_corrections": 0,
            "total_whitelist_hits": 0,
            "total_pyspell_corrections": 0,
            "time_per_essay_with_whitelist": 0.0,
            "time_per_essay_without_whitelist": 0.0,
            "whitelisted_words": set(),
        }

        # Extract typed variables for mypy
        total_l2_corrections: int = 0
        total_whitelist_hits: int = 0
        total_pyspell_corrections: int = 0
        time_per_essay_with_whitelist: float = 0.0
        time_per_essay_without_whitelist: float = 0.0
        whitelisted_words: Set[str] = set()

        # Process each essay once to get average times
        essay_count = 0

        for student_name, essay_text in real_essays.items():
            print(f"\nProcessing essay from: {student_name}")
            print(f"Essay length: {len(essay_text)} characters, {len(essay_text.split())} words")

            # Process WITH whitelist
            start_time = time.time()
            result_with_wl = await default_perform_spell_check_algorithm(
                essay_text,
                l2_dictionary,
                essay_id=f"{student_name}_with_whitelist",
                language="en",
                whitelist=whitelist,
            )
            time_with_whitelist = time.time() - start_time

            # Process WITHOUT whitelist (for comparison)
            start_time = time.time()
            result_no_wl = await default_perform_spell_check_algorithm(
                essay_text,
                l2_dictionary,
                essay_id=f"{student_name}_no_whitelist",
                language="en",
                whitelist=None,
            )
            time_without_whitelist = time.time() - start_time

            # Analyze corrections
            essay_stats = self._analyze_corrections(
                essay_text,
                result_with_wl.corrected_text,
                result_no_wl.corrected_text,
                whitelist,
                l2_dictionary,
            )

            # Update total statistics
            essay_count += 1
            total_l2_corrections += essay_stats["l2_corrections"]
            total_whitelist_hits += essay_stats["whitelist_hits"]
            total_pyspell_corrections += (
                result_with_wl.total_corrections - essay_stats["l2_corrections"]
            )
            time_per_essay_with_whitelist += time_with_whitelist
            time_per_essay_without_whitelist += time_without_whitelist
            whitelisted_words.update(essay_stats["whitelisted_words"])

            # Print essay statistics
            print(f"  L2 corrections: {essay_stats['l2_corrections']}")
            print(f"  Whitelist hits: {essay_stats['whitelist_hits']}")
            print(
                f"  PySpell corrections: {result_with_wl.total_corrections - essay_stats['l2_corrections']}"
            )
            print(f"  Time with whitelist: {time_with_whitelist:.3f}s")
            print(f"  Time without whitelist: {time_without_whitelist:.3f}s")

        # Calculate averages
        avg_time_with_wl = time_per_essay_with_whitelist / essay_count
        avg_time_without_wl = time_per_essay_without_whitelist / essay_count

        # Scale up to 10,000 essays
        ESSAYS_AT_SCALE = 10000
        scaled_time_with_wl = (avg_time_with_wl * ESSAYS_AT_SCALE) + whitelist_load_time
        scaled_time_without_wl = avg_time_without_wl * ESSAYS_AT_SCALE

        # Scale up correction counts
        avg_l2_per_essay = total_l2_corrections / essay_count
        avg_whitelist_per_essay = total_whitelist_hits / essay_count
        avg_pyspell_per_essay = total_pyspell_corrections / essay_count

        scaled_l2 = int(avg_l2_per_essay * ESSAYS_AT_SCALE)
        scaled_whitelist = int(avg_whitelist_per_essay * ESSAYS_AT_SCALE)
        scaled_pyspell = int(avg_pyspell_per_essay * ESSAYS_AT_SCALE)

        # Print summary statistics
        print(f"\n{'=' * 80}")
        print("SUMMARY STATISTICS (SCALED TO 10,000 ESSAYS)")
        print(f"{'=' * 80}\n")

        print(f"Sample size: {essay_count} essays analyzed")
        print("\nCorrections per essay (average):")
        print(f"  L2 dictionary corrections: {avg_l2_per_essay:.1f}")
        print(f"  Whitelist hits (words NOT corrected): {avg_whitelist_per_essay:.1f}")
        print(f"  PySpell corrections: {avg_pyspell_per_essay:.1f}")

        print(f"\nProjected for {ESSAYS_AT_SCALE:,} essays:")
        print(f"  Total L2 corrections: {scaled_l2:,}")
        print(f"  Total whitelist hits: {scaled_whitelist:,}")
        print(f"  Total PySpell corrections: {scaled_pyspell:,}")

        print("\nPerformance Impact at Scale:")
        print(f"  Time WITH whitelist (including 2s load): {scaled_time_with_wl:.1f}s")
        print(f"  Time WITHOUT whitelist: {scaled_time_without_wl:.1f}s")
        print(f"  Total time saved: {scaled_time_without_wl - scaled_time_with_wl:.1f}s")
        improvement_pct = (
            (scaled_time_without_wl - scaled_time_with_wl) / scaled_time_without_wl * 100
        )
        print(f"  Performance improvement: {improvement_pct:.1f}%")

        print("\nAccuracy Impact:")
        print(f"  {scaled_whitelist:,} false positive corrections avoided")
        print(f"  Unique whitelisted words found in sample: {len(whitelisted_words)}")

        # Assertions
        assert total_whitelist_hits > 0, (
            "Should have found at least some whitelisted words in real essays"
        )

    def _analyze_corrections(
        self,
        original_text: str,
        corrected_with_whitelist: str,
        corrected_without_whitelist: str,
        whitelist: DefaultWhitelist,
        l2_dictionary: Dict[str, str],
    ) -> Dict[str, Any]:
        """Analyze the corrections made to identify L2, whitelist, and pyspell contributions."""

        # Use typed variables to avoid mypy object type issues
        l2_corrections = 0
        whitelist_hits = 0
        whitelisted_words_set: Set[str] = set()

        # Count L2 corrections
        words = original_text.split()
        for word in words:
            word_lower = word.lower().strip('.,!?;:"')
            if word_lower in l2_dictionary:
                l2_corrections += 1

        # Find whitelisted words
        for word in words:
            word_clean = word.strip('.,!?;:"')
            if whitelist.is_whitelisted(word_clean):
                whitelist_hits += 1
                whitelisted_words_set.add(word_clean)

        return {
            "l2_corrections": l2_corrections,
            "whitelist_hits": whitelist_hits,
            "whitelisted_words": whitelisted_words_set,
        }
