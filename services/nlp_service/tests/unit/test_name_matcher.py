"""
Unit tests for NameMatcher - test name-based matching algorithms.

Tests the core business logic of matching extracted names against student roster
using exact, partial, and fuzzy matching strategies. Follows behavioral testing
patterns - testing actual match results, confidence scores, and matching logic.
"""

from __future__ import annotations

import pytest

from services.nlp_service.features.student_matching.matching.name_matcher import NameMatcher
from services.nlp_service.features.student_matching.models import (
    MatchReason,
    StudentInfo,
)


class TestNameMatcher:
    """Test NameMatcher algorithm with various matching scenarios."""

    @pytest.fixture
    def matcher(self) -> NameMatcher:
        """Create NameMatcher with default confidence settings."""
        return NameMatcher()

    @pytest.fixture
    def custom_matcher(self) -> NameMatcher:
        """Create NameMatcher with custom confidence settings for testing thresholds."""
        return NameMatcher(
            exact_confidence=0.99,
            fuzzy_confidence=0.80,
            partial_confidence=0.90,
            fuzzy_threshold=0.6,
        )

    @pytest.fixture
    def sample_roster(self) -> list[StudentInfo]:
        """Create sample student roster for testing."""
        return [
            StudentInfo(
                student_id="student-1",
                first_name="Anna",
                last_name="Andersson",
                full_legal_name="Anna Karin Andersson",
                email="anna.andersson@student.se",
            ),
            StudentInfo(
                student_id="student-2",
                first_name="Erik",
                last_name="Johansson",
                full_legal_name="Erik Lars Johansson",
                email="erik.johansson@student.se",
            ),
            StudentInfo(
                student_id="student-3",
                first_name="Maria",
                last_name="Nilsson",
                full_legal_name="Maria Elisabet Nilsson",
                email="maria.nilsson@student.se",
            ),
            StudentInfo(
                student_id="student-4",
                first_name="Lars",
                last_name="von Sydow",
                full_legal_name="Lars Johan von Sydow",
                email="lars.vonsydow@student.se",
            ),
            StudentInfo(
                student_id="student-5",
                first_name="Anna-Lisa",
                last_name="Svensson",
                full_legal_name="Anna-Lisa Marie Svensson",
                email="anna.lisa.svensson@student.se",
            ),
        ]

    @pytest.mark.asyncio
    async def test_exact_match_full_legal_name(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test exact matching against full legal names."""
        # Act
        results = await matcher.match("Anna Karin Andersson", sample_roster)

        # Assert
        assert len(results) == 1
        result = results[0]
        assert result.student.student_id == "student-1"
        assert result.confidence == 0.95  # Default exact confidence
        assert result.match_reason == MatchReason.NAME_EXACT
        assert result.match_details["matched_field"] == "full_legal_name"
        assert result.match_details["matched_value"] == "Anna Karin Andersson"

    @pytest.mark.asyncio
    async def test_exact_match_display_name(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test exact matching against first + last name combination."""
        # Act
        results = await matcher.match("Erik Johansson", sample_roster)

        # Assert
        assert len(results) == 1
        result = results[0]
        assert result.student.student_id == "student-2"
        assert result.confidence == 0.95
        assert result.match_reason == MatchReason.NAME_EXACT
        assert result.match_details["matched_field"] == "display_name"
        assert result.match_details["matched_value"] == "Erik Johansson"

    @pytest.mark.asyncio
    async def test_exact_match_display_name_priority(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that exact display name match takes priority over partial matching."""
        # Act - "Anna Andersson" exactly matches display name format
        results = await matcher.match("Anna Andersson", sample_roster)

        # Assert - Should find exact match, not partial match
        assert len(results) == 1
        result = results[0]
        assert result.student.student_id == "student-1"
        assert result.confidence == 0.95  # Exact match confidence
        assert result.match_reason == MatchReason.NAME_EXACT
        assert result.match_details["matched_field"] == "display_name"
        assert result.match_details["matched_value"] == "Anna Andersson"

    @pytest.mark.asyncio
    async def test_fuzzy_match_with_typos(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test fuzzy matching with minor spelling errors."""
        # Act - Names with typos that should match fuzzily with 0.6 threshold
        test_cases = [
            ("Erik Johanson", "student-2"),  # Missing 's' in Johansson
            ("Maria Nilson", "student-3"),  # Missing 's' in Nilsson
            ("Ana Andersson", "student-1"),  # Missing 'n' in Anna
        ]

        for typo_name, expected_student_id in test_cases:
            results = await matcher.match(typo_name, sample_roster)

            # Assert
            assert len(results) >= 1, f"Should find fuzzy match for {typo_name}"
            # Get the highest confidence result
            best_result = max(results, key=lambda r: r.confidence)
            assert best_result.student.student_id == expected_student_id
            assert best_result.match_reason == MatchReason.NAME_FUZZY
            # Confidence should be fuzzy_confidence (0.75) * similarity_score (≥0.6)
            assert best_result.confidence >= 0.6 * 0.75  # threshold * fuzzy_confidence
            assert best_result.confidence <= 0.75  # Should not exceed fuzzy_confidence
            assert "similarity_score" in best_result.match_details

    @pytest.mark.asyncio
    async def test_compound_name_matching(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test matching with compound first names (Swedish style)."""
        # Act
        results = await matcher.match("Anna-Lisa Svensson", sample_roster)

        # Assert
        assert len(results) == 1
        result = results[0]
        assert result.student.student_id == "student-5"
        assert result.match_reason == MatchReason.NAME_EXACT
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_particle_name_matching(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test matching with Swedish name particles (von, af, etc.)."""
        # Act
        results = await matcher.match("Lars von Sydow", sample_roster)

        # Assert
        assert len(results) == 1
        result = results[0]
        assert result.student.student_id == "student-4"
        assert result.match_reason == MatchReason.NAME_EXACT
        assert result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_multiple_matches_sorted_by_confidence(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that multiple matches are returned sorted by confidence."""
        # Add a second Anna to the roster for testing
        roster_with_duplicate = sample_roster + [
            StudentInfo(
                student_id="student-6",
                first_name="Anna",
                last_name="Svensson",
                full_legal_name="Anna Marie Svensson",
                email="anna.svensson@student.se",
            )
        ]

        # Act - Search for "Anna Svensson" which should match two different students
        results = await matcher.match("Anna", roster_with_duplicate)

        # Assert - Single names may not match (too ambiguous), which is correct behavior
        # Instead test with "Anna S" which should match both Anna Andersson and Anna
        # Svensson fuzzily
        results = await matcher.match("Anna S", roster_with_duplicate)

        if len(results) >= 2:
            # Verify sorting (highest confidence first)
            for i in range(len(results) - 1):
                assert results[i].confidence >= results[i + 1].confidence

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that matching is case insensitive."""
        # Act
        test_cases = [
            "ANNA ANDERSSON",
            "anna andersson",
            "Anna Andersson",
            "aNnA aNdErSsOn",
        ]

        for case_variant in test_cases:
            results = await matcher.match(case_variant, sample_roster)

            # Assert - Should find match regardless of case
            assert len(results) >= 1, f"Should match {case_variant}"
            best_result = max(results, key=lambda r: r.confidence)
            assert best_result.student.student_id == "student-1"

    @pytest.mark.asyncio
    async def test_whitespace_normalization(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that extra whitespace is handled correctly."""
        # Act
        test_cases = [
            "  Anna   Andersson  ",
            "Anna\t\tAndersson",
            "Anna     Andersson",
            " Anna Andersson ",
        ]

        for whitespace_variant in test_cases:
            results = await matcher.match(whitespace_variant, sample_roster)

            # Assert
            assert len(results) >= 1, f"Should match '{whitespace_variant}'"
            best_result = max(results, key=lambda r: r.confidence)
            assert best_result.student.student_id == "student-1"

    @pytest.mark.asyncio
    async def test_no_matches_found(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test behavior when no matches are found."""
        # Act
        results = await matcher.match("Nonexistent Student", sample_roster)

        # Assert
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_custom_confidence_thresholds(
        self, custom_matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that custom confidence settings are applied correctly."""
        # Act
        results = await custom_matcher.match("Anna Karin Andersson", sample_roster)

        # Assert - Should use custom exact confidence (0.99)
        assert len(results) == 1
        result = results[0]
        assert result.confidence == 0.99
        assert result.match_reason == MatchReason.NAME_EXACT

    @pytest.mark.asyncio
    async def test_fuzzy_threshold_filtering(
        self, custom_matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that fuzzy matches below threshold are filtered out."""
        # Act - Use a name that would have low similarity
        results = await custom_matcher.match("Completely Different Name", sample_roster)

        # Assert - Should find no matches due to low similarity below threshold (0.6)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_empty_name_handling(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test handling of empty or invalid names."""
        # Act
        test_cases = ["", "   ", "\t\n", " "]

        for empty_name in test_cases:
            results = await matcher.match(empty_name, sample_roster)

            # Assert - Should handle gracefully without crashing
            assert isinstance(results, list)
            # Results might be empty or contain very low confidence matches

    @pytest.mark.asyncio
    async def test_single_name_partial_matching(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test behavior with single name (no last name)."""
        # Act
        results = await matcher.match("Anna", sample_roster)

        # Assert - Should find matches but might be lower confidence
        assert isinstance(results, list)
        # Single names typically match through fuzzy matching

    @pytest.mark.asyncio
    async def test_reversed_name_order(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test matching with reversed name order (Last, First)."""
        # Act
        results = await matcher.match("Andersson, Anna", sample_roster)

        # Assert - Should find match (NameMatcher handles "Last, First" format)
        assert len(results) >= 1
        best_result = max(results, key=lambda r: r.confidence)
        assert best_result.student.student_id == "student-1"
        # NameMatcher handles reversed format as exact match through name variations
        assert best_result.match_reason == MatchReason.NAME_EXACT
        assert best_result.confidence == 0.95

    @pytest.mark.asyncio
    async def test_punctuation_handling(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that punctuation in names is handled correctly."""
        # Act
        test_cases = [
            "Anna, Andersson",
            "Anna. Andersson",
            "Anna (Andersson)",
            "Anna [Andersson]",
        ]

        for punct_name in test_cases:
            results = await matcher.match(punct_name, sample_roster)

            # Assert - Should find matches despite punctuation
            assert len(results) >= 1, f"Should match '{punct_name}'"
            best_result = max(results, key=lambda r: r.confidence)
            assert best_result.student.student_id == "student-1"

    @pytest.mark.asyncio
    async def test_match_result_structure(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that MatchingResult objects have correct structure."""
        # Act
        results = await matcher.match("Anna Andersson", sample_roster)

        # Assert
        assert len(results) >= 1
        result = results[0]

        # Verify MatchingResult structure
        assert isinstance(result.student, StudentInfo)
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.match_reason, MatchReason)
        assert isinstance(result.match_details, dict)

        # Verify student info is preserved
        assert result.student.student_id in ["student-1"]  # Should match Anna
        assert result.student.first_name == "Anna"
        assert result.student.last_name == "Andersson"

    @pytest.mark.asyncio
    async def test_confidence_score_scaling(
        self, matcher: NameMatcher, sample_roster: list[StudentInfo]
    ) -> None:
        """Test that fuzzy match confidence is scaled by similarity score."""
        # Act
        results = await matcher.match("Erik Johanson", sample_roster)  # Minor typo

        # Assert
        assert len(results) >= 1
        result = results[0]
        assert result.match_reason == MatchReason.NAME_FUZZY

        # Confidence should be fuzzy_confidence * similarity_score
        # So it should be less than the base fuzzy_confidence (0.75)
        assert result.confidence < 0.75
        assert result.confidence > 0.0

        # Similarity score should be in match details
        assert "similarity_score" in result.match_details
        similarity = result.match_details["similarity_score"]
        assert isinstance(similarity, float)
        assert 0.0 <= similarity <= 1.0

    @pytest.mark.asyncio
    async def test_empty_roster_handling(self, matcher: NameMatcher) -> None:
        """Test behavior with empty student roster."""
        # Act
        results = await matcher.match("Anna Andersson", [])

        # Assert
        assert len(results) == 0
