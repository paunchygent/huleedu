"""Realistic tests for grade projector with comprehensive anchor coverage.

Tests the fine-grained 15-point grade scale with realistic anchor distributions
that reflect actual educational use cases.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.protocols import ContentClientProtocol


class TestRealisticGradeProjector:
    """Tests with realistic anchor distributions matching real educational scenarios."""

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create mock content client."""
        client = AsyncMock(spec=ContentClientProtocol)
        client.fetch_content = AsyncMock(return_value="Sample anchor essay content")
        client.store_content = AsyncMock(return_value={"content_id": "stored_123"})
        return client

    @pytest.fixture
    def mock_database_session(self) -> AsyncMock:
        """Create mock database session."""
        session = AsyncMock()
        session.add_all = Mock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.get = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def comprehensive_anchor_rankings(self) -> list[dict[str, Any]]:
        """Create rankings with comprehensive anchor coverage at strategic grades.

        This represents a realistic scenario where teachers provide anchors for:
        F+, E-, D-, D+, C-, C+, B-, B+, A-

        This gives good coverage across the spectrum with interpolation for
        the remaining grades (F, E, E+, D, C, B, A).
        """
        return [
            # Student essays to be graded
            {
                "els_essay_id": "student_top",
                "bradley_terry_score": 0.95,
                "bradley_terry_se": 0.03,
                "rank": 1,
                "comparison_count": 20,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_high",
                "bradley_terry_score": 0.82,
                "bradley_terry_se": 0.04,
                "rank": 3,
                "comparison_count": 18,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_mid_high",
                "bradley_terry_score": 0.68,
                "bradley_terry_se": 0.05,
                "rank": 5,
                "comparison_count": 15,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_mid",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.06,
                "rank": 7,
                "comparison_count": 12,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_mid_low",
                "bradley_terry_score": 0.35,
                "bradley_terry_se": 0.07,
                "rank": 9,
                "comparison_count": 10,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_low",
                "bradley_terry_score": 0.22,
                "bradley_terry_se": 0.08,
                "rank": 11,
                "comparison_count": 8,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_bottom",
                "bradley_terry_score": 0.08,
                "bradley_terry_se": 0.10,
                "rank": 13,
                "comparison_count": 6,
                "is_anchor": False,
            },
            # Comprehensive anchor essays
            {
                "els_essay_id": "anchor_a_minus",
                "bradley_terry_score": 0.88,
                "bradley_terry_se": 0.02,
                "rank": 2,
                "comparison_count": 25,
                "is_anchor": True,
                "anchor_grade": "A-",
            },
            {
                "els_essay_id": "anchor_b_plus",
                "bradley_terry_score": 0.75,
                "bradley_terry_se": 0.025,
                "rank": 4,
                "comparison_count": 23,
                "is_anchor": True,
                "anchor_grade": "B+",
            },
            {
                "els_essay_id": "anchor_b_minus",
                "bradley_terry_score": 0.62,
                "bradley_terry_se": 0.03,
                "rank": 6,
                "comparison_count": 21,
                "is_anchor": True,
                "anchor_grade": "B-",
            },
            {
                "els_essay_id": "anchor_c_plus",
                "bradley_terry_score": 0.55,
                "bradley_terry_se": 0.035,
                "rank": 8,
                "comparison_count": 19,
                "is_anchor": True,
                "anchor_grade": "C+",
            },
            {
                "els_essay_id": "anchor_c_minus",
                "bradley_terry_score": 0.42,
                "bradley_terry_se": 0.04,
                "rank": 10,
                "comparison_count": 17,
                "is_anchor": True,
                "anchor_grade": "C-",
            },
            {
                "els_essay_id": "anchor_d_plus",
                "bradley_terry_score": 0.30,
                "bradley_terry_se": 0.045,
                "rank": 12,
                "comparison_count": 15,
                "is_anchor": True,
                "anchor_grade": "D+",
            },
            {
                "els_essay_id": "anchor_d_minus",
                "bradley_terry_score": 0.18,
                "bradley_terry_se": 0.05,
                "rank": 14,
                "comparison_count": 13,
                "is_anchor": True,
                "anchor_grade": "D-",
            },
            {
                "els_essay_id": "anchor_e_minus",
                "bradley_terry_score": 0.12,
                "bradley_terry_se": 0.055,
                "rank": 15,
                "comparison_count": 11,
                "is_anchor": True,
                "anchor_grade": "E-",
            },
            {
                "els_essay_id": "anchor_f_plus",
                "bradley_terry_score": 0.05,
                "bradley_terry_se": 0.06,
                "rank": 16,
                "comparison_count": 9,
                "is_anchor": True,
                "anchor_grade": "F+",
            },
        ]

    @pytest.fixture
    def alternative_anchor_rankings(self) -> list[dict[str, Any]]:
        """Alternative realistic anchor distribution: E-, E, D, C-, C+, B, A.

        This represents a different but equally realistic scenario.
        """
        return [
            # Student essays
            {
                "els_essay_id": "student_excellent",
                "bradley_terry_score": 0.92,
                "bradley_terry_se": 0.03,
                "rank": 1,
                "comparison_count": 15,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_good",
                "bradley_terry_score": 0.70,
                "bradley_terry_se": 0.05,
                "rank": 3,
                "comparison_count": 12,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_average",
                "bradley_terry_score": 0.48,
                "bradley_terry_se": 0.06,
                "rank": 5,
                "comparison_count": 10,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_below_avg",
                "bradley_terry_score": 0.28,
                "bradley_terry_se": 0.08,
                "rank": 7,
                "comparison_count": 8,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_poor",
                "bradley_terry_score": 0.15,
                "bradley_terry_se": 0.09,
                "rank": 9,
                "comparison_count": 6,
                "is_anchor": False,
            },
            # Alternative anchor distribution
            {
                "els_essay_id": "anchor_a",
                "bradley_terry_score": 0.85,
                "bradley_terry_se": 0.025,
                "rank": 2,
                "comparison_count": 20,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_b",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.03,
                "rank": 4,
                "comparison_count": 18,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_c_plus",
                "bradley_terry_score": 0.52,
                "bradley_terry_se": 0.035,
                "rank": 6,
                "comparison_count": 16,
                "is_anchor": True,
                "anchor_grade": "C+",
            },
            {
                "els_essay_id": "anchor_c_minus",
                "bradley_terry_score": 0.38,
                "bradley_terry_se": 0.04,
                "rank": 8,
                "comparison_count": 14,
                "is_anchor": True,
                "anchor_grade": "C-",
            },
            {
                "els_essay_id": "anchor_d",
                "bradley_terry_score": 0.25,
                "bradley_terry_se": 0.045,
                "rank": 10,
                "comparison_count": 12,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_e",
                "bradley_terry_score": 0.18,
                "bradley_terry_se": 0.05,
                "rank": 11,
                "comparison_count": 10,
                "is_anchor": True,
                "anchor_grade": "E",
            },
            {
                "els_essay_id": "anchor_e_minus",
                "bradley_terry_score": 0.10,
                "bradley_terry_se": 0.055,
                "rank": 12,
                "comparison_count": 8,
                "is_anchor": True,
                "anchor_grade": "E-",
            },
        ]

    @pytest.mark.asyncio
    async def test_comprehensive_anchor_coverage(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        comprehensive_anchor_rankings: list[dict[str, Any]],
    ) -> None:
        """Test with comprehensive anchor coverage at strategic grades."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "comprehensive_anchors"
        mock_context.assessment_instructions = "Grade based on quality"
        mock_context.anchor_contents = {}

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
                rankings=comprehensive_anchor_rankings,
                cj_batch_id=1,
                assignment_id="comprehensive_test",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True

            # With comprehensive anchors, grade assignments should be very accurate

            # Student with 0.95 score (above A- at 0.88) should get A or A-
            assert result.primary_grades["student_top"] in {"A", "A-"}

            # Student with 0.82 score (between B+ at 0.75 and A- at 0.88)
            assert result.primary_grades["student_high"] in {"A-", "B+", "A"}

            # Student with 0.68 score (between B- at 0.62 and B+ at 0.75)
            assert result.primary_grades["student_mid_high"] in {"B", "B+", "B-"}

            # Student with 0.50 score (between C- at 0.42 and C+ at 0.55)
            assert result.primary_grades["student_mid"] in {"C", "C+", "C-"}

            # Student with 0.35 score (between D+ at 0.30 and C- at 0.42)
            assert result.primary_grades["student_mid_low"] in {"C-", "D+", "D"}

            # Student with 0.22 score (between D- at 0.18 and D+ at 0.30)
            assert result.primary_grades["student_low"] in {"D", "D+", "D-"}

            # Student with 0.08 score (between F+ at 0.05 and E- at 0.12)
            assert result.primary_grades["student_bottom"] in {"E-", "E", "F+", "F"}

            # Verify all probabilities sum to 1
            for essay_id, probs in result.grade_probabilities.items():
                total = sum(probs.values())
                assert 0.999 <= total <= 1.001

    @pytest.mark.asyncio
    async def test_alternative_anchor_distribution(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        alternative_anchor_rankings: list[dict[str, Any]],
    ) -> None:
        """Test with alternative realistic anchor distribution."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "alternative_anchors"
        mock_context.assessment_instructions = "Grade based on quality"
        mock_context.anchor_contents = {}

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
                rankings=alternative_anchor_rankings,
                cj_batch_id=1,
                assignment_id="alternative_test",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True

            # With anchors at A, B, C+, C-, D, E, E-

            # Student with 0.92 score (above A at 0.85)
            assert result.primary_grades["student_excellent"] in {"A", "A-"}

            # Student with 0.70 score (above B at 0.65)
            assert result.primary_grades["student_good"] in {"B+", "B", "A-"}

            # Student with 0.48 score (between C- at 0.38 and C+ at 0.52)
            assert result.primary_grades["student_average"] in {"C", "C+", "C-"}

            # Student with 0.28 score (between D at 0.25 and C- at 0.38)
            assert result.primary_grades["student_below_avg"] in {"D+", "D", "C-"}

            # Student with 0.15 score (between E- at 0.10 and E at 0.18)
            assert result.primary_grades["student_poor"] in {"E", "E-", "E+"}

    @pytest.mark.asyncio
    async def test_confidence_with_comprehensive_anchors(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        comprehensive_anchor_rankings: list[dict[str, Any]],
    ) -> None:
        """Test that comprehensive anchor coverage leads to higher confidence."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "comprehensive_confidence"
        mock_context.assessment_instructions = "Grade based on quality"
        mock_context.anchor_contents = {}

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
                rankings=comprehensive_anchor_rankings,
                cj_batch_id=1,
                assignment_id="confidence_test",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True

            # With comprehensive anchors, essays near anchors should have high confidence
            # Check that most essays have MID or HIGH confidence
            high_mid_count = sum(
                1 for label in result.confidence_labels.values() if label in {"HIGH", "MID"}
            )
            total_count = len(result.confidence_labels)

            # At least 70% should have MID or HIGH confidence with good anchor coverage
            assert high_mid_count / total_count >= 0.7

            # Verify calibration info shows all 9 anchors
            assert result.calibration_info["anchor_count"] == 9

    @pytest.mark.asyncio
    async def test_grade_distribution_statistics(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        comprehensive_anchor_rankings: list[dict[str, Any]],
    ) -> None:
        """Test that grade distributions follow expected statistical properties."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "statistics_test"
        mock_context.assessment_instructions = "Grade based on quality"
        mock_context.anchor_contents = {}

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
                rankings=comprehensive_anchor_rankings,
                cj_batch_id=1,
                assignment_id="statistics_test",
                course_code="ENG5",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True

            # Check that grade centers are monotonically increasing
            if result.calibration_info and "grade_centers" in result.calibration_info:
                centers = result.calibration_info["grade_centers"]
                grade_order = grade_projector.GRADE_ORDER_FINE

                prev_center = -float("inf")
                for grade in grade_order:
                    if grade in centers and centers[grade] is not None:
                        # Allow for some floating point tolerance
                        assert centers[grade] >= prev_center - 0.001, (
                            f"Non-monotonic: {grade} ({centers[grade]}) < previous ({prev_center})"
                        )
                        prev_center = centers[grade]

            # Check that essays are distributed across grades (not all clustered)
            grade_counts: dict[str, int] = {}
            for grade in result.primary_grades.values():
                grade_counts[grade] = grade_counts.get(grade, 0) + 1

            # Should have at least 3 different grades assigned
            assert len(grade_counts) >= 3, "Grades are too clustered"
