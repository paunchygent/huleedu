"""Tests for grade projector calibration logic.

This module tests the statistical calibration aspects of the grade projection system:
- Calibration from anchor essays with known grades
- Grade diversity requirements
- Boundary monotonicity validation
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


class TestGradeProjectorCalibration:
    """Tests for grade projector statistical calibration."""

    @pytest.mark.asyncio
    async def test_statistical_calibration_with_anchors(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test statistical calibration produces valid grade probabilities and confidence scores."""
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        # Mock the context builder to return anchors
        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                rankings=sample_rankings_with_anchors,
                cj_batch_id=1,
                assignment_id="assignment_789",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert - Behavioral outcomes with new statistical features
            assert result.projections_available is True

            # Only student essays should have projections (anchors are used for calibration)
            student_essay_ids = {
                r["els_essay_id"] for r in sample_rankings_with_anchors if not r.get("is_anchor")
            }
            assert set(result.primary_grades.keys()) == student_essay_ids
            assert set(result.confidence_scores.keys()) == student_essay_ids
            assert set(result.confidence_labels.keys()) == student_essay_ids

            # All confidence scores must be in valid range
            for confidence_score in result.confidence_scores.values():
                assert 0.0 <= confidence_score <= 1.0

            # All confidence labels must be valid categories
            valid_confidence_labels = {"HIGH", "MID", "LOW"}
            for confidence_label in result.confidence_labels.values():
                assert confidence_label in valid_confidence_labels

            # All grades must be valid Swedish grades (8 anchor + 5 minus + 2 plus = 15 grades)
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
            for grade in result.primary_grades.values():
                assert grade in valid_grades

            # Check new statistical features
            assert "grade_probabilities" in result.model_dump()
            assert "calibration_info" in result.model_dump()
            assert "bt_stats" in result.model_dump()

            # Verify grade probabilities exist and sum to 1
            for essay_id in student_essay_ids:
                if essay_id in result.grade_probabilities:
                    probs = result.grade_probabilities[essay_id]
                    assert isinstance(probs, dict)
                    # Probabilities should sum to approximately 1
                    total_prob = sum(probs.values())
                    assert 0.99 <= total_prob <= 1.01

            # Verify calibration info contains expected fields
            if result.calibration_info:
                assert "grade_centers" in result.calibration_info
                assert "grade_boundaries" in result.calibration_info
                assert "anchor_count" in result.calibration_info
                assert result.calibration_info["anchor_count"] == 3
                # PR-3: SE diagnostics summary should be exposed for observability
                assert "bt_se_summary" in result.calibration_info
                se_summary = result.calibration_info["bt_se_summary"]
                assert isinstance(se_summary, dict)
                assert "all" in se_summary
                assert "anchors" in se_summary
                assert "students" in se_summary

            # Verify BT stats contain mean and SE
            for essay_id in student_essay_ids:
                if essay_id in result.bt_stats:
                    stats = result.bt_stats[essay_id]
                    assert "bt_mean" in stats
                    assert "bt_se" in stats
                    assert stats["bt_se"] >= 0.0

    @pytest.mark.asyncio
    async def test_insufficient_grade_diversity(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
    ) -> None:
        """Test that system requires sufficient grade diversity in anchors for calibration."""
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        # Rankings with anchors all having the same grade (insufficient diversity)
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
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_2",
                "bradley_terry_score": 0.80,
                "bradley_terry_se": 0.04,
                "rank": 3,
                "is_anchor": True,
                "anchor_grade": "A",  # Same grade - no diversity
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

            # Assert - Insufficient grade diversity should prevent projections
            assert result.projections_available is False
            assert len(result.primary_grades) == 0

    @pytest.mark.asyncio
    async def test_calibration_boundary_monotonicity(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test that grade boundaries are monotonically decreasing (A > B > C > D > F)."""
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                rankings=sample_rankings_with_anchors,
                cj_batch_id=1,
                assignment_id="assignment_789",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True
            assert result.calibration_info is not None

            if "grade_boundaries" in result.calibration_info:
                boundaries = result.calibration_info["grade_boundaries"]
                grade_order = ["A", "B", "C", "D", "F"]

                # Check monotonicity
                for i in range(len(grade_order) - 1):
                    grade_high = grade_order[i]
                    grade_low = grade_order[i + 1]
                    if grade_high in boundaries and grade_low in boundaries:
                        assert boundaries[grade_high] > boundaries[grade_low], (
                            f"Boundary for {grade_high} ({boundaries[grade_high]}) "
                            f"should be > {grade_low} ({boundaries[grade_low]})"
                        )
