"""Session provider and GradeProjector fixtures for CJ Assessment Service tests.

Provides mock fixtures with proper async context manager patterns for:
- SessionProviderProtocol with asynccontextmanager session()
- GradeProjector with all required dependencies

These fixtures follow DDD principles:
- Test behaviors, not plumbing
- Protocol-mocked dependencies
- One fixture, one responsibility
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.grade_projection.calibration_engine import (
    CalibrationEngine,
)
from services.cj_assessment_service.cj_core_logic.grade_projection.context_service import (
    ProjectionContextService,
)
from services.cj_assessment_service.cj_core_logic.grade_projection.projection_engine import (
    ProjectionEngine,
)
from services.cj_assessment_service.cj_core_logic.grade_projection.projection_repository import (
    GradeProjectionRepository,
)
from services.cj_assessment_service.cj_core_logic.grade_projection.scale_resolver import (
    GradeScaleResolver,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.protocols import SessionProviderProtocol


@pytest.fixture
def mock_session_provider() -> AsyncMock:
    """Provide mock SessionProviderProtocol with proper async context manager.

    Returns a mock that correctly implements the async context manager protocol
    for session(), yielding a mock AsyncSession with configured methods.

    Usage:
        async with session_provider.session() as session:
            result = await session.execute(stmt)
    """
    provider = AsyncMock(spec=SessionProviderProtocol)

    @asynccontextmanager
    async def mock_session() -> AsyncGenerator[AsyncMock, None]:
        session = AsyncMock(spec=AsyncSession)
        # Configure common session methods
        session.execute = AsyncMock()
        session.add = AsyncMock()
        session.add_all = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.get = AsyncMock()
        session.scalar = AsyncMock()
        session.scalars = AsyncMock()
        yield session

    provider.session = mock_session
    return provider


@pytest.fixture
def mock_grade_projector(mock_session_provider: AsyncMock) -> GradeProjector:
    """Provide fully-initialized GradeProjector with protocol-mocked dependencies.

    Returns a GradeProjector instance with all required dependencies mocked as
    protocol types. Uses the mock_session_provider fixture for consistency.

    Dependencies mocked:
    - SessionProviderProtocol (from fixture)
    - ProjectionContextService
    - GradeScaleResolver
    - CalibrationEngine
    - ProjectionEngine
    - GradeProjectionRepository

    Usage in tests:
        grade_projector.project_grades_for_batch(...)
        # All internal operations use mocks
    """
    mock_context_service = AsyncMock(spec=ProjectionContextService)
    mock_scale_resolver = AsyncMock(spec=GradeScaleResolver)
    mock_calibration_engine = AsyncMock(spec=CalibrationEngine)
    mock_projection_engine = AsyncMock(spec=ProjectionEngine)
    mock_repository = AsyncMock(spec=GradeProjectionRepository)

    return GradeProjector(
        session_provider=mock_session_provider,
        context_service=mock_context_service,
        scale_resolver=mock_scale_resolver,
        calibration_engine=mock_calibration_engine,
        projection_engine=mock_projection_engine,
        repository=mock_repository,
    )
