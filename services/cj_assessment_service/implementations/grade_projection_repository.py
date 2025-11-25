"""Grade projection repository implementation for CJ Assessment Service."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import GradeProjection
from services.cj_assessment_service.protocols import GradeProjectionRepositoryProtocol

logger = create_service_logger("cj_assessment_service.repositories.grade_projection")


class PostgreSQLGradeProjectionRepository(GradeProjectionRepositoryProtocol):
    """PostgreSQL implementation for grade projection persistence."""

    async def store_grade_projections(
        self,
        session: AsyncSession,
        projections: list[GradeProjection],
    ) -> None:
        """Store grade projections in database."""
        if not projections:
            return

        try:
            session.add_all(projections)
            await session.flush()
            logger.info("Stored %s grade projections", len(projections))
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Failed to store grade projections",
                extra={"error": str(exc)},
                exc_info=True,
            )
            raise
