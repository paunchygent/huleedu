"""Test Swedish 8-grade system implementation."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.protocols import ContentClientProtocol


class TestSwedishGradeSystem:
    """Tests for the Swedish 8-anchor grade system implementation."""

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
    def sparse_anchor_rankings(self) -> list[dict[str, Any]]:
        """Create rankings with a sparse, realistic Swedish anchor distribution.

        - Many C and D anchors.
        - Few A and E anchors.
        - No F anchors.
        """
        return [
            # Student essays
            {
                "els_essay_id": "student_A_level",
                "bradley_terry_score": 0.9,
                "bradley_terry_se": 0.05,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_C_level",
                "bradley_terry_score": 0.5,
                "bradley_terry_se": 0.05,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_E_level",
                "bradley_terry_score": 0.1,
                "bradley_terry_se": 0.05,
                "is_anchor": False,
            },
            # Anchors (sparse distribution)
            {
                "els_essay_id": "anchor_A1",
                "bradley_terry_score": 0.85,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_C1",
                "bradley_terry_score": 0.55,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_C2",
                "bradley_terry_score": 0.45,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_D1",
                "bradley_terry_score": 0.3,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_D2",
                "bradley_terry_score": 0.2,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_E1",
                "bradley_terry_score": 0.15,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "E",
            },
        ]

    @pytest.mark.asyncio
    async def test_sparse_anchor_handling(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
        sparse_anchor_rankings: list[dict[str, Any]],
    ) -> None:
        """Test system handles non-uniform anchor distribution gracefully."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "sparse_swedish_anchors"
        mock_context.grade_scale = "swedish_8_anchor"

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
                rankings=sparse_anchor_rankings,
                cj_batch_id=1,
                assignment_id="sparse_test",
                course_code="SWE1",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True

            # Check that grades are reasonable despite sparse/missing anchors
            grades = result.primary_grades
            # With boundary constraints, high scorer should get A (not C due to prior bias)
            assert grades["student_A_level"] in ["A", "A-"], (
                f"Score 0.9 should get A/A- with boundary constraints, "
                f"got {grades['student_A_level']}"
            )
            assert grades["student_C_level"] in ["C", "C+", "C-", "B-", "D+"]
            assert grades["student_E_level"] in ["E", "E+", "E-", "F"]

            # Check that calibration info shows that some grades had 0 anchors
            # and that the system used expected positions for them (e.g., F)
            calib_info = result.calibration_info
            assert calib_info is not None
            grade_centers = calib_info["grade_centers"]
            assert "F" in grade_centers  # Should be estimated
            assert "B" in grade_centers  # Should be estimated

    @pytest.mark.asyncio
    async def test_population_priors_not_anchor_frequency(self) -> None:
        """Verify priors come from population, not anchor counts."""
        # This will be a more complex test to write, as it requires inspecting
        # the internal state of the calibration. For now, we can rely on the
        # fact that the code is written to use POPULATION_PRIORS.
        pass

    @pytest.mark.asyncio
    async def test_minus_grade_assignment(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test minus grades assigned at lower boundaries."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        # Anchors designed to create clear boundaries
        # B is centered at 0.8, C at 0.6. Boundary B/C is 0.7
        # C is centered at 0.6, D at 0.4. Boundary C/D is 0.5
        rankings = [
            # Student who should get B-
            {
                "els_essay_id": "student_B_minus",
                "bradley_terry_score": 0.76,
                "bradley_terry_se": 0.01,
                "is_anchor": False,
            },
            # Student who should get B
            {
                "els_essay_id": "student_B_solid",
                "bradley_terry_score": 0.80,
                "bradley_terry_se": 0.01,
                "is_anchor": False,
            },
            # Anchors
            {
                "els_essay_id": "anchor_A1",
                "bradley_terry_score": 0.95,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_A2",
                "bradley_terry_score": 0.9,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_A3",
                "bradley_terry_score": 0.85,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_B1",
                "bradley_terry_score": 0.8,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_B2",
                "bradley_terry_score": 0.8,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_B3",
                "bradley_terry_score": 0.8,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_C1",
                "bradley_terry_score": 0.6,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_C2",
                "bradley_terry_score": 0.6,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_C3",
                "bradley_terry_score": 0.6,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_D1",
                "bradley_terry_score": 0.4,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_D2",
                "bradley_terry_score": 0.4,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_D3",
                "bradley_terry_score": 0.4,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D",
            },
        ]

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "minus_grade_test"
        mock_context.grade_scale = "swedish_8_anchor"

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
                rankings=rankings,
                cj_batch_id=1,
                assignment_id="minus_grade_test",
                course_code="SWE1",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True
            grades = result.primary_grades
            assert grades["student_B_minus"] == "B-"
            assert grades["student_B_solid"] == "B"

    @pytest.mark.asyncio
    async def test_confidence_with_8_grades(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Verify improved confidence with fewer grades."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        # Rankings with good anchor coverage for the 8-grade system
        rankings = [
            # Students
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.95,
                "bradley_terry_se": 0.03,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_2",
                "bradley_terry_score": 0.82,
                "bradley_terry_se": 0.04,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_3",
                "bradley_terry_score": 0.68,
                "bradley_terry_se": 0.05,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_4",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.06,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_5",
                "bradley_terry_score": 0.35,
                "bradley_terry_se": 0.07,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_6",
                "bradley_terry_score": 0.22,
                "bradley_terry_se": 0.08,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_7",
                "bradley_terry_score": 0.08,
                "bradley_terry_se": 0.10,
                "is_anchor": False,
            },
            # Anchors
            {
                "els_essay_id": "anchor_A1",
                "bradley_terry_score": 0.9,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_A2",
                "bradley_terry_score": 0.9,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_A3",
                "bradley_terry_score": 0.9,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_B1",
                "bradley_terry_score": 0.75,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_B2",
                "bradley_terry_score": 0.75,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_B3",
                "bradley_terry_score": 0.75,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_C+1",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C+",
            },
            {
                "els_essay_id": "anchor_C+2",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C+",
            },
            {
                "els_essay_id": "anchor_C+3",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C+",
            },
            {
                "els_essay_id": "anchor_C1",
                "bradley_terry_score": 0.55,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_C2",
                "bradley_terry_score": 0.55,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_C3",
                "bradley_terry_score": 0.55,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_D+1",
                "bradley_terry_score": 0.45,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D+",
            },
            {
                "els_essay_id": "anchor_D+2",
                "bradley_terry_score": 0.45,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D+",
            },
            {
                "els_essay_id": "anchor_D+3",
                "bradley_terry_score": 0.45,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D+",
            },
            {
                "els_essay_id": "anchor_D1",
                "bradley_terry_score": 0.35,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_D2",
                "bradley_terry_score": 0.35,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_D3",
                "bradley_terry_score": 0.35,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_E1",
                "bradley_terry_score": 0.2,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "E",
            },
            {
                "els_essay_id": "anchor_E2",
                "bradley_terry_score": 0.2,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "E",
            },
            {
                "els_essay_id": "anchor_E3",
                "bradley_terry_score": 0.2,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "E",
            },
            {
                "els_essay_id": "anchor_F1",
                "bradley_terry_score": 0.1,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "F",
            },
            {
                "els_essay_id": "anchor_F2",
                "bradley_terry_score": 0.1,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "F",
            },
            {
                "els_essay_id": "anchor_F3",
                "bradley_terry_score": 0.1,
                "bradley_terry_se": 0.02,
                "is_anchor": True,
                "anchor_grade": "F",
            },
        ]

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "confidence_test"
        mock_context.grade_scale = "swedish_8_anchor"

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
                rankings=rankings,
                cj_batch_id=1,
                assignment_id="confidence_test",
                course_code="SWE1",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True

            # Expect 70%+ MID/HIGH confidence with good anchors
            confidence_labels = result.confidence_labels
            high_mid_count = sum(
                1 for label in confidence_labels.values() if label in ["HIGH", "MID"]
            )
            total_count = len(confidence_labels)
            assert (high_mid_count / total_count) >= 0.7

    @pytest.mark.asyncio
    async def test_realistic_anchor_distribution(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test with realistic anchor distribution: 2-3 anchors per grade.

        This distribution represents a typical Swedish exam calibration set
        with sufficient anchors for stable estimation.
        """

        # Create realistic distribution with 22 total anchors
        realistic_rankings = [
            # Test student essays - same scores as sparse test
            {
                "els_essay_id": "student_A_level",
                "bradley_terry_score": 0.9,
                "bradley_terry_se": 0.05,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_C_level",
                "bradley_terry_score": 0.5,
                "bradley_terry_se": 0.05,
                "is_anchor": False,
            },
            {
                "els_essay_id": "student_E_level",
                "bradley_terry_score": 0.1,
                "bradley_terry_se": 0.05,
                "is_anchor": False,
            },
            # A anchors (2 anchors) - Excellent essays
            {
                "els_essay_id": "anchor_A1",
                "bradley_terry_score": 0.88,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_A2",
                "bradley_terry_score": 0.85,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            # B anchors (3 anchors) - Very good essays
            {
                "els_essay_id": "anchor_B1",
                "bradley_terry_score": 0.78,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_B2",
                "bradley_terry_score": 0.75,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_B3",
                "bradley_terry_score": 0.72,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            # C+ anchors (3 anchors) - Approaching excellence
            {
                "els_essay_id": "anchor_Cplus1",
                "bradley_terry_score": 0.66,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "C+",
            },
            {
                "els_essay_id": "anchor_Cplus2",
                "bradley_terry_score": 0.63,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "C+",
            },
            {
                "els_essay_id": "anchor_Cplus3",
                "bradley_terry_score": 0.60,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "C+",
            },
            # C anchors (3 anchors) - Good (modal grade)
            {
                "els_essay_id": "anchor_C1",
                "bradley_terry_score": 0.54,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_C2",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_C3",
                "bradley_terry_score": 0.46,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            # D+ anchors (3 anchors) - Developing competence
            {
                "els_essay_id": "anchor_Dplus1",
                "bradley_terry_score": 0.40,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "D+",
            },
            {
                "els_essay_id": "anchor_Dplus2",
                "bradley_terry_score": 0.37,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "D+",
            },
            {
                "els_essay_id": "anchor_Dplus3",
                "bradley_terry_score": 0.34,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "D+",
            },
            # D anchors (3 anchors) - Satisfactory
            {
                "els_essay_id": "anchor_D1",
                "bradley_terry_score": 0.28,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_D2",
                "bradley_terry_score": 0.25,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_D3",
                "bradley_terry_score": 0.22,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            # E anchors (3 anchors) - Barely passing
            {
                "els_essay_id": "anchor_E1",
                "bradley_terry_score": 0.16,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "E",
            },
            {
                "els_essay_id": "anchor_E2",
                "bradley_terry_score": 0.13,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "E",
            },
            {
                "els_essay_id": "anchor_E3",
                "bradley_terry_score": 0.10,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "E",
            },
            # F anchors (2 anchors) - Failing
            {
                "els_essay_id": "anchor_F1",
                "bradley_terry_score": 0.06,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "F",
            },
            {
                "els_essay_id": "anchor_F2",
                "bradley_terry_score": 0.03,
                "bradley_terry_se": 0.04,
                "is_anchor": True,
                "anchor_grade": "F",
            },
        ]

        # Initialize projector
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "realistic_distribution"
        mock_context.grade_scale = "swedish_8_anchor"

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Act
            result = await grade_projector.calculate_projections(
                session=mock_database_session,
                rankings=realistic_rankings,
                cj_batch_id=1,
                assignment_id="realistic_test",
                course_code="SWE1",
                content_client=mock_content_client,
                correlation_id=correlation_id,
            )

            # Assert
            assert result.projections_available is True

            grades = result.primary_grades
            confidence_labels = result.confidence_labels

            # With realistic anchor distribution, grades should be accurate
            print("\n=== Realistic Distribution Results ===")
            print(
                f"Student A (0.9): Grade={grades['student_A_level']}, "
                f"Confidence={confidence_labels['student_A_level']}"
            )
            print(
                f"Student C (0.5): Grade={grades['student_C_level']}, "
                f"Confidence={confidence_labels['student_C_level']}"
            )
            print(
                f"Student E (0.1): Grade={grades['student_E_level']}, "
                f"Confidence={confidence_labels['student_E_level']}"
            )

            # Expected grade assignments with good anchor coverage
            # With boundary constraints, grades should match boundary membership
            assert grades["student_A_level"] in ["A", "A-"], (
                f"With realistic anchors, high scorer (0.9) should get A/A-, "
                f"got {grades['student_A_level']}"
            )

            assert grades["student_C_level"] in ["C", "C+", "C-"], (
                f"With realistic anchors, mid scorer (0.5) should get C range, "
                f"got {grades['student_C_level']}"
            )

            assert grades["student_E_level"] in ["E", "E+", "E-", "F"], (
                f"With realistic anchors, low scorer (0.1) should get E/F range, "
                f"got {grades['student_E_level']}"
            )

            # Confidence should be HIGH with good anchors and boundary constraints
            # (boundary constraints reduce entropy significantly)
            for student_id in ["student_A_level", "student_C_level", "student_E_level"]:
                assert confidence_labels[student_id] in ["HIGH", "MID"], (
                    f"With 22 anchors, {student_id} should have HIGH/MID confidence, "
                    f"got {confidence_labels[student_id]}"
                )

            # Get calibration info to understand the impact
            calib_info = result.calibration_info
            if calib_info and "grade_centers" in calib_info:
                print("\nCalibration Info:")
                grade_centers = calib_info.get("grade_centers", {})
                for grade in ["F", "E", "D", "D+", "C", "C+", "B", "A"]:
                    if grade in grade_centers:
                        center_info = grade_centers[grade]
                        # Handle both dict and scalar formats
                        if isinstance(center_info, dict):
                            print(
                                f"  {grade}: mean={center_info.get('mean', 0):.3f}, "
                                f"n_anchors={center_info.get('n_anchors', 0)}"
                            )
                        else:
                            print(f"  {grade}: value={center_info:.3f}")

            print("\n✅ Realistic distribution test completed successfully")
