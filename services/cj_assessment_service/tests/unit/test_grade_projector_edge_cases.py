"""Tests for grade projector edge cases.

This module tests edge case handling in the grade projection system:
- Empty rankings handling
- Single anchor handling
- Anchors without grade metadata
- Extreme Bradley-Terry scores
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from services.cj_assessment_service.tests.unit.test_helpers.grade_projector_fixtures import (
    create_test_projector,
)

# Explicit fixture registration per rule 075
pytest_plugins = ["services.cj_assessment_service.tests.unit.test_helpers.grade_projector_fixtures"]


class TestGradeProjectorEdgeCases:
    """Tests for grade projector edge case handling."""

    @pytest.mark.asyncio
    async def test_empty_rankings_handling(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that empty rankings list produces valid empty projections.

        Behavioral expectation: Empty rankings should return projections_available=False
        with all result fields empty.
        """
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        # Act
        result = await grade_projector.calculate_projections(
            rankings=[],  # Empty rankings
            cj_batch_id=1,
            assignment_id="assignment_789",
            course_code="ENG5",
            content_client=mock_content_client,
            correlation_id=correlation_id,
        )

        # Assert - Empty rankings should return projections_available=False
        assert result.projections_available is False
        assert len(result.primary_grades) == 0
        assert len(result.confidence_labels) == 0
        assert len(result.confidence_scores) == 0
        assert len(result.grade_probabilities) == 0
        assert len(result.bt_stats) == 0
        assert len(result.calibration_info) == 0

    @pytest.mark.asyncio
    async def test_single_anchor_handling(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
    ) -> None:
        """Test that system handles single anchor gracefully.

        Behavioral expectation: Single anchor is insufficient for calibration
        (need at least 2 distinct grades for grade boundaries).
        """
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        rankings = [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.05,
                "rank": 1,
                "is_anchor": False,
            },
            {
                "els_essay_id": "anchor_1",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.03,
                "rank": 2,
                "is_anchor": True,
                "anchor_grade": "B",
            },
        ]

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                rankings=rankings,
                cj_batch_id=1,
                assignment_id="assignment_789",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert - Single anchor insufficient for calibration
            assert result.projections_available is False
            assert len(result.primary_grades) == 0

    @pytest.mark.asyncio
    async def test_extreme_bt_scores_handling(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
    ) -> None:
        """Test handling of extreme Bradley-Terry scores (near 0 or 1).

        Behavioral expectation: System should handle extreme scores gracefully
        and still produce valid grade assignments within allowed grade set.
        """
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        rankings = [
            # Extreme scores
            {
                "els_essay_id": "very_high",
                "bradley_terry_score": 0.999,
                "bradley_terry_se": 0.01,
                "rank": 1,
                "is_anchor": False,
            },
            {
                "els_essay_id": "very_low",
                "bradley_terry_score": 0.001,
                "bradley_terry_se": 0.01,
                "rank": 2,
                "is_anchor": False,
            },
            # Anchors for calibration
            {
                "els_essay_id": "anchor_a",
                "bradley_terry_score": 0.80,
                "bradley_terry_se": 0.03,
                "rank": 3,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_c",
                "bradley_terry_score": 0.20,
                "bradley_terry_se": 0.04,
                "rank": 4,
                "is_anchor": True,
                "anchor_grade": "C",
            },
        ]

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                rankings=rankings,
                cj_batch_id=1,
                assignment_id="assignment_789",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True

            # Check extreme scores still produce valid grades
            assert "very_high" in result.primary_grades
            assert "very_low" in result.primary_grades
            # Validate against Swedish grade system
            valid_grades = {
                "F",
                "E-",
                "E",
                "E+",
                "D-",
                "D",
                "D+",
                "C-",
                "C",
                "C+",
                "B-",
                "B",
                "B+",
                "A-",
                "A",
            }
            assert result.primary_grades["very_high"] in valid_grades
            assert result.primary_grades["very_low"] in valid_grades

    @pytest.mark.asyncio
    async def test_anchors_without_grades(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
    ) -> None:
        """Test that anchors missing grade metadata are handled gracefully.

        Behavioral expectation: Anchors without resolvable grades cannot be used
        for calibration, leading to projections_available=False.
        """
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        # Rankings with anchors missing grade information
        sample_rankings = [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.05,
                "rank": 1,
                "is_anchor": False,
            },
            {
                "els_essay_id": "anchor_1",
                "bradley_terry_score": 0.85,
                "bradley_terry_se": 0.03,
                "rank": 2,
                "is_anchor": True,
                # Missing anchor_grade field
            },
        ]

        # Mock context builder
        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                rankings=sample_rankings,
                cj_batch_id=1,
                assignment_id="assignment_789",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert - Anchors without grades cannot be used for calibration
            assert result.projections_available is False
            assert len(result.primary_grades) == 0
