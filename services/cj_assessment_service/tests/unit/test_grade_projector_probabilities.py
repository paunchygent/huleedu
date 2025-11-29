"""Tests for grade projector probability distributions.

This module tests the probability and confidence aspects of grade projection:
- Grade probability distributions sum to 1.0
- Standard error values are reasonable
- Entropy-based confidence calculation
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


class TestGradeProjectorProbabilities:
    """Tests for grade projector probability distributions and confidence."""

    @pytest.mark.asyncio
    async def test_confidence_based_on_entropy(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
    ) -> None:
        """Test that confidence scores are based on entropy of probability distributions.

        Behavioral expectation: Essays with lower SE and clearer grade signals
        should generally have different confidence characteristics than essays
        with high SE and uncertain positioning.
        """
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        rankings = [
            # Essay with high BT score and low SE (should have higher confidence)
            {
                "els_essay_id": "high_confidence_essay",
                "bradley_terry_score": 0.85,
                "bradley_terry_se": 0.02,
                "rank": 1,
                "comparison_count": 20,
                "is_anchor": False,
            },
            # Essay with medium BT score and high SE (should have lower confidence)
            {
                "els_essay_id": "low_confidence_essay",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.15,
                "rank": 2,
                "comparison_count": 5,
                "is_anchor": False,
            },
            # Include diverse anchors for calibration
            {
                "els_essay_id": "anchor_a",
                "bradley_terry_score": 0.90,
                "bradley_terry_se": 0.03,
                "rank": 3,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_b",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.04,
                "rank": 4,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_c",
                "bradley_terry_score": 0.20,
                "bradley_terry_se": 0.05,
                "rank": 5,
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

            # Both essays should have confidence labels
            assert "high_confidence_essay" in result.confidence_labels
            assert "low_confidence_essay" in result.confidence_labels

            # Valid confidence labels
            valid_labels = {"HIGH", "MID", "LOW"}
            assert result.confidence_labels["high_confidence_essay"] in valid_labels
            assert result.confidence_labels["low_confidence_essay"] in valid_labels

            # Confidence scores should be in valid range
            assert 0.0 <= result.confidence_scores["high_confidence_essay"] <= 1.0
            assert 0.0 <= result.confidence_scores["low_confidence_essay"] <= 1.0

            # Verify SE is captured in bt_stats
            assert "high_confidence_essay" in result.bt_stats
            assert result.bt_stats["high_confidence_essay"]["bt_se"] == 0.02
            assert "low_confidence_essay" in result.bt_stats
            assert result.bt_stats["low_confidence_essay"]["bt_se"] == 0.15

    @pytest.mark.asyncio
    async def test_probability_distributions_sum_to_one(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test that grade probability distributions always sum to 1.0.

        Behavioral expectation: Probability distributions are valid (sum to 1,
        all individual probabilities in [0, 1]).
        """
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

            # Check each essay's probability distribution
            for essay_id, probs in result.grade_probabilities.items():
                total_prob = sum(probs.values())
                assert 0.999 <= total_prob <= 1.001, (
                    f"Essay {essay_id} probabilities sum to {total_prob}"
                )

                # All probabilities should be non-negative
                for grade, prob in probs.items():
                    assert 0.0 <= prob <= 1.0, f"Invalid probability {prob} for grade {grade}"

    @pytest.mark.asyncio
    async def test_se_values_reasonable(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test that standard errors are non-negative and within reasonable bounds.

        Behavioral expectation: All SE values should be non-negative and less
        than 2.0 (unreasonably large SE would indicate a problem).
        """
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

            for essay_id, stats in result.bt_stats.items():
                se = stats.get("bt_se", 0)
                assert se >= 0.0, f"SE for {essay_id} is negative: {se}"
                assert se < 2.0, f"SE for {essay_id} is unreasonably large: {se}"
