"""Unit tests for Grade Projector System behavioral outcomes.

This module tests the observable behavioral outcomes of the grade projection system:
- Confidence score calculation produces valid ranges and categorization
- Grade assignment reflects ranking order appropriately
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
        return mock_context

    @pytest.fixture
    def mock_empty_context(self) -> Mock:
        """Create mock context with no anchor essays for testing fallback behavior."""
        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "course_fallback"
        return mock_context

    @pytest.fixture
    def sample_rankings_with_anchors(self) -> list[dict[str, Any]]:
        """Create sample rankings that include both student and anchor essays."""
        return [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.85,
                "rank": 1,
                "comparison_count": 8,
            },
            {
                "els_essay_id": "ANCHOR_1_abc123",
                "bradley_terry_score": 0.90,
                "rank": 2,
                "comparison_count": 10,
            },
            {
                "els_essay_id": "student_2",
                "bradley_terry_score": 0.65,
                "rank": 3,
                "comparison_count": 7,
            },
            {
                "els_essay_id": "ANCHOR_2_def456",
                "bradley_terry_score": 0.70,
                "rank": 4,
                "comparison_count": 9,
            },
            {
                "els_essay_id": "student_3",
                "bradley_terry_score": 0.35,
                "rank": 5,
                "comparison_count": 6,
            },
        ]

    @pytest.mark.asyncio
    async def test_confidence_score_calculation_with_anchors(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        mock_anchor_context: Mock,
        sample_rankings_with_anchors: list[dict[str, Any]],
    ) -> None:
        """Test confidence scores are in valid 0.0-1.0 range with HIGH/MID/LOW categorization."""
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

            # Assert - Behavioral outcomes
            assert result.projections_available is True

            # All confidence scores must be in valid range
            for confidence_score in result.confidence_scores.values():
                assert 0.0 <= confidence_score <= 1.0

            # All confidence labels must be valid categories
            valid_confidence_labels = {"HIGH", "MID", "LOW"}
            for confidence_label in result.confidence_labels.values():
                assert confidence_label in valid_confidence_labels

            # All grades must be valid letter grades
            valid_grades = {"A", "B", "C", "D", "E", "F", "U"}
            for grade in result.primary_grades.values():
                assert grade in valid_grades

            # Projections should exist for ALL essays in rankings (including anchors)
            assert len(result.primary_grades) == len(sample_rankings_with_anchors)
            assert len(result.confidence_scores) == len(sample_rankings_with_anchors)
            assert len(result.confidence_labels) == len(sample_rankings_with_anchors)

            # All essay IDs from rankings should have projections
            ranking_essay_ids = {r["els_essay_id"] for r in sample_rankings_with_anchors}
            projection_essay_ids = set(result.primary_grades.keys())
            assert ranking_essay_ids == projection_essay_ids

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

        sample_rankings = [
            {"els_essay_id": "student_1", "bradley_terry_score": 0.85, "rank": 1},
            {"els_essay_id": "student_2", "bradley_terry_score": 0.65, "rank": 2},
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

    @pytest.mark.asyncio
    async def test_empty_rankings_handling(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that empty rankings list produces valid empty projections."""
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

        # Assert - Should return valid but empty projections
        assert result.projections_available is True
        assert len(result.primary_grades) == 0
        assert len(result.confidence_labels) == 0
        assert len(result.confidence_scores) == 0

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
            {"els_essay_id": "student_1", "bradley_terry_score": 0.75, "rank": 1},
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
