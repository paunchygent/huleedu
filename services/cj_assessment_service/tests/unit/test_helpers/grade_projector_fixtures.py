"""Shared fixtures for grade projector tests.

This module provides reusable test fixtures and helpers for testing the grade
projection system, following rule 075 requirement for explicit test utilities.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from services.cj_assessment_service.cj_core_logic.grade_projection.context_service import (
    ProjectionContextService,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)


def create_test_projector() -> GradeProjector:
    """Create a GradeProjector with mocked dependencies for testing.

    Returns:
        GradeProjector instance with all dependencies mocked.
    """
    mock_session_provider = Mock(spec=SessionProviderProtocol)
    # Mock the async session context manager properly
    mock_session = AsyncMock()
    mock_session.add_all = Mock()  # add_all is synchronous in SQLAlchemy
    mock_session_provider.session.return_value = mock_session
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    mock_instruction_repo = Mock(spec=AssessmentInstructionRepositoryProtocol)
    mock_anchor_repo = Mock(spec=AnchorRepositoryProtocol)

    context_service = ProjectionContextService(
        session_provider=mock_session_provider,
        instruction_repository=mock_instruction_repo,
        anchor_repository=mock_anchor_repo,
    )

    return GradeProjector(
        session_provider=mock_session_provider,
        context_service=context_service,
    )


@pytest.fixture
def mock_content_client() -> AsyncMock:
    """Create mock content client matching ContentClientProtocol interface.

    Returns:
        AsyncMock configured with ContentClientProtocol interface.
    """
    client = AsyncMock(spec=ContentClientProtocol)
    client.fetch_content = AsyncMock(return_value="Sample anchor essay content")
    client.store_content = AsyncMock(return_value={"content_id": "stored_123"})
    return client


@pytest.fixture
def mock_database_session() -> AsyncMock:
    """Create mock database session for grade projector operations.

    Returns:
        AsyncMock configured as SQLAlchemy async session.
    """
    session = AsyncMock()
    # Mock async methods properly
    session.add_all = Mock()  # add_all is synchronous
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_anchor_context() -> Mock:
    """Create mock context with anchor essays for testing anchor-based projections.

    Returns:
        Mock context with 3 diverse anchor essays (A, B, C grades).
    """
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
    mock_context.grade_scale = "swedish_8_anchor"
    return mock_context


@pytest.fixture
def mock_empty_context() -> Mock:
    """Create mock context with no anchor essays for testing fallback behavior.

    Returns:
        Mock context with empty anchor list.
    """
    mock_context = Mock()
    mock_context.anchor_essay_refs = []
    mock_context.context_source = "course_fallback"
    mock_context.assessment_instructions = "Default grading instructions"
    mock_context.anchor_contents = {}
    mock_context.grade_scale = "swedish_8_anchor"
    return mock_context


@pytest.fixture
def sample_rankings_with_anchors() -> list[dict[str, Any]]:
    """Create sample rankings that include both student and anchor essays.

    Returns:
        List of rankings with proper flags and metadata for 3 students and 3 anchors.
    """
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
