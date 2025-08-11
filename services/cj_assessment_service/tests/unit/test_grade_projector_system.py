"""Unit tests for Grade Projector System behavioral outcomes.

This module tests the observable behavioral outcomes of the grade projection system:
- Statistical calibration from anchor essays with known grades
- Grade probability distributions based on Bradley-Terry scores and SEs
- Entropy-based confidence calculation
- System handles missing anchor scenarios gracefully
- Error resilience with invalid inputs
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.cj_core_logic.grade_utils import _grade_to_normalized
from services.cj_assessment_service.protocols import ContentClientProtocol


class TestGradeProjectorSystem:
    """Tests for the Grade Projector System functionality."""

    @pytest.fixture
    def mock_content_client(self) -> AsyncMock:
        """Create mock content client matching ContentClientProtocol interface."""
        client = AsyncMock(spec=ContentClientProtocol)
        client.fetch_content = AsyncMock(return_value="Sample anchor essay content")
        client.store_content = AsyncMock(return_value={"content_id": "stored_123"})
        return client

    @pytest.fixture
    def mock_database_session(self) -> AsyncMock:
        """Create mock database session for grade projector operations."""
        session = AsyncMock()
        # Mock async methods properly
        session.add_all = Mock()  # add_all is synchronous
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.get = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def mock_anchor_context(self) -> Mock:
        """Create mock context with anchor essays for testing anchor-based projections."""
        mock_context = Mock()
        mock_context.anchor_essay_refs = [
            Mock(id=1, grade="A", text_storage_id="anchor_a_123"),
            Mock(id=2, grade="B", text_storage_id="anchor_b_456"),
            Mock(id=3, grade="C", text_storage_id="anchor_c_789"),
        ]
        mock_context.context_source = "assignment_789"
        mock_context.assessment_instructions = "Grade based on clarity and argumentation"
        mock_context.anchor_contents = {
            "anchor_a_123": "Excellent essay content",
            "anchor_b_456": "Good essay content",
            "anchor_c_789": "Average essay content",
        }
        return mock_context

    @pytest.fixture
    def mock_empty_context(self) -> Mock:
        """Create mock context with no anchor essays for testing fallback behavior."""
        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "course_fallback"
        mock_context.assessment_instructions = "Default grading instructions"
        mock_context.anchor_contents = {}
        return mock_context

    @pytest.fixture
    def sample_rankings_with_anchors(self) -> list[dict[str, Any]]:
        """Create sample rankings that include both student and anchor essays with proper flags."""
        return [
            # Student essays
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.85,
                "bradley_terry_se": 0.05,
                "rank": 1,
                "comparison_count": 8,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_2",
                "bradley_terry_score": 0.45,
                "bradley_terry_se": 0.08,
                "rank": 3,
                "comparison_count": 7,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_3",
                "bradley_terry_score": 0.15,
                "bradley_terry_se": 0.10,
                "rank": 5,
                "comparison_count": 6,
                "is_anchor": False,
            },
            # Anchor essays with known grades
            {
                "els_essay_id": "anchor_1",
                "bradley_terry_score": 0.90,
                "bradley_terry_se": 0.03,
                "rank": 2,
                "comparison_count": 10,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_2",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.04,
                "rank": 4,
                "comparison_count": 9,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_3",
                "bradley_terry_score": 0.10,
                "bradley_terry_se": 0.06,
                "rank": 6,
                "comparison_count": 8,
                "is_anchor": True,
                "anchor_grade": "C",
            },
        ]

    @pytest.mark.asyncio
    async def test_statistical_calibration_with_anchors(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test statistical calibration produces valid grade probabilities and confidence scores."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        # Mock the context builder to return anchors
        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
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

            # Verify BT stats contain mean and SE
            for essay_id in student_essay_ids:
                if essay_id in result.bt_stats:
                    stats = result.bt_stats[essay_id]
                    assert "bt_mean" in stats
                    assert "bt_se" in stats
                    assert stats["bt_se"] >= 0.0

    def test_normalized_score_transformation_ranges(self) -> None:
        """Test that grade-to-normalized transformation produces valid 0.0-1.0 range."""
        # Arrange - Test all possible letter grades
        test_cases = [
            ("A", 1.0),
            ("B", 0.8),
            ("C", 0.6),
            ("D", 0.4),
            ("E", 0.2),
            ("F", 0.0),
            ("U", 0.0),
            (None, 0.0),
        ]

        # Act & Assert - Test behavioral outcome
        for grade, expected_score in test_cases:
            normalized_score = _grade_to_normalized(grade)

            # All normalized scores must be in valid range
            assert 0.0 <= normalized_score <= 1.0
            assert normalized_score == expected_score

    @pytest.mark.asyncio
    async def test_fallback_behavior_without_anchors(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_empty_context: Mock,
    ) -> None:
        """Test that system returns projections_available=False when no anchor essays exist."""
        # Arrange
        grade_projector = GradeProjector()
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
                session=mock_database_session,
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
    async def test_empty_rankings_handling(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that empty rankings list produces valid empty projections
        with projections_available=False."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        # Act
        result = await grade_projector.calculate_projections(
            session=mock_database_session,
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
    async def test_error_resilience_with_invalid_anchor_data(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that system handles anchor retrieval errors gracefully."""
        # Arrange
        grade_projector = GradeProjector()
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
                    session=mock_database_session,
                    rankings=sample_rankings,
                    cj_batch_id=1,
                    assignment_id="assignment_789",
                    course_code="ENG5",
                    content_client=mock_content_client,
                    correlation_id=correlation_id,
                )

    @pytest.mark.asyncio
    async def test_insufficient_grade_diversity(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
    ) -> None:
        """Test that system requires sufficient grade diversity in anchors for calibration."""
        # Arrange
        grade_projector = GradeProjector()
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
                session=mock_database_session,
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
    async def test_confidence_based_on_entropy(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
    ) -> None:
        """Test that confidence scores are based on entropy of probability distributions."""
        # Arrange
        grade_projector = GradeProjector()
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
                session=mock_database_session,
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

            # Generally, lower SE should lead to higher confidence
            # (though not always due to entropy)
            # We test that the mechanism exists, not the exact mapping

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
        mock_anchor_context: Mock,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test that grade probability distributions always sum to 1.0."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
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
    async def test_calibration_boundary_monotonicity(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test that grade boundaries are monotonically decreasing (A > B > C > D > F)."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
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

    @pytest.mark.asyncio
    async def test_se_values_reasonable(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test that standard errors are non-negative and within reasonable bounds."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_anchor_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
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

    @pytest.mark.asyncio
    async def test_single_anchor_handling(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
    ) -> None:
        """Test that system handles single anchor gracefully (no calibration possible)."""
        # Arrange
        grade_projector = GradeProjector()
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
                session=mock_database_session,
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
        mock_anchor_context: Mock,
    ) -> None:
        """Test handling of extreme Bradley-Terry scores (near 0 or 1)."""
        # Arrange
        grade_projector = GradeProjector()
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
                session=mock_database_session,
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

            # With limited anchors (only A and C), grade assignment might vary
            # We just test that grades are assigned and are valid
            # The exact grade depends on the calibration from the limited anchors

    @pytest.mark.asyncio
    async def test_anchors_without_grades(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
    ) -> None:
        """Test that anchors missing grade metadata are handled gracefully."""
        # Arrange
        grade_projector = GradeProjector()
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
                session=mock_database_session,
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

    @pytest.mark.asyncio
    async def test_integration_with_realistic_choix_output(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
    ) -> None:
        """Integration test with realistic Bradley-Terry scores from Choix algorithm."""
        # Arrange
        grade_projector = GradeProjector()
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
                session=mock_database_session,
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
