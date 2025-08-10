"""Test anchor validation functionality in grade projector."""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from uuid import uuid4

from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector


class TestAnchorValidation:
    """Test the anchor validation and warning system."""

    @pytest.mark.asyncio
    async def test_warns_missing_major_grades(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that system warns when major grades are missing from anchors."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        # Rankings with anchors only for A, B, C (missing F, E, D)
        sparse_rankings = [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.05,
                "rank": 1,
                "is_anchor": False,
            },
            {
                "els_essay_id": "anchor_a",
                "bradley_terry_score": 0.90,
                "bradley_terry_se": 0.02,
                "rank": 2,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_b",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.02,
                "rank": 3,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_c",
                "bradley_terry_score": 0.40,
                "bradley_terry_se": 0.02,
                "rank": 4,
                "is_anchor": True,
                "anchor_grade": "C",
            },
        ]

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "test_validation"
        mock_context.assessment_instructions = "Grade based on quality"
        mock_context.anchor_contents = {}

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Capture log warnings
            with patch.object(grade_projector.logger, "warning") as mock_warning:
                # Act
                result = await grade_projector.calculate_projections(
                    session=mock_database_session,
                    rankings=sparse_rankings,
                    cj_batch_id=1,
                    assignment_id="test_sparse",
                    course_code="TEST",
                    content_client=mock_content_client,
                    correlation_id=correlation_id,
                )

                # Assert
                assert result.projections_available is True

                # Check that warning was logged about missing grades
                warning_calls = mock_warning.call_args_list
                assert len(warning_calls) >= 1

                # Find the missing grades warning
                found_missing_warning = False
                for call in warning_calls:
                    args = call[0]
                    if "Missing anchors for major grades" in str(args):
                        found_missing_warning = True
                        # Should mention D, E, F are missing
                        assert "D" in str(args)
                        assert "E" in str(args)
                        assert "F" in str(args)
                        break

                assert found_missing_warning, "Should warn about missing major grades"

    @pytest.mark.asyncio
    async def test_no_warning_with_complete_coverage(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that no warning is issued when all major grades are covered."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        # Rankings with complete major grade coverage
        complete_rankings = [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.05,
                "rank": 1,
                "is_anchor": False,
            },
            {
                "els_essay_id": "anchor_a",
                "bradley_terry_score": 0.90,
                "bradley_terry_se": 0.02,
                "rank": 2,
                "is_anchor": True,
                "anchor_grade": "A",
            },
            {
                "els_essay_id": "anchor_b",
                "bradley_terry_score": 0.75,
                "bradley_terry_se": 0.02,
                "rank": 3,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_c",
                "bradley_terry_score": 0.55,
                "bradley_terry_se": 0.02,
                "rank": 4,
                "is_anchor": True,
                "anchor_grade": "C",
            },
            {
                "els_essay_id": "anchor_d",
                "bradley_terry_score": 0.35,
                "bradley_terry_se": 0.02,
                "rank": 5,
                "is_anchor": True,
                "anchor_grade": "D",
            },
            {
                "els_essay_id": "anchor_e",
                "bradley_terry_score": 0.20,
                "bradley_terry_se": 0.02,
                "rank": 6,
                "is_anchor": True,
                "anchor_grade": "E",
            },
            {
                "els_essay_id": "anchor_f",
                "bradley_terry_score": 0.05,
                "bradley_terry_se": 0.02,
                "rank": 7,
                "is_anchor": True,
                "anchor_grade": "F",
            },
        ]

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "test_complete"
        mock_context.assessment_instructions = "Grade based on quality"
        mock_context.anchor_contents = {}

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Capture log messages
            with patch.object(grade_projector.logger, "info") as mock_info:
                with patch.object(grade_projector.logger, "warning") as mock_warning:
                    # Act
                    result = await grade_projector.calculate_projections(
                        session=mock_database_session,
                        rankings=complete_rankings,
                        cj_batch_id=1,
                        assignment_id="test_complete",
                        course_code="TEST",
                        content_client=mock_content_client,
                        correlation_id=correlation_id,
                    )

                    # Assert
                    assert result.projections_available is True

                    # Check that info was logged about good coverage
                    info_calls = mock_info.call_args_list
                    found_good_coverage = False
                    for call in info_calls:
                        args = call[0]
                        if "Good anchor coverage" in str(args):
                            found_good_coverage = True
                            break

                    assert found_good_coverage, "Should log info about good anchor coverage"

                    # Check that no warning about missing grades was logged
                    warning_calls = mock_warning.call_args_list
                    for call in warning_calls:
                        args = call[0]
                        assert "Missing anchors for major grades" not in str(args)

    @pytest.mark.asyncio
    async def test_strong_warning_many_missing_grades(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that a strong warning is issued when more than 3 major grades are missing."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        # Rankings with only B and C anchors (missing F, E, D, A - 4 grades)
        very_sparse_rankings = [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.05,
                "rank": 1,
                "is_anchor": False,
            },
            {
                "els_essay_id": "anchor_b",
                "bradley_terry_score": 0.65,
                "bradley_terry_se": 0.02,
                "rank": 2,
                "is_anchor": True,
                "anchor_grade": "B",
            },
            {
                "els_essay_id": "anchor_c",
                "bradley_terry_score": 0.40,
                "bradley_terry_se": 0.02,
                "rank": 3,
                "is_anchor": True,
                "anchor_grade": "C",
            },
        ]

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "test_very_sparse"
        mock_context.assessment_instructions = "Grade based on quality"
        mock_context.anchor_contents = {}

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Capture log warnings
            with patch.object(grade_projector.logger, "warning") as mock_warning:
                # Act
                result = await grade_projector.calculate_projections(
                    session=mock_database_session,
                    rankings=very_sparse_rankings,
                    cj_batch_id=1,
                    assignment_id="test_very_sparse",
                    course_code="TEST",
                    content_client=mock_content_client,
                    correlation_id=correlation_id,
                )

                # Assert
                assert result.projections_available is True

                # Check that both warnings were logged
                warning_calls = mock_warning.call_args_list
                assert len(warning_calls) >= 2

                # Check for the strong warning about calibration quality
                found_quality_warning = False
                for call in warning_calls:
                    args = call[0]
                    if "Calibration quality may be compromised" in str(args):
                        found_quality_warning = True
                        break

                assert found_quality_warning, "Should warn strongly about calibration quality"

    @pytest.mark.asyncio
    async def test_fine_grades_mapped_to_major(
        self,
        mock_content_client: AsyncMock,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that fine grades (B+, B-, etc.) are correctly mapped to major grades."""
        # Arrange
        grade_projector = GradeProjector()
        correlation_id = uuid4()

        # Rankings with fine-grained anchors that cover all major grades
        fine_rankings = [
            {
                "els_essay_id": "student_1",
                "bradley_terry_score": 0.50,
                "bradley_terry_se": 0.05,
                "rank": 1,
                "is_anchor": False,
            },
            {
                "els_essay_id": "anchor_a_minus",
                "bradley_terry_score": 0.88,
                "bradley_terry_se": 0.02,
                "rank": 2,
                "is_anchor": True,
                "anchor_grade": "A-",  # Maps to A
            },
            {
                "els_essay_id": "anchor_b_plus",
                "bradley_terry_score": 0.72,
                "bradley_terry_se": 0.02,
                "rank": 3,
                "is_anchor": True,
                "anchor_grade": "B+",  # Maps to B
            },
            {
                "els_essay_id": "anchor_c_minus",
                "bradley_terry_score": 0.48,
                "bradley_terry_se": 0.02,
                "rank": 4,
                "is_anchor": True,
                "anchor_grade": "C-",  # Maps to C
            },
            {
                "els_essay_id": "anchor_d_plus",
                "bradley_terry_score": 0.32,
                "bradley_terry_se": 0.02,
                "rank": 5,
                "is_anchor": True,
                "anchor_grade": "D+",  # Maps to D
            },
            {
                "els_essay_id": "anchor_e_minus",
                "bradley_terry_score": 0.15,
                "bradley_terry_se": 0.02,
                "rank": 6,
                "is_anchor": True,
                "anchor_grade": "E-",  # Maps to E
            },
            {
                "els_essay_id": "anchor_f_plus",
                "bradley_terry_score": 0.08,
                "bradley_terry_se": 0.02,
                "rank": 7,
                "is_anchor": True,
                "anchor_grade": "F+",  # Maps to F
            },
        ]

        mock_context = Mock()
        mock_context.anchor_essay_refs = []
        mock_context.context_source = "test_fine_grades"
        mock_context.assessment_instructions = "Grade based on quality"
        mock_context.anchor_contents = {}

        with patch.object(
            grade_projector.context_builder, "build", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_context

            # Capture log messages
            with patch.object(grade_projector.logger, "info") as mock_info:
                # Act
                result = await grade_projector.calculate_projections(
                    session=mock_database_session,
                    rankings=fine_rankings,
                    cj_batch_id=1,
                    assignment_id="test_fine",
                    course_code="TEST",
                    content_client=mock_content_client,
                    correlation_id=correlation_id,
                )

                # Assert
                assert result.projections_available is True

                # Check that good coverage was detected despite using fine grades
                info_calls = mock_info.call_args_list
                found_good_coverage = False
                for call in info_calls:
                    args = call[0]
                    if "Good anchor coverage" in str(args):
                        found_good_coverage = True
                        break

                assert found_good_coverage, "Should recognize coverage from fine grades"


@pytest.fixture
def mock_content_client() -> AsyncMock:
    """Create a mock content client."""
    client = AsyncMock()
    client.get_anchor_essay_content = AsyncMock(return_value={})
    return client


@pytest.fixture
def mock_database_session() -> AsyncMock:
    """Create a mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session