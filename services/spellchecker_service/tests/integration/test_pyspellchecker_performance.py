"""
Isolated integration test to understand PySpellChecker performance bottleneck.

This test reproduces the exact performance issue we're seeing in production
with specific words that take 0.3-1.0 seconds to process.
"""

import time
from typing import List, Tuple
import pytest
from spellchecker import SpellChecker


def time_correction(spell_checker: SpellChecker, word: str) -> Tuple[str, float]:
    """Time a single word correction."""
    start = time.time()
    corrected = spell_checker.correction(word)
    duration = time.time() - start
    return corrected, duration


def analyze_candidates(spell_checker: SpellChecker, word: str) -> dict:
    """Analyze the candidate generation for a word."""
    start = time.time()
    candidates = spell_checker.candidates(word)
    candidates_time = time.time() - start
    
    # Count edit distance 1 and 2 candidates
    start_ed1 = time.time()
    ed1_candidates = spell_checker.edit_distance_1(word)
    ed1_time = time.time() - start_ed1
    
    start_ed2 = time.time()
    ed2_candidates = spell_checker.edit_distance_2(word)
    ed2_time = time.time() - start_ed2
    
    return {
        "word": word,
        "word_length": len(word),
        "candidates": len(candidates) if candidates else 0,
        "candidates_time": candidates_time,
        "ed1_count": len(ed1_candidates),
        "ed1_time": ed1_time,
        "ed2_count": len(ed2_candidates),
        "ed2_time": ed2_time,
    }


class TestPySpellCheckerPerformance:
    """Test PySpellChecker performance with problematic words from real essays."""
    
    # Actual problematic words from the logs
    SLOW_WORDS = [
        "overconsumption",  # 15 chars, takes ~0.8-1.0s
        "overconsuming",    # 13 chars, takes ~0.7s
        "children's",       # 10 chars with apostrophe, takes ~0.35s
        "short-term",       # 10 chars with hyphen, takes ~0.34s
        "career-suicide",   # 14 chars with hyphen, takes ~0.77s
    ]
    
    FAST_WORDS = [
        "dangures",         # 8 chars, simple misspelling
        "recieve",          # 7 chars, common misspelling
        "teh",              # 3 chars, common typo
    ]

    def test_default_distance_performance(self):
        """Test performance with default distance=2."""
        spell_checker = SpellChecker(language='en')  # Default distance=2
        
        print("\n\n=== Performance with distance=2 (default) ===")
        print(f"{'Word':<20} {'Length':<8} {'Corrected':<20} {'Time (s)':<10}")
        print("-" * 60)
        
        for word in self.SLOW_WORDS + self.FAST_WORDS:
            corrected, duration = time_correction(spell_checker, word)
            print(f"{word:<20} {len(word):<8} {corrected or 'None':<20} {duration:<10.3f}")
            
            # Assert slow words are actually slow with distance=2
            if word in self.SLOW_WORDS:
                assert duration > 0.1, f"{word} should be slow but took only {duration:.3f}s"

    def test_distance_1_performance(self):
        """Test performance with distance=1 as recommended by docs."""
        spell_checker = SpellChecker(language='en', distance=1)
        
        print("\n\n=== Performance with distance=1 (optimized) ===")
        print(f"{'Word':<20} {'Length':<8} {'Corrected':<20} {'Time (s)':<10}")
        print("-" * 60)
        
        for word in self.SLOW_WORDS + self.FAST_WORDS:
            corrected, duration = time_correction(spell_checker, word)
            print(f"{word:<20} {len(word):<8} {corrected or 'None':<20} {duration:<10.3f}")
            
            # All words should be fast with distance=1
            assert duration < 0.1, f"{word} took {duration:.3f}s, expected < 0.1s"

    def test_candidate_generation_analysis(self):
        """Analyze why certain words are slow."""
        spell_checker = SpellChecker(language='en')  # Default distance=2
        
        print("\n\n=== Candidate Generation Analysis ===")
        print(f"{'Word':<20} {'Len':<5} {'ED1':<8} {'ED1 Time':<10} {'ED2':<10} {'ED2 Time':<10}")
        print("-" * 75)
        
        for word in self.SLOW_WORDS[:3]:  # Just analyze a few slow words
            analysis = analyze_candidates(spell_checker, word)
            print(f"{analysis['word']:<20} {analysis['word_length']:<5} "
                  f"{analysis['ed1_count']:<8} {analysis['ed1_time']:<10.3f} "
                  f"{analysis['ed2_count']:<10} {analysis['ed2_time']:<10.3f}")

    def test_unknown_words_performance(self):
        """Test the unknown() method performance which is always fast."""
        spell_checker = SpellChecker(language='en')
        
        print("\n\n=== Unknown Words Check Performance ===")
        all_words = self.SLOW_WORDS + self.FAST_WORDS
        
        start = time.time()
        unknown_words = spell_checker.unknown(all_words)
        duration = time.time() - start
        
        print(f"Checking {len(all_words)} words took {duration:.3f}s")
        print(f"Unknown words: {unknown_words}")
        
        # This should always be fast
        assert duration < 0.01, f"unknown() took {duration:.3f}s, expected < 0.01s"

    @pytest.mark.parametrize("distance,word,expected_max_time", [
        (2, "overconsumption", 2.0),  # Allow up to 2s for distance=2
        (1, "overconsumption", 0.1),  # Should be fast with distance=1
        (2, "teh", 0.01),             # Short words are always fast
        (1, "teh", 0.01),
    ])
    def test_specific_word_performance(self, distance, word, expected_max_time):
        """Parameterized test for specific word/distance combinations."""
        spell_checker = SpellChecker(language='en', distance=distance)
        corrected, duration = time_correction(spell_checker, word)
        
        assert duration < expected_max_time, \
            f"{word} with distance={distance} took {duration:.3f}s, expected < {expected_max_time}s"


if __name__ == "__main__":
    # Run the test directly to see print output
    test = TestPySpellCheckerPerformance()
    test.test_default_distance_performance()
    test.test_distance_1_performance()
    test.test_candidate_generation_analysis()
    test.test_unknown_words_performance()