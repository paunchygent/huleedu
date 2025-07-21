"""Unit tests for adaptive edit distance functionality."""

from services.spellchecker_service.core_logic import get_adaptive_edit_distance


class TestAdaptiveEditDistance:
    """Test the adaptive edit distance function."""

    def test_long_words_get_distance_1(self) -> None:
        """Words longer than 9 characters should get distance=1."""
        # Test various long words
        assert get_adaptive_edit_distance("overconsumption") == 1  # 15 chars
        assert get_adaptive_edit_distance("overconsuming") == 1  # 13 chars
        assert get_adaptive_edit_distance("development") == 1  # 11 chars
        assert get_adaptive_edit_distance("programming") == 1  # 11 chars
        assert get_adaptive_edit_distance("algorithms") == 1  # 10 chars

    def test_compound_words_get_distance_1(self) -> None:
        """Words with hyphens should get distance=1."""
        assert get_adaptive_edit_distance("short-term") == 1
        assert get_adaptive_edit_distance("career-suicide") == 1
        assert get_adaptive_edit_distance("self-employed") == 1
        assert get_adaptive_edit_distance("e-mail") == 1
        assert get_adaptive_edit_distance("up-to-date") == 1

    def test_contractions_get_distance_1(self) -> None:
        """Words with apostrophes should get distance=1."""
        assert get_adaptive_edit_distance("children's") == 1
        assert get_adaptive_edit_distance("don't") == 1
        assert get_adaptive_edit_distance("won't") == 1
        assert get_adaptive_edit_distance("it's") == 1
        assert get_adaptive_edit_distance("they're") == 1

    def test_short_simple_words_get_distance_2(self) -> None:
        """Short, simple words should get distance=2 for better accuracy."""
        assert get_adaptive_edit_distance("cat") == 2  # 3 chars
        assert get_adaptive_edit_distance("dog") == 2  # 3 chars
        assert get_adaptive_edit_distance("house") == 2  # 5 chars
        assert get_adaptive_edit_distance("school") == 2  # 6 chars
        assert get_adaptive_edit_distance("friend") == 2  # 6 chars
        assert get_adaptive_edit_distance("teacher") == 2  # 7 chars
        assert get_adaptive_edit_distance("computer") == 2  # 8 chars exactly

    def test_edge_cases(self) -> None:
        """Test edge cases for the 9-character boundary."""
        # 8 characters - should be distance=2
        assert get_adaptive_edit_distance("exactly8") == 2
        assert get_adaptive_edit_distance("12345678") == 2

        # 9 characters exactly - should be distance=2
        assert get_adaptive_edit_distance("exactly9x") == 2
        assert get_adaptive_edit_distance("123456789") == 2
        assert get_adaptive_edit_distance("algorithm") == 2  # 9 chars

        # 10 characters - should be distance=1
        assert get_adaptive_edit_distance("exactly10x") == 1
        assert get_adaptive_edit_distance("1234567890") == 1

    def test_mixed_conditions(self) -> None:
        """Test words that meet multiple conditions."""
        # Short word with apostrophe - apostrophe takes precedence
        assert get_adaptive_edit_distance("I'm") == 1
        assert get_adaptive_edit_distance("we'd") == 1

        # Long word with hyphen - both conditions result in distance=1
        assert get_adaptive_edit_distance("self-improvement") == 1
        assert get_adaptive_edit_distance("merry-go-round") == 1
