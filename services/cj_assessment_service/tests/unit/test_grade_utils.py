"""Tests for grade utility functions.

This module tests pure utility functions for grade transformations.
"""

from __future__ import annotations

import pytest

from services.cj_assessment_service.cj_core_logic.grade_utils import _grade_to_normalized


class TestGradeUtils:
    """Tests for grade utility functions."""

    @pytest.mark.parametrize(
        "grade, expected_score",
        [
            # Standard letter grades
            ("A", 1.0),
            ("B", 0.8),
            ("C", 0.6),
            ("D", 0.4),
            ("E", 0.2),
            ("F", 0.0),
            # Alternative fail grade
            ("U", 0.0),
            # None/missing grade
            (None, 0.0),
        ],
    )
    def test_normalized_score_transformation_ranges(
        self,
        grade: str | None,
        expected_score: float,
    ) -> None:
        """Test that grade-to-normalized transformation produces valid 0.0-1.0 range.

        All normalized scores must be in valid range [0.0, 1.0] and match
        expected mappings for Swedish grading system.
        """
        # Act
        normalized_score = _grade_to_normalized(grade)

        # Assert - All normalized scores must be in valid range
        assert 0.0 <= normalized_score <= 1.0
        assert normalized_score == expected_score
