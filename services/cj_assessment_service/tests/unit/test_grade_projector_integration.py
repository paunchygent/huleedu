"""Integration test for grade projector with realistic data.

This module contains an integration test using realistic Bradley-Terry scores
that simulate actual output from the Choix algorithm in a CJ assessment session.
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


class TestGradeProjectorIntegration:
    """Integration test for grade projector with realistic choix output."""

    @pytest.mark.asyncio
    async def test_integration_with_realistic_choix_output(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Any,
    ) -> None:
        """Integration test with realistic Bradley-Terry scores from Choix algorithm.

        This test simulates a realistic CJ session with 10 essays (3 anchors, 7 students)
        using values that would come from choix.ilsr_pairwise in production.
        """
        # Arrange
        grade_projector = create_test_projector()
        correlation_id = uuid4()

        # Realistic rankings from a CJ session with 10 essays (3 anchors, 7 students)
        # These values simulate output from choix.ilsr_pairwise
        rankings = [
            # Top performing student essays
            {
                "els_essay_id": "student_top1",
                "bradley_terry_score": 0.923,
                "bradley_terry_se": 0.045,
                "rank": 1,
                "comparison_count": 15,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_top2",
                "bradley_terry_score": 0.876,
                "bradley_terry_se": 0.052,
                "rank": 2,
                "comparison_count": 14,
                "is_anchor": False,
            },
            # High-performing anchor (Grade A)
            {
                "els_essay_id": "anchor_a",
                "bradley_terry_score": 0.845,
                "bradley_terry_se": 0.038,
                "rank": 3,
                "comparison_count": 18,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            # Mid-range student essays
            {
                "els_essay_id": "student_mid1",
                "bradley_terry_score": 0.612,
                "bradley_terry_se": 0.067,
                "rank": 4,
                "comparison_count": 12,
                "is_anchor": False,
            },
            # Mid-performing anchor (Grade B)
            {
                "els_essay_id": "anchor_b",
                "bradley_terry_score": 0.543,
                "bradley_terry_se": 0.041,
                "rank": 5,
                "comparison_count": 16,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "student_mid2",
                "bradley_terry_score": 0.487,
                "bradley_terry_se": 0.073,
                "rank": 6,
                "comparison_count": 11,
                "is_anchor": False,
            },
            # Low-performing anchor (Grade C)
            {
                "els_essay_id": "anchor_c",
                "bradley_terry_score": 0.312,
                "bradley_terry_se": 0.055,
                "rank": 7,
                "comparison_count": 14,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            # Lower performing student essays
            {
                "els_essay_id": "student_low1",
                "bradley_terry_score": 0.245,
                "bradley_terry_se": 0.082,
                "rank": 8,
                "comparison_count": 10,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_low2",
                "bradley_terry_score": 0.134,
                "bradley_terry_se": 0.095,
                "rank": 9,
                "comparison_count": 9,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_bottom",
                "bradley_terry_score": 0.078,
                "bradley_terry_se": 0.112,
                "rank": 10,
                "comparison_count": 8,
                "is_anchor": False,
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

            # Assert - Comprehensive validation of statistical features
            assert result.projections_available is True

            # All student essays should have projections
            student_essay_ids: set[str] = {
                str(r["els_essay_id"]) for r in rankings if not r.get("is_anchor")
            }
            assert len(result.primary_grades) == len(student_essay_ids)

            # Essays scoring above the A anchor (0.845) should likely get A or A-
            assert result.primary_grades["student_top1"] in {"A", "A-", "B", "B+"}  # 0.923 > 0.845
            assert result.primary_grades["student_top2"] in {"A", "A-", "B", "B+"}  # 0.876 > 0.845

            # Essays scoring between B (0.543) and A (0.845) anchors
            assert result.primary_grades["student_mid1"] in {
                "A",
                "A-",
                "B",
                "B+",
                "B-",
                "C+",
                "C",
            }  # 0.612

            # Essays scoring around B anchor (0.543)
            assert result.primary_grades["student_mid2"] in {
                "B",
                "B+",
                "B-",
                "C+",
                "C",
                "C-",
            }  # 0.487

            # Essays scoring below C anchor (0.312)
            assert result.primary_grades["student_low1"] in {
                "C",
                "C-",
                "D+",
                "D",
                "D-",
                "E",
                "E+",
                "E-",
                "F",
            }  # 0.245
            assert result.primary_grades["student_low2"] in {
                "D+",
                "D",
                "D-",
                "E",
                "E+",
                "E-",
                "F",
            }  # 0.134
            assert result.primary_grades["student_bottom"] in {
                "D",
                "D-",
                "E",
                "E+",
                "E-",
                "F",
            }  # 0.078

            # Verify all probability distributions sum to 1
            for essay_id in student_essay_ids:
                if essay_id in result.grade_probabilities:
                    probs = result.grade_probabilities[essay_id]
                    total = sum(probs.values())
                    assert 0.999 <= total <= 1.001

            # Verify calibration info is complete
            assert result.calibration_info is not None
            assert "grade_centers" in result.calibration_info
            assert "grade_boundaries" in result.calibration_info
            assert result.calibration_info["anchor_count"] == 3

            # Verify all BT stats are captured
            for essay_id in student_essay_ids:
                assert essay_id in result.bt_stats
                stats = result.bt_stats[essay_id]
                assert "bt_mean" in stats
                assert "bt_se" in stats

                # Find the original SE from rankings
                original = next(r for r in rankings if r["els_essay_id"] == essay_id)
                assert stats["bt_se"] == original["bradley_terry_se"]
                assert stats["bt_mean"] == original["bradley_terry_score"]

            # Essays with more comparisons should have lower SE (generally)
            high_comp_essay = "student_top1"  # 15 comparisons
            low_comp_essay = "student_bottom"  # 8 comparisons
            assert (
                result.bt_stats[high_comp_essay]["bt_se"] < result.bt_stats[low_comp_essay]["bt_se"]
            )
