"""
Unit tests for string similarity utilities.

Tests the fuzzy matching algorithms using RapidFuzz library for student name matching.
"""

from __future__ import annotations

import pytest

from services.nlp_service.features.student_matching.utils.string_similarity import (
    best_match_from_list,
    exact_match,
    levenshtein_distance,
    normalized_similarity,
    partial_similarity,
    similarity_with_threshold,
)


class TestNormalizedSimilarity:
    """Tests for the normalized_similarity function using token_sort_ratio."""

    @pytest.mark.parametrize(
        "str1, str2, expected_min, expected_max",
        [
            # Exact matches should score 1.0
            ("Anna Andersson", "Anna Andersson", 1.0, 1.0),
            # Name order variations (token_sort handles these well)
            ("Anna Andersson", "Andersson Anna", 1.0, 1.0),
            ("John Smith Jr", "Jr Smith John", 1.0, 1.0),
            # Swedish names with good similarity
            ("Anna Andersson", "Anna Andersen", 0.85, 1.0),
            ("Erik Johansson", "Eric Johannson", 0.8, 1.0),
            # Case insensitive matching
            ("ANNA ANDERSSON", "anna andersson", 1.0, 1.0),
            ("Anna Andersson", "ANNA ANDERSSON", 1.0, 1.0),
        ],
    )
    def test_normalized_similarity_expected_ranges(
        self, str1: str, str2: str, expected_min: float, expected_max: float
    ) -> None:
        """Test similarity scores fall within expected ranges."""
        score = normalized_similarity(str1, str2)
        assert expected_min <= score <= expected_max
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize(
        "str1, str2, expected",
        [
            # Empty string cases should return 0.0
            ("", "Anna", 0.0),
            ("Anna", "", 0.0),
            (None, "Anna", 0.0),  # type: ignore
            ("Anna", None, 0.0),  # type: ignore
        ],
    )
    def test_normalized_similarity_empty_cases(
        self, str1: str | None, str2: str | None, expected: float
    ) -> None:
        """Test empty and None string handling."""
        score = normalized_similarity(str1, str2)  # type: ignore
        assert score == expected

    def test_normalized_similarity_swedish_names(self) -> None:
        """Test with realistic Swedish name pairs."""
        # These should have reasonable similarity for student matching
        assert normalized_similarity("Anna-Karin Svensson", "Anna Karin Svensson") > 0.9
        assert normalized_similarity("Björn Andersson", "Bjorn Andersson") > 0.9
        assert normalized_similarity("Carl von Linné", "von Linné Carl") == 1.0


class TestPartialSimilarity:
    """Tests for the partial_similarity function."""

    @pytest.mark.parametrize(
        "str1, str2, expected_min",
        [
            # Substring matches should score high
            ("Anna", "Anna Andersson", 0.9),
            ("Andersson", "Anna Andersson", 0.9),
            ("John", "Johnson", 0.8),
            # Partial matches in names
            ("Anna Sven", "Anna Svensson", 0.8),
            ("Erik J", "Erik Johansson", 0.8),
        ],
    )
    def test_partial_similarity_high_scores(
        self, str1: str, str2: str, expected_min: float
    ) -> None:
        """Test cases that should have high partial similarity."""
        score = partial_similarity(str1, str2)
        assert score >= expected_min
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize(
        "str1, str2",
        [
            ("", "Anna"),
            ("Anna", ""),
            (None, "Anna"),  # type: ignore
            ("Anna", None),  # type: ignore
        ],
    )
    def test_partial_similarity_empty_cases(self, str1: str | None, str2: str | None) -> None:
        """Test empty and None string handling."""
        score = partial_similarity(str1, str2)  # type: ignore
        assert score == 0.0

    def test_partial_similarity_symmetric(self) -> None:
        """Test that partial similarity is symmetric."""
        str1, str2 = "Anna", "Anna Andersson"
        score1 = partial_similarity(str1, str2)
        score2 = partial_similarity(str2, str1)
        assert score1 == score2


class TestExactMatch:
    """Tests for the exact_match function."""

    @pytest.mark.parametrize(
        "str1, str2, case_sensitive, expected",
        [
            # Case insensitive (default)
            ("Anna", "anna", False, True),
            ("ANNA", "anna", False, True),
            ("Anna Andersson", "ANNA ANDERSSON", False, True),
            # Case sensitive
            ("Anna", "anna", True, False),
            ("Anna", "Anna", True, True),
            ("ANNA", "ANNA", True, True),
            # Different strings
            ("Anna", "Erik", False, False),
            ("Anna", "Erik", True, False),
            # Whitespace sensitivity
            ("Anna", " Anna ", False, False),
            ("Anna Andersson", "Anna  Andersson", False, False),
        ],
    )
    def test_exact_match_cases(
        self, str1: str, str2: str, case_sensitive: bool, expected: bool
    ) -> None:
        """Test exact match with various case sensitivity settings."""
        result = exact_match(str1, str2, case_sensitive=case_sensitive)
        assert result == expected

    def test_exact_match_swedish_characters(self) -> None:
        """Test exact matching with Swedish characters."""
        assert exact_match("Björn", "björn", case_sensitive=False) is True
        assert exact_match("Björn", "Bjorn", case_sensitive=False) is False
        assert exact_match("Åsa", "åsa", case_sensitive=False) is True


class TestLevenshteinDistance:
    """Tests for the levenshtein_distance function."""

    @pytest.mark.parametrize(
        "str1, str2, expected_distance",
        [
            # Identical strings
            ("Anna", "Anna", 0),
            ("", "", 0),
            # Single character differences
            ("Anna", "Anne", 1),
            ("Erik", "Eric", 1),
            # Multiple differences
            ("Anna", "Erik", 4),
            ("Andersson", "Anderson", 1),
            # Swedish name variations
            ("Björn", "Bjorn", 1),  # ö -> o
            ("Åsa", "Asa", 1),  # å -> a
        ],
    )
    def test_levenshtein_distance_expected_values(
        self, str1: str, str2: str, expected_distance: int
    ) -> None:
        """Test Levenshtein distance calculation."""
        distance = levenshtein_distance(str1, str2)
        assert distance == expected_distance
        assert distance >= 0

    def test_levenshtein_distance_symmetric(self) -> None:
        """Test that Levenshtein distance is symmetric."""
        str1, str2 = "Anna", "Erik"
        distance1 = levenshtein_distance(str1, str2)
        distance2 = levenshtein_distance(str2, str1)
        assert distance1 == distance2


class TestSimilarityWithThreshold:
    """Tests for the similarity_with_threshold function."""

    @pytest.mark.parametrize(
        "str1, str2, threshold, algorithm, expected_meets_threshold",
        [
            # High similarity should meet threshold
            ("Anna Andersson", "Anna Andersson", 0.8, "token_sort", True),
            ("Anna Andersson", "Andersson Anna", 0.8, "token_sort", True),
            # Low similarity should not meet threshold
            ("Anna", "Erik", 0.8, "token_sort", False),
            ("Andersson", "Johnson", 0.8, "token_sort", False),
            # Test different algorithms
            ("Anna", "Anna Andersson", 0.8, "partial", True),
            ("Anna", "Anna Andersson", 0.8, "ratio", False),
        ],
    )
    def test_similarity_with_threshold_meets_threshold(
        self,
        str1: str,
        str2: str,
        threshold: float,
        algorithm: str,
        expected_meets_threshold: bool,
    ) -> None:
        """Test threshold checking with different algorithms."""
        meets_threshold, score = similarity_with_threshold(str1, str2, threshold, algorithm)
        assert meets_threshold == expected_meets_threshold
        assert 0.0 <= score <= 1.0

    def test_similarity_with_threshold_invalid_algorithm(self) -> None:
        """Test error handling for invalid algorithm."""
        with pytest.raises(ValueError, match="Unknown algorithm: invalid"):
            similarity_with_threshold("Anna", "Erik", 0.8, "invalid")

    @pytest.mark.parametrize(
        "str1, str2",
        [
            ("", "Anna"),
            ("Anna", ""),
            (None, "Anna"),  # type: ignore
            ("Anna", None),  # type: ignore
        ],
    )
    def test_similarity_with_threshold_empty_strings(
        self, str1: str | None, str2: str | None
    ) -> None:
        """Test empty string handling."""
        meets_threshold, score = similarity_with_threshold(str1, str2, 0.5)  # type: ignore
        assert meets_threshold is False
        assert score == 0.0


class TestBestMatchFromList:
    """Tests for the best_match_from_list function."""

    def test_best_match_from_list_finds_best(self) -> None:
        """Test finding the best match from a list."""
        target = "Anna Andersson"
        candidates = ["Erik Johansson", "Anna Andersen", "Björn Nilsson", "Anna Andersson"]

        best_match, score = best_match_from_list(target, candidates, threshold=0.0)

        assert best_match == "Anna Andersson"
        assert score == 1.0

    def test_best_match_from_list_with_threshold(self) -> None:
        """Test threshold filtering in best match."""
        target = "Anna"
        candidates = ["Erik", "Björn", "Carl"]  # All low similarity

        best_match, score = best_match_from_list(target, candidates, threshold=0.8)

        assert best_match is None
        assert score == 0.0

    def test_best_match_from_list_swedish_names(self) -> None:
        """Test with realistic Swedish name matching."""
        target = "Anna Svensson"
        candidates = [
            "Erik Johansson",
            "Anna Svenson",  # Close match
            "Björn Andersson",
            "Anna Nilsson",
        ]

        best_match, score = best_match_from_list(target, candidates, threshold=0.7)

        assert best_match == "Anna Svenson"
        assert score > 0.7

    @pytest.mark.parametrize(
        "target, candidates, expected_match, expected_score",
        [
            # Empty inputs
            ("", ["Anna", "Erik"], None, 0.0),
            ("Anna", [], None, 0.0),
            (None, ["Anna", "Erik"], None, 0.0),  # type: ignore
            # No candidates above threshold
            (
                "Anna",
                ["Erik", "Björn"],
                None,
                0.0,
            ),  # With default threshold 0.0, this should find a match
        ],
    )
    def test_best_match_from_list_edge_cases(
        self,
        target: str | None,
        candidates: list[str],
        expected_match: str | None,
        expected_score: float,
    ) -> None:
        """Test edge cases and empty inputs."""
        if target is None:
            best_match, score = best_match_from_list(target, candidates, threshold=0.5)  # type: ignore
        else:
            best_match, score = best_match_from_list(target, candidates, threshold=0.5)

        if expected_match is None:
            assert best_match is None
        else:
            assert best_match == expected_match
        assert score == expected_score
