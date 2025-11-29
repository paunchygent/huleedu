"""Tests for grade projector fallback behavior.

This module tests fallback and error handling in the grade projection system:
- Fallback behavior without anchors
- Error resilience with invalid anchor data
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from services.cj_assessment_service.tests.unit.test_helpers.grade_projector_fixtures import (
    create_test_projector,
)

# Explicit fixture registration per rule 075
pytest_plugins = ["services.cj_assessment_service.tests.unit.test_helpers.grade_projector_fixtures"]


class TestGradeProjectorFallback:
    """Tests for grade projector fallback and error handling."""

    @pytest.mark.asyncio
    async def test_fallback_behavior_without_anchors(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_empty_context: AsyncMock,
    ) -> None:
        """Test that system returns projections_available=False when no anchor essays exist.

        Behavioral expectation: Without anchors, the system cannot perform
        calibration and should gracefully return an empty result.
        """
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        # Rankings without any anchors flagged
        sample_rankings = [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.85,
                "bradley_terry_se": 0.05,
                "rank": 1,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_2",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.07,
                "rank": 2,
                "is_anchor": False,
            },
        ]

        # Mock context builder to return NO anchors
        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_empty_context

            # Act
            result = await grade_projector.calculate_projections(
                rankings=sample_rankings,
                cj_batch_id=1,
                assignment_id="assignment_789",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert - Without anchors, no projections available
            assert result.projections_available is False
            assert len(result.primary_grades) == 0
            assert len(result.confidence_labels) == 0
            assert len(result.confidence_scores) == 0
            assert len(result.grade_probabilities) == 0
            assert len(result.bt_stats) == 0

    @pytest.mark.asyncio
    async def test_error_resilience_with_invalid_anchor_data(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that system handles anchor retrieval errors gracefully.

        Behavioral expectation: If context building fails (e.g., content service
        unavailable), the error should propagate (not be silently swallowed).
        """
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        sample_rankings = [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.75,
                "bradley_terry_se": 0.06,
                "rank": 1,
                "is_anchor": False,
            },
        ]

        # Mock context builder to fail
        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.side_effect = Exception("Content service unavailable")

            # Act & Assert - Should propagate error (not silently fail)
            with pytest.raises(Exception, match="Content service unavailable"):
                await grade_projector.calculate_projections(
                    rankings=sample_rankings,
                    cj_batch_id=1,
                    assignment_id="assignment_789",
                    course_code="ENG5",
                    content_client=mock_content_client,
                    correlation_id=correlation_id,
                )
